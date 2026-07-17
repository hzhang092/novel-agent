"""Novel Bible editor — tabbed world setting and style guide editor."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.storage.editor_layout import EditorLayoutStore
from app.storage.models import Project as ProjectModel
from app.storage.models import CharacterTier, PowerSystem, StyleGuide, WorldSetting
from app.storage.project_files import (
    load_project,
    save_style_guide,
    save_world_setting,
)
from app.ui.character_editor import CharacterEditorView
from app.ui.world_section_catalog import (
    WORLD_SECTION_DEFINITIONS,
    populated_world_sections,
)
from app.ui.widgets import (
    AddMenuItem,
    CollapsibleSection,
    KeyValueTable,
    SearchableAddMenu,
    StringListEditor,
    combo_val as _combo_val,
    read_table_cell,
    set_combo as _set_combo,
)
from app.utils.template_merge import (
    TemplateMergeMode,
    merge_style_guide,
    merge_world_setting,
)
from app.utils.xianxia_template import get_xianxia_template

logger = logging.getLogger(__name__)


class BibleEditorView(QWidget):
    """Tabbed editor for world setting and style guide.

    Receives the project directory path via ``load_project_dir()`` and
    handles its own persistence. Emits ``saved`` after successful writes.
    """

    saved = pyqtSignal()
    dirty_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_dir: Path | None = None
        self._baseline_world: WorldSetting | None = None
        self._baseline_style: StyleGuide | None = None
        self._world_dirty = False
        self._style_dirty = False
        self._populating = False
        self._last_dirty = False
        self._layout_store: EditorLayoutStore | None = None
        self._world_sections: dict[str, CollapsibleSection] = {}
        self._power_sections: dict[str, CollapsibleSection] = {}
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
            self._populate_world_tab(project.world_setting)
            self._populate_style_tab(project.style_guide)
            self._character_tab.load_project_dir(project_dir)
            if not had_layout:
                self._layout_store.layout.world.visible_sections = sorted(
                    populated_world_sections(project.world_setting)
                )
                self._layout_store.layout.style.collapsed_sections = ["advanced"]
                self._layout_store.schedule_save()
            self._apply_world_layout()
            self._apply_style_layout()
            self._restore_selected_tab()
        finally:
            self._populating = False
        self._baseline_world = self._gather_world()
        self._baseline_style = self._gather_style()
        self._world_dirty = False
        self._style_dirty = False
        self._update_aggregate_dirty_state()
        self._refresh_overview()

    @property
    def is_dirty(self) -> bool:
        return self._world_dirty or self._style_dirty or self._character_tab.is_dirty

    # ── UI Setup ───────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()
        self._template_btn = QPushButton("修仙模板")
        self._template_btn.setToolTip("一键填充修仙世界观和写作风格")
        self._template_btn.clicked.connect(self._on_apply_template)
        toolbar.addWidget(self._template_btn)
        toolbar.addStretch()
        self._unsaved_label = QLabel("未保存")
        self._unsaved_label.setStyleSheet("color: #d48806;")
        self._unsaved_label.setVisible(False)
        toolbar.addWidget(self._unsaved_label)
        self._save_btn = QPushButton("保存")
        self._save_btn.setToolTip("保存所有修改到磁盘")
        self._save_btn.clicked.connect(self._on_save)
        self._save_btn.setEnabled(False)
        toolbar.addWidget(self._save_btn)
        layout.addLayout(toolbar)

        # Tabs
        self._tabs = QTabWidget()
        self._overview_tab = self._build_overview_tab()
        self._world_tab = self._build_world_tab()
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
        self._open_world_menu()

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
        world = self._gather_world()
        style = self._gather_style()
        characters = {
            character_id: character.core
            for character_id, character in self._character_tab._characters.items()
        }
        if self._character_tab._current_id in characters:
            characters[self._character_tab._current_id] = self._character_tab._gather_core(
                self._character_tab._current_id
            )
        empty = world == WorldSetting() and style == StyleGuide() and not characters
        self._overview_empty.setVisible(empty)
        self._overview_summary.setVisible(not empty)
        if empty:
            return

        populated_world = populated_world_sections(world)
        visible_world = (
            set(self._layout_store.layout.world.visible_sections)
            if self._layout_store is not None
            else set()
        )
        self._overview_world_summary.setText(
            f"世界：{len(visible_world)} 个已显示设定 · "
            f"{len(populated_world - visible_world)} 个含内容的隐藏设定"
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
        for editor in (self._geo_edit, self._history_edit):
            editor.textChanged.connect(self._recompute_world_dirty)
        for editor in (self._tech_edit, self._social_edit):
            editor.textChanged.connect(self._recompute_world_dirty)
        for editor in (
            self._rules_list,
            self._taboos_list,
            self._realms_list,
            self._limitations_list,
            self._costs_list,
            self._resources_list,
            self._forbidden_list,
            self._factions_table,
            self._term_table,
            self._abilities_table,
        ):
            editor.changed.connect(self._recompute_world_dirty)

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

    def _recompute_world_dirty(self) -> None:
        if self._populating:
            return
        self._world_dirty = self._gather_world() != self._baseline_world
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

    # ── World Tab ──────────────────────────────────────────────────────────

    def _build_world_tab(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QVBoxLayout(container)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("<h2>世界设定</h2>"))
        toolbar.addStretch()
        self._add_world_btn = QPushButton("+ 添加设定")
        self._add_world_btn.clicked.connect(self._open_world_menu)
        toolbar.addWidget(self._add_world_btn)
        form.addLayout(toolbar)

        self._world_empty_state = QWidget()
        empty_layout = QVBoxLayout(self._world_empty_state)
        empty_layout.addWidget(QLabel("<h3>按故事需要构建世界</h3>"))
        empty_layout.addWidget(QLabel("只添加当前需要的部分，以后可以继续补充。"))
        for label, section_id in (
            ("添加地理", "geography"),
            ("添加势力", "factions"),
            ("添加力量体系", "power_system"),
        ):
            button = QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, sid=section_id: self._on_add_world_section(sid)
            )
            empty_layout.addWidget(button)
        browse = QPushButton("浏览全部设定")
        browse.clicked.connect(self._open_world_menu)
        empty_layout.addWidget(browse)
        form.addWidget(self._world_empty_state)

        self._geo_edit = QTextEdit()
        self._geo_edit.setPlaceholderText("描述世界观的地理环境...")
        self._geo_edit.setMaximumHeight(100)
        self._history_edit = QTextEdit()
        self._history_edit.setPlaceholderText("世界观的历史背景...")
        self._history_edit.setMaximumHeight(80)
        self._tech_edit = QLineEdit()
        self._tech_edit.setPlaceholderText("如：修仙文明")
        self._social_edit = QLineEdit()
        self._social_edit.setPlaceholderText("如：宗门制，强者为尊")
        self._rules_list = StringListEditor()
        self._taboos_list = StringListEditor()
        self._factions_table = KeyValueTable(["势力名称", "描述", "目标"])
        self._term_table = KeyValueTable(["术语", "定义"])
        self._realms_list = StringListEditor()
        self._abilities_table = KeyValueTable(["境界", "能力描述"])
        self._limitations_list = StringListEditor()
        self._costs_list = StringListEditor()
        self._resources_list = StringListEditor()
        self._forbidden_list = StringListEditor()

        section_content: dict[str, QWidget] = {}
        for section_id in (
            "geography", "history", "society", "rules", "taboos",
            "factions", "terminology", "power_system",
        ):
            content = QWidget()
            section_content[section_id] = content
            content.setLayout(QVBoxLayout())
        section_content["geography"].layout().addWidget(self._geo_edit)
        section_content["history"].layout().addWidget(self._history_edit)
        section_content["society"].layout().addWidget(QLabel("科技水平"))
        section_content["society"].layout().addWidget(self._tech_edit)
        section_content["society"].layout().addWidget(QLabel("社会结构"))
        section_content["society"].layout().addWidget(self._social_edit)
        section_content["rules"].layout().addWidget(self._rules_list)
        section_content["taboos"].layout().addWidget(self._taboos_list)
        section_content["factions"].layout().addWidget(self._factions_table)
        section_content["terminology"].layout().addWidget(self._term_table)

        for title, section_id, widgets in (
            ("境界与能力", "realms", (self._realms_list, self._abilities_table)),
            ("限制与代价", "costs", (self._limitations_list, self._costs_list)),
            ("稀有资源与禁忌之术", "rare", (self._resources_list, self._forbidden_list)),
        ):
            nested_id = f"power_{section_id}"
            nested = CollapsibleSection(title, section_id=nested_id)
            nested_content = QWidget()
            nested_layout = QVBoxLayout(nested_content)
            for widget in widgets:
                nested_layout.addWidget(widget)
            nested.set_content_widget(nested_content)
            nested.expanded_changed.connect(
                lambda expanded, sid=nested_id: self._on_world_expanded(sid, expanded)
            )
            self._power_sections[nested_id] = nested
            section_content["power_system"].layout().addWidget(nested)

        labels = {
            "geography": "地理",
            "history": "历史",
            "society": "社会与科技",
            "rules": "世界规则",
            "taboos": "禁忌",
            "factions": "势力",
            "terminology": "术语",
            "power_system": "力量 / 修炼体系",
        }
        for definition in WORLD_SECTION_DEFINITIONS:
            section = CollapsibleSection(
                labels[definition.section_id],
                section_id=definition.section_id,
                hideable=True,
            )
            section.set_content_widget(section_content[definition.section_id])
            section.hide_requested.connect(
                lambda sid=definition.section_id: self._on_hide_world_section(sid)
            )
            section.expanded_changed.connect(
                lambda expanded, sid=definition.section_id: self._on_world_expanded(
                    sid, expanded
                )
            )
            self._world_sections[definition.section_id] = section
            form.addWidget(section)

        self._world_add_menu = SearchableAddMenu(self)
        self._world_add_menu.item_selected.connect(self._on_add_world_section)
        form.addStretch()

        scroll.setWidget(container)
        return scroll

    def _apply_world_layout(self) -> None:
        if self._layout_store is None:
            return
        layout = self._layout_store.layout.world
        supported_visible = set(self._world_sections)
        supported_collapsed = supported_visible | set(self._power_sections)
        unknown = (
            set(layout.visible_sections) - supported_visible
        ) | (set(layout.collapsed_sections) - supported_collapsed)
        if unknown:
            logger.warning("Ignoring unknown world layout IDs: %s", sorted(unknown))
        layout.visible_sections = [
            section_id
            for section_id in layout.visible_sections
            if section_id in supported_visible
        ]
        layout.collapsed_sections = [
            section_id
            for section_id in layout.collapsed_sections
            if section_id in supported_collapsed
        ]
        visible = set(layout.visible_sections)
        for section_id, section in self._world_sections.items():
            section.setVisible(section_id in visible)
            section.set_expanded(section_id not in layout.collapsed_sections)
        for section_id, section in self._power_sections.items():
            section.set_expanded(section_id not in layout.collapsed_sections)
        self._world_empty_state.setVisible(not visible)

    def _open_world_menu(self) -> None:
        if self._layout_store is None:
            return
        categories = {
            "geography": "环境",
            "history": "环境",
            "society": "环境",
            "rules": "规则与体系",
            "taboos": "规则与体系",
            "power_system": "规则与体系",
            "factions": "人物与语言",
            "terminology": "人物与语言",
        }
        self._world_add_menu.set_items(
            [
                AddMenuItem(
                    item.section_id,
                    item.label,
                    categories[item.section_id],
                    item.description,
                    item.keywords,
                )
                for item in WORLD_SECTION_DEFINITIONS
            ],
            visible_ids=set(self._layout_store.layout.world.visible_sections),
            populated_ids=populated_world_sections(self._gather_world()),
        )
        self._world_add_menu.open_below(self._add_world_btn)

    def _on_add_world_section(self, section_id: str) -> None:
        if self._layout_store is None or section_id not in self._world_sections:
            return
        layout = self._layout_store.layout.world
        layout.visible_sections = sorted(
            set(layout.visible_sections) | {section_id}
        )
        collapsed = set(layout.collapsed_sections)
        collapsed.discard(section_id)
        layout.collapsed_sections = sorted(collapsed)
        section = self._world_sections[section_id]
        section.setVisible(True)
        section.set_expanded(True)
        self._world_empty_state.setVisible(False)
        self._layout_store.schedule_save()
        self._refresh_overview()

    def _on_hide_world_section(self, section_id: str) -> None:
        if self._layout_store is None or section_id not in self._world_sections:
            return
        layout = self._layout_store.layout.world
        layout.visible_sections = sorted(
            set(layout.visible_sections) - {section_id}
        )
        self._world_sections[section_id].setVisible(False)
        self._world_empty_state.setVisible(not layout.visible_sections)
        self._layout_store.schedule_save()
        self._refresh_overview()

    def _on_world_expanded(self, section_id: str, expanded: bool) -> None:
        if self._layout_store is None:
            return
        collapsed = set(self._layout_store.layout.world.collapsed_sections)
        if expanded:
            collapsed.discard(section_id)
        else:
            collapsed.add(section_id)
        self._layout_store.layout.world.collapsed_sections = sorted(collapsed)
        self._layout_store.schedule_save()

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

    def _populate_world_tab(self, world: WorldSetting) -> None:
        self._geo_edit.setPlainText(world.geography)
        self._history_edit.setPlainText(world.history)
        self._tech_edit.setText(world.technology_level)
        self._social_edit.setText(world.social_structure)
        self._rules_list.set_items(world.rules)
        self._taboos_list.set_items(world.taboos)
        self._factions_table.set_rows(
            [["", "", ""]] if not world.factions
            else [[f.get("name", ""), f.get("description", ""), f.get("goals", "")]
                  for f in world.factions]
        )
        self._term_table.set_rows(
            [[k, v] for k, v in world.terminology.items()]
        )
        ps = world.power_system or PowerSystem()
        self._realms_list.set_items(ps.realms)
        self._abilities_table.set_rows([[k, v] for k, v in ps.abilities.items()])
        self._limitations_list.set_items(ps.limitations)
        self._costs_list.set_items(ps.costs)
        self._resources_list.set_items(ps.rare_resources)
        self._forbidden_list.set_items(ps.forbidden_methods)

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

    def _gather_world(self) -> WorldSetting:
        factions = []
        for row in range(self._factions_table.rowCount()):
            name = _cell(self._factions_table._table, row, 0)
            desc = _cell(self._factions_table._table, row, 1)
            goals = _cell(self._factions_table._table, row, 2)
            if name or desc or goals:
                factions.append({"name": name, "description": desc, "goals": goals})

        terminology = {}
        for row in range(self._term_table.rowCount()):
            term = _cell(self._term_table._table, row, 0)
            defn = _cell(self._term_table._table, row, 1)
            if term:
                terminology[term] = defn

        abilities = {}
        for row in range(self._abilities_table.rowCount()):
            realm = _cell(self._abilities_table._table, row, 0)
            desc = _cell(self._abilities_table._table, row, 1)
            if realm:
                abilities[realm] = desc

        power_system = PowerSystem(
            realms=self._realms_list.get_items(),
            abilities=abilities,
            limitations=self._limitations_list.get_items(),
            costs=self._costs_list.get_items(),
            rare_resources=self._resources_list.get_items(),
            forbidden_methods=self._forbidden_list.get_items(),
        )
        return WorldSetting(
            geography=self._geo_edit.toPlainText().strip(),
            power_system=power_system if any(power_system.model_dump().values()) else None,
            factions=factions,
            history=self._history_edit.toPlainText().strip(),
            rules=self._rules_list.get_items(),
            taboos=self._taboos_list.get_items(),
            technology_level=self._tech_edit.text().strip(),
            social_structure=self._social_edit.text().strip(),
            terminology=terminology,
        )

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
        if self._world_dirty:
            world = self._gather_world()
            try:
                save_world_setting(self._project_dir, world)
            except Exception as error:
                QMessageBox.warning(self, "世界设定保存失败", str(error))
                return False
            self._baseline_world = world.model_copy(deep=True)
            self._world_dirty = False
            self._update_aggregate_dirty_state()
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
        if dialog.merge_mode == TemplateMergeMode.REPLACE:
            reply = QMessageBox.question(
                self,
                "确认替换",
                "替换会覆盖所选范围中的现有内容，但只有在点击“保存”后才会写入磁盘。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        before_world = self._gather_world()
        before_style = self._gather_style()
        template_world, template_style = get_xianxia_template()
        self._populating = True
        try:
            if dialog.apply_world:
                self._populate_world_tab(
                    merge_world_setting(
                        self._gather_world(), template_world, dialog.merge_mode
                    )
                )
            if dialog.apply_style:
                self._populate_style_tab(
                    merge_style_guide(
                        self._gather_style(), template_style, dialog.merge_mode
                    )
                )
        finally:
            self._populating = False
        after_world = self._gather_world()
        after_style = self._gather_style()
        if dialog.apply_world:
            for section_id in (
                populated_world_sections(after_world)
                - populated_world_sections(before_world)
            ):
                self._on_add_world_section(section_id)
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
        if dialog.apply_world:
            self._recompute_world_dirty()
        if dialog.apply_style:
            self._recompute_style_dirty()


# ── Helpers ────────────────────────────────────────────────────────────────

def _cell(table, row: int, col: int) -> str:
    """Read a table cell — delegates to shared widget helper."""
    return read_table_cell(table, row, col)

