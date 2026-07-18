"""Novel Bible editor — tabbed world setting and style guide editor."""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.storage.editor_layout import EditorLayoutStore
from app.storage.bible_models import BibleElementType, WorldOverview
from app.storage.models import CharacterTier, StyleGuide
from app.storage.project_files import (
    load_project,
    save_style_guide,
)
from app.ui.character_editor import CharacterEditorView
from app.ui.world_bible_editor import WorldBibleEditorView
from app.ui.widgets import (
    CollapsibleSection,
    StringListEditor,
    combo_val as _combo_val,
    set_combo as _set_combo,
)
from app.utils.template_merge import (
    TemplateMergeMode,
    apply_story_template,
    merge_style_guide,
    preview_story_template_replace,
)
from app.utils.xianxia_template import get_xianxia_template

logger = logging.getLogger(__name__)


class BibleEditorView(QWidget):
    """Tabbed editor for world setting and style guide.

    Receives the project directory path via ``load_project_dir()`` and
    handles its own persistence. Emits ``saved`` after successful writes.
    """

    saved = Signal()
    dirty_changed = Signal(bool)
    elements_changed = Signal()
    scene_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_dir: Path | None = None
        self._baseline_style: StyleGuide | None = None
        self._world_dirty = False
        self._style_dirty = False
        self._populating = False
        self._last_dirty = False
        self._layout_store: EditorLayoutStore | None = None
        self._style_sections: dict[str, CollapsibleSection] = {}
        self._setup_ui()
        self._connect_dirty_tracking()

    # ── Public API ─────────────────────────────────────────────────────────

    def load_project_dir(self, project_dir: Path) -> None:
        """Load project data from disk and populate the editor."""
        self._project_dir = project_dir
        project = load_project(project_dir)
        layout_path = project_dir / ".novel-agent" / "editor-layout.yaml"
        had_layout = layout_path.exists()
        self._layout_store = EditorLayoutStore(project_dir)
        had_layout = had_layout and not self._layout_store.recovered_from_error
        self._character_tab.set_layout_store(self._layout_store)
        self._populating = True
        try:
            self._world_tab.set_layout_store(self._layout_store)
            self._world_tab.load_project_dir(project_dir)
            self._populate_style_tab(project.style_guide)
            self._character_tab.load_project_dir(project_dir)
            if not had_layout:
                self._layout_store.layout.style.collapsed_sections = ["advanced"]
                self._layout_store.schedule_save()
            self._apply_style_layout()
            self._restore_selected_tab()
        finally:
            self._populating = False
        self._baseline_style = self._gather_style()
        self._world_dirty = self._world_tab.is_dirty
        self._style_dirty = False
        self._update_aggregate_dirty_state()
        self._refresh_overview()

    @property
    def is_dirty(self) -> bool:
        return self._world_tab.is_dirty or self._style_dirty or self._character_tab.is_dirty

    def set_current_scene_id(self, scene_id: str | None) -> None:
        self._character_tab.set_current_scene_id(scene_id)
        self._world_tab.set_current_scene_id(scene_id)

    def refresh_usage(self) -> None:
        self._world_tab.refresh_usage()

    # ── UI Setup ───────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.addStretch()
        self._unsaved_label = QLabel("设定集未保存")
        self._unsaved_label.setStyleSheet("color: #d48806;")
        self._unsaved_label.setVisible(False)
        toolbar.addWidget(self._unsaved_label)
        self._save_btn = QPushButton("保存全部")
        self._save_btn.setToolTip("保存所有修改到磁盘")
        self._save_btn.clicked.connect(self._on_save)
        self._save_btn.setEnabled(False)
        toolbar.addWidget(self._save_btn)
        layout.addLayout(toolbar)

        # Tabs
        self._tabs = QTabWidget()
        self._overview_tab = self._build_overview_tab()
        self._world_tab = WorldBibleEditorView()
        self._style_tab = self._build_style_tab()
        self._character_tab = CharacterEditorView()
        self._tabs.addTab(self._overview_tab, "概览")
        self._tabs.addTab(self._world_tab, "世界设定")
        self._tabs.addTab(self._character_tab, "角色")
        self._tabs.addTab(self._style_tab, "写作风格")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs)

    def _build_overview_tab(self) -> QWidget:
        overview = QWidget()
        layout = QVBoxLayout(overview)
        self._overview_empty = QWidget()
        empty_layout = QVBoxLayout(self._overview_empty)
        empty_layout.addWidget(QLabel("<h2>构建你的故事设定集</h2>"))
        empty_layout.addWidget(QLabel("从你已经了解的故事部分开始。你可以随时添加或隐藏设定。"))
        self._create_character_btn = QPushButton("创建角色")
        self._create_character_btn.clicked.connect(self._start_character_from_overview)
        empty_layout.addWidget(self._create_character_btn)
        self._overview_world_btn = QPushButton("添加世界设定")
        self._overview_world_btn.clicked.connect(self._start_world_from_overview)
        empty_layout.addWidget(self._overview_world_btn)
        self._set_style_btn = QPushButton("设置写作风格")
        self._set_style_btn.clicked.connect(self._start_style_from_overview)
        empty_layout.addWidget(self._set_style_btn)
        self._overview_template_btn = QPushButton("应用故事模板")
        self._overview_template_btn.clicked.connect(self._on_apply_template)
        empty_layout.addWidget(self._overview_template_btn)
        layout.addWidget(self._overview_empty)

        self._overview_summary = QWidget()
        summary_layout = QVBoxLayout(self._overview_summary)
        summary_layout.addWidget(QLabel("<h2>故事设定集概览</h2>"))
        self._overview_world_summary = QLabel()
        self._overview_character_summary = QLabel()
        self._overview_style_summary = QLabel()
        for label, button_text, target in (
            (self._overview_world_summary, "打开世界设定", "world"),
            (self._overview_character_summary, "打开角色", "characters"),
            (self._overview_style_summary, "打开写作风格", "style"),
        ):
            summary_layout.addWidget(label)
            button = QPushButton(button_text)
            button.clicked.connect(
                lambda _checked=False, tab_id=target: self._open_overview_target(tab_id)
            )
            summary_layout.addWidget(button)
        layout.addWidget(self._overview_summary)
        layout.addStretch()
        return overview

    def _start_character_from_overview(self) -> None:
        self._tabs.setCurrentWidget(self._character_tab)
        self._character_tab._on_add_character()

    def _start_world_from_overview(self) -> None:
        self._tabs.setCurrentWidget(self._world_tab)
        self._world_tab._element_list.select_element("overview")

    def _start_style_from_overview(self) -> None:
        self._tabs.setCurrentWidget(self._style_tab)
        self._pacing_slider.setFocus()

    def _open_overview_target(self, tab_id: str) -> None:
        target = {
            "world": self._world_tab,
            "characters": self._character_tab,
            "style": self._style_tab,
        }.get(tab_id)
        if target is not None:
            self._tabs.setCurrentWidget(target)

    def _restore_selected_tab(self) -> None:
        if self._layout_store is None:
            return
        tabs = {
            "overview": self._overview_tab,
            "world": self._world_tab,
            "characters": self._character_tab,
            "style": self._style_tab,
        }
        self._tabs.setCurrentWidget(
            tabs.get(self._layout_store.layout.selected_tab, self._overview_tab)
        )

    def _on_tab_changed(self) -> None:
        if self._layout_store is None or self._populating:
            return
        tab_ids = {
            self._overview_tab: "overview",
            self._world_tab: "world",
            self._character_tab: "characters",
            self._style_tab: "style",
        }
        self._layout_store.layout.selected_tab = tab_ids.get(
            self._tabs.currentWidget(), "overview"
        )
        self._layout_store.schedule_save()

    def _apply_style_layout(self) -> None:
        if self._layout_store is None:
            return
        layout = self._layout_store.layout.style
        supported = set(self._style_sections)
        unknown = set(layout.collapsed_sections) - supported
        if unknown:
            logger.warning("Ignoring unknown style layout IDs: %s", sorted(unknown))
        layout.collapsed_sections = [
            section_id
            for section_id in layout.collapsed_sections
            if section_id in supported
        ]
        collapsed = set(layout.collapsed_sections)
        for section_id, section in self._style_sections.items():
            section.set_expanded(section_id not in collapsed)

    def _on_style_expanded(self, section_id: str, expanded: bool) -> None:
        if self._layout_store is None:
            return
        collapsed = set(self._layout_store.layout.style.collapsed_sections)
        if expanded:
            collapsed.discard(section_id)
        else:
            collapsed.add(section_id)
        self._layout_store.layout.style.collapsed_sections = sorted(collapsed)
        self._layout_store.schedule_save()

    def _refresh_overview(self) -> None:
        world = self._world_tab.overview_in_memory()
        elements = self._world_tab.elements_in_memory()
        style = self._gather_style()
        characters = {
            character_id: character.core
            for character_id, character in self._character_tab._characters.items()
        }
        if self._character_tab._current_id in characters:
            characters[self._character_tab._current_id] = self._character_tab._gather_core(
                self._character_tab._current_id
            )
        empty = (
            world == WorldOverview()
            and not elements
            and style == StyleGuide()
            and not characters
        )
        self._overview_empty.setVisible(empty)
        self._overview_summary.setVisible(not empty)
        if empty:
            return

        counts = Counter(element.element_type for element in elements)
        self._overview_world_summary.setText(
            f"世界：4 个概览部分 · {len(elements)} 个元素\n"
            f"{counts[BibleElementType.FACTION]} 个势力 · "
            f"{counts[BibleElementType.LOCATION]} 个地点 · "
            f"{counts[BibleElementType.POWER_SYSTEM]} 个力量体系"
        )
        counts = {
            tier: sum(core.tier == tier for core in characters.values())
            for tier in CharacterTier
        }
        self._overview_character_summary.setText(
            f"角色：{len(characters)} 个角色 · {counts[CharacterTier.MAJOR]} 位主要角色 · "
            f"{counts[CharacterTier.SUPPORTING]} 位配角 · "
            f"{counts[CharacterTier.BACKGROUND]} 位背景角色"
        )
        style_parts = [value for value in (style.pacing, style.tone, style.pov) if value]
        self._overview_style_summary.setText(
            "写作风格：" + (" · ".join(style_parts) if style_parts else "未设置")
        )

    def _connect_dirty_tracking(self) -> None:
        self._world_tab.dirty_changed.connect(self._on_world_dirty_changed)
        self._world_tab.content_changed.connect(self._refresh_overview)
        self._world_tab.elements_changed.connect(self.elements_changed)
        self._world_tab.character_requested.connect(self._open_character)
        self._world_tab.scene_requested.connect(self.scene_requested)

        self._pacing_slider.valueChanged.connect(self._recompute_style_dirty)
        for row in (
            self._tone_combo,
            self._dialogue_combo,
            self._desc_combo,
            self._sent_combo,
            self._pov_combo,
        ):
            for index in range(row.count()):
                combo = row.itemAt(index).widget()
                if isinstance(combo, QComboBox):
                    combo.currentIndexChanged.connect(self._recompute_style_dirty)
        for editor in (self._taboo_patterns_list, self._preferred_patterns_list):
            editor.changed.connect(self._recompute_style_dirty)
        for editor in (self._ref_passages_edit, self._notes_edit):
            editor.textChanged.connect(self._recompute_style_dirty)
        self._character_tab.dirty_changed.connect(self._update_aggregate_dirty_state)
        self._character_tab.characters_changed.connect(self._refresh_overview)

    def _open_character(self, character_id: str) -> None:
        if not self._world_tab._resolve_dirty_before_switch():
            return
        self._tabs.setCurrentWidget(self._character_tab)
        self._character_tab.select_character(character_id)

    def _on_world_dirty_changed(self, dirty: bool) -> None:
        self._world_dirty = dirty
        self._update_aggregate_dirty_state()
        self._refresh_overview()

    def _recompute_style_dirty(self) -> None:
        if self._populating:
            return
        self._style_dirty = self._gather_style() != self._baseline_style
        self._update_aggregate_dirty_state()
        self._refresh_overview()

    def _update_aggregate_dirty_state(self, *_args) -> None:
        dirty = self.is_dirty
        self._unsaved_label.setVisible(dirty)
        self._save_btn.setEnabled(dirty)
        if dirty != self._last_dirty:
            self._last_dirty = dirty
            self.dirty_changed.emit(dirty)

    # ── Style Tab ──────────────────────────────────────────────────────────

    def _build_style_tab(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QVBoxLayout(container)

        pacing_label = QLabel("<b>节奏</b>")
        self._pacing_slider = QSlider(Qt.Orientation.Horizontal)
        self._pacing_slider.setRange(0, 5)
        self._pacing_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._pacing_slider.setTickInterval(1)
        pacing_display = QLabel("未设置")
        self._pacing_slider.valueChanged.connect(
            lambda v: pacing_display.setText(
                {0: "未设置", 1: "很慢", 2: "偏慢", 3: "适中", 4: "偏快", 5: "很快"}.get(v, "")
            )
        )
        pacing_row = QHBoxLayout()
        pacing_row.addWidget(pacing_label)
        pacing_row.addWidget(self._pacing_slider)
        pacing_row.addWidget(pacing_display)

        self._tone_combo = self._labeled_combo("基调:", ["", "严肃", "轻松", "热血", "黑暗"])
        self._dialogue_combo = self._labeled_combo("对白密度:", ["", "对白多", "适中", "对白少"])
        self._desc_combo = self._labeled_combo("描写风格:", ["", "简练", "细致"])
        self._sent_combo = self._labeled_combo("句长偏好:", ["", "长句多", "短句多", "混合"])
        self._pov_combo = self._labeled_combo("视角:", ["", "第三人称", "第一人称", "多视角"])
        self._taboo_patterns_list = StringListEditor()
        self._preferred_patterns_list = StringListEditor()
        self._ref_passages_edit = QTextEdit()
        self._ref_passages_edit.setPlaceholderText("粘贴参考文本段落，每段用空行分隔...")
        self._ref_passages_edit.setMaximumHeight(120)
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("任何关于写作风格的补充说明...")
        self._notes_edit.setMaximumHeight(100)

        core_content = QWidget()
        core_layout = QVBoxLayout(core_content)
        core_layout.addLayout(pacing_row)
        core_layout.addLayout(self._tone_combo)
        core_layout.addLayout(self._pov_combo)

        prose_content = QWidget()
        prose_layout = QVBoxLayout(prose_content)
        prose_layout.addLayout(self._dialogue_combo)
        prose_layout.addLayout(self._desc_combo)
        prose_layout.addLayout(self._sent_combo)

        advanced_content = QWidget()
        advanced_layout = QVBoxLayout(advanced_content)
        self._advanced_new_label = QLabel("新")
        self._advanced_new_label.setStyleSheet("color: #d48806;")
        self._advanced_new_label.setVisible(False)
        advanced_layout.addWidget(self._advanced_new_label)
        advanced_layout.addWidget(QLabel("<b>禁忌模式</b>"))
        advanced_layout.addWidget(self._taboo_patterns_list)
        advanced_layout.addWidget(QLabel("<b>偏好模式</b>"))
        advanced_layout.addWidget(self._preferred_patterns_list)
        advanced_layout.addWidget(QLabel("<b>参考段落</b>（每段一个，用于风格参照）"))
        advanced_layout.addWidget(self._ref_passages_edit)
        advanced_layout.addWidget(QLabel("<b>自由笔记</b>"))
        advanced_layout.addWidget(self._notes_edit)

        for section_id, title, content, collapsible in (
            ("core", "核心风格", core_content, False),
            ("prose", "行文偏好", prose_content, True),
            ("advanced", "高级说明", advanced_content, True),
        ):
            section = CollapsibleSection(
                title, section_id=section_id, collapsible=collapsible
            )
            section.set_content_widget(content)
            section.expanded_changed.connect(
                lambda expanded, sid=section_id: self._on_style_expanded(
                    sid, expanded
                )
            )
            self._style_sections[section_id] = section
            form.addWidget(section)

        form.addStretch()
        scroll.setWidget(container)
        return scroll

    @staticmethod
    def _labeled_combo(label: str, items: list[str]) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        combo = QComboBox()
        combo.addItems(items)
        row.addWidget(combo)
        return row

    # ── Populate ───────────────────────────────────────────────────────────

    def _populate_style_tab(self, style: StyleGuide) -> None:
        pacing_map = {"": 0, "很慢": 1, "偏慢": 2, "适中": 3, "偏快": 4, "很快": 5}
        self._pacing_slider.setValue(pacing_map.get(style.pacing, 0))
        _set_combo(self._tone_combo, style.tone)
        _set_combo(self._dialogue_combo, style.dialogue_density)
        _set_combo(self._desc_combo, style.description_style)
        _set_combo(self._sent_combo, style.sentence_length)
        _set_combo(self._pov_combo, style.pov)
        self._taboo_patterns_list.set_items(style.taboo_patterns)
        self._preferred_patterns_list.set_items(style.preferred_patterns)
        self._ref_passages_edit.setPlainText("\n\n".join(style.reference_passages))
        self._notes_edit.setPlainText(style.freeform_notes)

    # ── Gather ─────────────────────────────────────────────────────────────

    def _gather_style(self) -> StyleGuide:
        pacing_map = {0: "", 1: "很慢", 2: "偏慢", 3: "适中", 4: "偏快", 5: "很快"}
        ref_text = self._ref_passages_edit.toPlainText().strip()
        ref_passages = [p.strip() for p in ref_text.split("\n\n") if p.strip()] if ref_text else []

        return StyleGuide(
            pacing=pacing_map.get(self._pacing_slider.value(), ""),
            dialogue_density=_combo_val(self._dialogue_combo),
            description_style=_combo_val(self._desc_combo),
            tone=_combo_val(self._tone_combo),
            sentence_length=_combo_val(self._sent_combo),
            pov=_combo_val(self._pov_combo),
            taboo_patterns=self._taboo_patterns_list.get_items(),
            preferred_patterns=self._preferred_patterns_list.get_items(),
            reference_passages=ref_passages,
            freeform_notes=self._notes_edit.toPlainText().strip(),
        )

    # ── Actions ────────────────────────────────────────────────────────────

    def save_all(self) -> bool:
        if self._project_dir is None:
            return True
        if not self._world_tab.save_all():
            self._tabs.setCurrentWidget(self._world_tab)
            return False
        if self._style_dirty:
            style = self._gather_style()
            try:
                save_style_guide(self._project_dir, style)
            except Exception as error:
                QMessageBox.warning(self, "写作风格保存失败", str(error))
                return False
            self._baseline_style = style.model_copy(deep=True)
            self._style_dirty = False
            self._update_aggregate_dirty_state()
        if self._character_tab.is_dirty and not self._character_tab.save_current_character():
            return False
        self._update_aggregate_dirty_state()
        self.saved.emit()
        return True

    def _on_save(self) -> None:
        self.save_all()

    def _on_apply_template(self) -> None:
        from app.ui.template_apply_dialog import TemplateApplyDialog

        dialog = TemplateApplyDialog(self)
        if not dialog.exec() or not (dialog.apply_world or dialog.apply_style):
            return
        template = get_xianxia_template()
        before_overview = self._world_tab.overview_in_memory()
        before_elements = self._world_tab.elements_in_memory()
        before_style = self._gather_style()
        if dialog.merge_mode == TemplateMergeMode.REPLACE and dialog.apply_world:
            preview = preview_story_template_replace(before_elements, template)
            replaced = preview.elements_replaced
            unaffected = preview.unaffected_elements
            message = (
                "世界概览：\n"
                f"• {preview.overview_fields_replaced} fields replaced\n\n"
                "Elements:\n"
                f"• {replaced.get(BibleElementType.FACTION, 0)} factions replaced\n"
                f"• {replaced.get(BibleElementType.TERMINOLOGY, 0)} terminology entries replaced\n"
                f"• {replaced.get(BibleElementType.HISTORICAL_EVENT, 0)} historical event replaced\n"
                f"• {replaced.get(BibleElementType.POWER_SYSTEM, 0)} power system replaced\n\n"
                "Unaffected:\n"
                f"• {unaffected.get(BibleElementType.LOCATION, 0)} locations retained\n\n"
                "Changes are written only after Save."
            )
            reply = QMessageBox.question(
                self,
                "确认替换",
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        application = None
        if dialog.apply_world:
            try:
                application = apply_story_template(
                    before_overview,
                    before_elements,
                    before_style,
                    template,
                    dialog.merge_mode,
                )
            except ValueError as error:
                QMessageBox.warning(self, "模板应用失败", str(error))
                return
        style_after = (
            application.style_guide
            if application is not None
            else merge_style_guide(before_style, template.style_guide, dialog.merge_mode)
        )
        self._populating = True
        try:
            if dialog.apply_world:
                assert application is not None
                self._world_tab.stage_snapshot(
                    application.world_overview, application.elements
                )
            if dialog.apply_style:
                self._populate_style_tab(style_after)
        finally:
            self._populating = False
        after_style = self._gather_style()
        if dialog.apply_style:
            before_prose = any(
                (
                    before_style.dialogue_density,
                    before_style.description_style,
                    before_style.sentence_length,
                )
            )
            after_prose = any(
                (
                    after_style.dialogue_density,
                    after_style.description_style,
                    after_style.sentence_length,
                )
            )
            if after_prose and not before_prose:
                self._style_sections["prose"].set_expanded(True)
                self._on_style_expanded("prose", True)
            before_advanced = any(
                (
                    before_style.taboo_patterns,
                    before_style.preferred_patterns,
                    before_style.reference_passages,
                    before_style.freeform_notes,
                )
            )
            after_advanced = any(
                (
                    after_style.taboo_patterns,
                    after_style.preferred_patterns,
                    after_style.reference_passages,
                    after_style.freeform_notes,
                )
            )
            advanced_is_new = after_advanced and not before_advanced
            self._advanced_new_label.setVisible(advanced_is_new)
            self._style_sections["advanced"].set_summary(
                "新" if advanced_is_new else ""
            )
        if dialog.apply_style:
            self._recompute_style_dirty()
        self._refresh_overview()

