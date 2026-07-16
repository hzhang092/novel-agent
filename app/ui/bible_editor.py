"""Novel Bible editor — tabbed world setting and style guide editor."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
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

from app.storage.models import Project as ProjectModel
from app.storage.models import PowerSystem, StyleGuide, WorldSetting
from app.storage.project_files import (
    load_project,
    save_style_guide,
    save_world_setting,
)
from app.ui.character_editor import CharacterEditorView
from app.ui.widgets import KeyValueTable, StringListEditor, read_table_cell, set_combo as _set_combo, combo_val as _combo_val
from app.utils.template_merge import (
    TemplateMergeMode,
    merge_style_guide,
    merge_world_setting,
)
from app.utils.xianxia_template import get_xianxia_template


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
        self._setup_ui()
        self._connect_dirty_tracking()

    # ── Public API ─────────────────────────────────────────────────────────

    def load_project_dir(self, project_dir: Path) -> None:
        """Load project data from disk and populate the editor."""
        self._project_dir = project_dir
        project = load_project(project_dir)
        self._populating = True
        try:
            self._populate_world_tab(project.world_setting)
            self._populate_style_tab(project.style_guide)
            self._character_tab.load_project_dir(project_dir)
        finally:
            self._populating = False
        self._baseline_world = self._gather_world()
        self._baseline_style = self._gather_style()
        self._world_dirty = False
        self._style_dirty = False
        self._update_aggregate_dirty_state()

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
        self._world_tab = self._build_world_tab()
        self._style_tab = self._build_style_tab()
        self._character_tab = CharacterEditorView()
        self._tabs.addTab(self._world_tab, "世界设定")
        self._tabs.addTab(self._style_tab, "写作风格")
        self._tabs.addTab(self._character_tab, "角色")
        layout.addWidget(self._tabs)

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

    def _recompute_world_dirty(self) -> None:
        if self._populating:
            return
        self._world_dirty = self._gather_world() != self._baseline_world
        self._update_aggregate_dirty_state()

    def _recompute_style_dirty(self) -> None:
        if self._populating:
            return
        self._style_dirty = self._gather_style() != self._baseline_style
        self._update_aggregate_dirty_state()

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

        # Geography
        form.addWidget(QLabel("<b>地理</b>"))
        self._geo_edit = QTextEdit()
        self._geo_edit.setPlaceholderText("描述世界观的地理环境...")
        self._geo_edit.setMaximumHeight(100)
        form.addWidget(self._geo_edit)

        # History
        form.addWidget(QLabel("<b>历史</b>"))
        self._history_edit = QTextEdit()
        self._history_edit.setPlaceholderText("世界观的历史背景...")
        self._history_edit.setMaximumHeight(80)
        form.addWidget(self._history_edit)

        # Technology & Social
        row = QHBoxLayout()
        row.addWidget(QLabel("科技水平:"))
        self._tech_edit = QLineEdit()
        self._tech_edit.setPlaceholderText("如：修仙文明")
        row.addWidget(self._tech_edit)
        row.addWidget(QLabel("社会结构:"))
        self._social_edit = QLineEdit()
        self._social_edit.setPlaceholderText("如：宗门制，强者为尊")
        row.addWidget(self._social_edit)
        form.addLayout(row)

        # Rules
        form.addWidget(QLabel("<b>规则</b>"))
        self._rules_list = StringListEditor()
        form.addWidget(self._rules_list)

        # Taboos
        form.addWidget(QLabel("<b>禁忌</b>"))
        self._taboos_list = StringListEditor()
        form.addWidget(self._taboos_list)

        # Factions
        form.addWidget(QLabel("<b>势力</b>"))
        self._factions_table = KeyValueTable(["势力名称", "描述", "目标"])
        form.addWidget(self._factions_table)

        # Terminology
        form.addWidget(QLabel("<b>术语表</b>"))
        self._term_table = KeyValueTable(["术语", "定义"])
        form.addWidget(self._term_table)

        # Power System
        ps_group = QGroupBox("修炼体系")
        ps_layout = QVBoxLayout(ps_group)

        ps_layout.addWidget(QLabel("<b>境界</b>"))
        self._realms_list = StringListEditor()
        ps_layout.addWidget(self._realms_list)

        ps_layout.addWidget(QLabel("<b>能力</b>（境界 → 能力描述）"))
        self._abilities_table = KeyValueTable(["境界", "能力描述"])
        ps_layout.addWidget(self._abilities_table)

        ps_layout.addWidget(QLabel("<b>限制</b>"))
        self._limitations_list = StringListEditor()
        ps_layout.addWidget(self._limitations_list)

        ps_layout.addWidget(QLabel("<b>代价</b>"))
        self._costs_list = StringListEditor()
        ps_layout.addWidget(self._costs_list)

        ps_layout.addWidget(QLabel("<b>稀有资源</b>"))
        self._resources_list = StringListEditor()
        ps_layout.addWidget(self._resources_list)

        ps_layout.addWidget(QLabel("<b>禁忌之术</b>"))
        self._forbidden_list = StringListEditor()
        ps_layout.addWidget(self._forbidden_list)

        form.addWidget(ps_group)
        form.addStretch()

        scroll.setWidget(container)
        return scroll

    # ── Style Tab ──────────────────────────────────────────────────────────

    def _build_style_tab(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QVBoxLayout(container)

        # Trait pickers
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
        form.addLayout(pacing_row)

        self._tone_combo = self._labeled_combo("基调:", ["", "严肃", "轻松", "热血", "黑暗"])
        form.addLayout(self._tone_combo)

        self._dialogue_combo = self._labeled_combo("对白密度:", ["", "对白多", "适中", "对白少"])
        form.addLayout(self._dialogue_combo)

        self._desc_combo = self._labeled_combo("描写风格:", ["", "简练", "细致"])
        form.addLayout(self._desc_combo)

        self._sent_combo = self._labeled_combo("句长偏好:", ["", "长句多", "短句多", "混合"])
        form.addLayout(self._sent_combo)

        self._pov_combo = self._labeled_combo("视角:", ["", "第三人称", "第一人称", "多视角"])
        form.addLayout(self._pov_combo)

        # Pattern lists
        form.addWidget(QLabel("<b>禁忌模式</b>"))
        self._taboo_patterns_list = StringListEditor()
        form.addWidget(self._taboo_patterns_list)

        form.addWidget(QLabel("<b>偏好模式</b>"))
        self._preferred_patterns_list = StringListEditor()
        form.addWidget(self._preferred_patterns_list)

        # Reference passages
        form.addWidget(QLabel("<b>参考段落</b>（每段一个，用于风格参照）"))
        self._ref_passages_edit = QTextEdit()
        self._ref_passages_edit.setPlaceholderText("粘贴参考文本段落，每段用空行分隔...")
        self._ref_passages_edit.setMaximumHeight(120)
        form.addWidget(self._ref_passages_edit)

        # Freeform notes
        form.addWidget(QLabel("<b>自由笔记</b>"))
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("任何关于写作风格的补充说明...")
        self._notes_edit.setMaximumHeight(100)
        form.addWidget(self._notes_edit)

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
        if dialog.apply_world:
            self._recompute_world_dirty()
        if dialog.apply_style:
            self._recompute_style_dirty()


# ── Helpers ────────────────────────────────────────────────────────────────

def _cell(table, row: int, col: int) -> str:
    """Read a table cell — delegates to shared widget helper."""
    return read_table_cell(table, row, col)

