"""Character editor widget — list + detail with Core/State tabs."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.storage.character_events import get_latest_event_id
from app.storage.bible_repository import BibleElementRepository
from app.domain.story_usage import ElementUsageSummary, StoryUsageService
from app.storage.editor_layout import CharacterEditorLayout, EditorLayoutStore
from app.storage.models import Character, CharacterCore, CharacterCustomFieldType, CharacterState, CharacterTier
from app.storage.project_files import (
    delete_character,
    list_character_ids,
    load_character,
    save_character,
    save_character_definition,
)
from app.storage.state_repository import commit_character_state_edit
from app.ui.character_detail_catalog import (
    CHARACTER_DETAIL_DEFINITIONS,
    default_character_fields,
    initial_character_fields,
    populated_character_fields,
)
from app.ui.display_labels import character_tier_label
from app.ui.story_usage_panel import StoryUsagePanel
from app.ui.widgets import (
    AddMenuItem,
    CollapsibleSection,
    DetailFieldContainer,
    KeyValueTable,
    SearchableAddMenu,
    StringListEditor,
    read_table_cell,
)
from app.ui.widgets.character_element_relation_editor import CharacterElementRelationEditor
from app.ui.widgets.custom_character_field_editor import CustomCharacterFieldEditor

logger = logging.getLogger(__name__)

TIER_COLORS = {
    CharacterTier.MAJOR: QColor("#e74c3c"),
    CharacterTier.SUPPORTING: QColor("#f39c12"),
    CharacterTier.BACKGROUND: QColor("#95a5a6"),
}


class CharacterEditorView(QWidget):
    """Character card editor with character list and Core/State detail tabs.

    Receives the project directory path via ``load_project_dir()`` and
    handles its own persistence. Emits ``saved`` after successful writes.
    """

    saved = pyqtSignal()
    dirty_changed = pyqtSignal(bool)
    characters_changed = pyqtSignal()
    scene_requested = pyqtSignal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        layout_store: EditorLayoutStore | None = None,
    ) -> None:
        super().__init__(parent)
        self._project_dir: Path | None = None
        self._characters: dict[str, Character] = {}  # id -> Character
        self._current_id: str | None = None
        self._current_scene_id: str = ""
        self._bus = None
        self._baseline_core: CharacterCore | None = None
        self._core_dirty = False
        self._populating = False
        self._persisted_character_ids: set[str] = set()
        self._selection_change_in_progress = False
        self._layout_store = layout_store
        self._current_layout: CharacterEditorLayout | None = None
        self._detail_fields: dict[str, DetailFieldContainer] = {}
        self._detail_sections: dict[str, CollapsibleSection] = {}
        self._setup_ui()
        self._connect_definition_changes()

    # ── Public API ─────────────────────────────────────────────────────────

    def load_project_dir(self, project_dir: Path) -> None:
        """Load all characters from disk and populate the list."""
        self._project_dir = project_dir
        if self._layout_store is None or self._layout_store.project_dir != project_dir:
            self._layout_store = EditorLayoutStore(project_dir)
        for layout in self._layout_store.layout.characters.values():
            self._sanitize_character_layout(layout)
        self._refresh_character_list()
        self._persisted_character_ids = set(self._characters)
        for character_id, character in self._characters.items():
            if character_id not in self._layout_store.layout.characters:
                self._layout_store.layout.characters[character_id] = CharacterEditorLayout(
                    visible_fields=sorted(initial_character_fields(character.core)),
                    initialized_for_tier=character.core.tier.value,
                )
                self._layout_store.schedule_save()
        if self._characters:
            first_id = next(iter(self._characters))
            self._list.setCurrentRow(0)
            self._select_character(first_id)
        else:
            self._clear_detail()

    def set_layout_store(self, layout_store: EditorLayoutStore) -> None:
        self._layout_store = layout_store

    def select_character(self, character_id: str) -> bool:
        """Select a loaded character for cross-editor navigation."""
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item and item.data(Qt.ItemDataRole.UserRole) == character_id:
                self._list.setCurrentRow(row)
                return True
        return False

    @property
    def is_dirty(self) -> bool:
        return self._core_dirty

    def set_event_bus(self, bus) -> None:
        """Subscribe to domain events for live state refresh."""
        if self._bus is not None:
            return  # already subscribed
        self._bus = bus
        bus.subscribe("character_state_updated", self._on_state_updated)

    def set_current_scene_id(self, scene_id: str) -> None:
        """Set the current scene ID for history filtering."""
        self._current_scene_id = scene_id

    def _on_state_updated(self, character_id: str, event_id: int) -> None:
        """Reload character state from disk when a domain event fires."""
        if character_id == self._current_id and self._project_dir is not None:
            self._reload_state_tab()
            # Refresh history tab
            char_dir = self._project_dir / "characters" / character_id
            if char_dir.exists():
                self._history_tab.set_character(char_dir, self._current_scene_id)

    # ── UI Setup ───────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()
        self._add_btn = QPushButton("添加角色")
        self._add_btn.setToolTip("创建一个新角色")
        self._add_btn.clicked.connect(self._on_add_character)
        toolbar.addWidget(self._add_btn)

        self._delete_btn = QPushButton("删除")
        self._delete_btn.setToolTip("删除选中的角色")
        self._delete_btn.clicked.connect(self._on_delete_character)
        toolbar.addWidget(self._delete_btn)

        toolbar.addStretch()

        self._unsaved_label = QLabel("未保存")
        self._unsaved_label.setStyleSheet("color: #d48806;")
        self._unsaved_label.setVisible(False)
        toolbar.addWidget(self._unsaved_label)

        self._save_btn = QPushButton("保存")
        self._save_btn.setToolTip("保存当前角色修改到磁盘")
        self._save_btn.clicked.connect(self._on_save)
        self._save_btn.setEnabled(False)
        toolbar.addWidget(self._save_btn)
        layout.addLayout(toolbar)

        # Splitter: list | detail
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Character list
        list_container = QWidget()
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.addWidget(QLabel("<b>角色列表</b>"))
        self._list = QListWidget()
        self._list.setMaximumWidth(200)
        self._list.currentItemChanged.connect(self._on_list_selection_changed)
        list_layout.addWidget(self._list)
        splitter.addWidget(list_container)

        # Detail area (tabs: Core / State)
        self._detail_tabs = QTabWidget()
        self._definition_tab = self._build_core_tab()
        self._state_tab = self._build_state_tab()
        from app.ui.widgets.character_history import CharacterHistoryWidget
        self._history_tab = CharacterHistoryWidget()
        self._detail_tabs.addTab(self._definition_tab, "基本设定")
        self._detail_tabs.addTab(self._state_tab, "当前状态")
        self._detail_tabs.addTab(self._history_tab, "变化历史")
        splitter.addWidget(self._detail_tabs)
        self._detail_tabs.setVisible(False)  # hidden until a character is selected

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

    def _connect_definition_changes(self) -> None:
        for editor in (
            self._core_name,
            self._core_identity,
            self._core_age,
            self._core_goal,
            self._core_motive,
            self._core_speech,
        ):
            editor.textChanged.connect(self._recompute_core_dirty)
        for editor in (
            self._core_appearance,
            self._core_personality,
            self._core_background,
        ):
            editor.textChanged.connect(self._recompute_core_dirty)
        self._core_tier.currentIndexChanged.connect(self._recompute_core_dirty)
        self._core_tier.currentIndexChanged.connect(self._on_tier_changed)
        for editor in (
            self._core_aliases,
            self._core_skills,
            self._core_weaknesses,
        ):
            editor.changed.connect(self._recompute_core_dirty)
        self._custom_fields.changed.connect(self._recompute_core_dirty)
        self._custom_fields.visibility_changed.connect(self._on_custom_field_visibility)
        self._element_relations.changed.connect(self._recompute_core_dirty)

    # ── Core Tab ───────────────────────────────────────────────────────────

    def _build_core_tab(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QVBoxLayout(container)

        essentials = QGroupBox("基本信息")
        essentials_layout = QVBoxLayout(essentials)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("姓名:"))
        self._core_name = QLineEdit()
        self._core_name.setPlaceholderText("角色姓名（必填）")
        row1.addWidget(self._core_name)
        row1.addWidget(QLabel("定位:"))
        self._core_tier = QComboBox()
        for tier in CharacterTier:
            self._core_tier.addItem(character_tier_label(tier), tier)
        row1.addWidget(self._core_tier)
        essentials_layout.addLayout(row1)
        essentials_layout.addWidget(QLabel("<b>身份</b>"))
        self._core_identity = QLineEdit()
        self._core_identity.setPlaceholderText("如：落云宗外门弟子")
        essentials_layout.addWidget(self._core_identity)
        self._tier_suggestion = QLabel()
        self._tier_suggestion.setVisible(False)
        essentials_layout.addWidget(self._tier_suggestion)
        self._recommended_btn = QPushButton("显示推荐字段")
        self._recommended_btn.setVisible(False)
        self._recommended_btn.clicked.connect(self._show_recommended_fields)
        essentials_layout.addWidget(self._recommended_btn)
        form.addWidget(essentials)

        self._custom_section = CollapsibleSection("自定义详情", section_id="custom_fields")
        custom_content = QWidget()
        custom_layout = QVBoxLayout(custom_content)
        self._custom_fields = CustomCharacterFieldEditor()
        custom_layout.addWidget(self._custom_fields)
        self._custom_section.set_content_widget(custom_content)
        self._custom_section.expanded_changed.connect(self._on_custom_section_expanded)
        form.addWidget(self._custom_section)

        self._connection_section = QGroupBox("故事连接")
        connection_layout = QVBoxLayout(self._connection_section)
        self._element_relations = CharacterElementRelationEditor()
        connection_layout.addWidget(self._element_relations)
        form.addWidget(self._connection_section)

        # Create every existing editor once; presentation controls only visibility.
        self._core_aliases = StringListEditor()
        self._core_age = QLineEdit()
        self._core_age.setPlaceholderText("如：17")
        self._core_appearance = QTextEdit()
        self._core_appearance.setPlaceholderText("描述角色外貌特征...")
        self._core_appearance.setMaximumHeight(80)
        self._core_personality = QTextEdit()
        self._core_personality.setPlaceholderText("描述角色性格...")
        self._core_personality.setMaximumHeight(80)
        self._core_background = QTextEdit()
        self._core_background.setPlaceholderText("角色背景故事...")
        self._core_background.setMaximumHeight(100)
        self._core_goal = QLineEdit()
        self._core_goal.setPlaceholderText("角色最终追求的目标")
        self._core_motive = QLineEdit()
        self._core_motive.setPlaceholderText("不为人知的深层动机")
        self._core_speech = QLineEdit()
        self._core_speech.setPlaceholderText("如：沉稳少言、活泼多话")
        self._core_skills = StringListEditor()
        self._core_weaknesses = StringListEditor()

        section_titles = {
            "characterization": "角色塑造",
            "motivation_history": "动机与经历",
            "identity_details": "身份细节",
            "capabilities": "能力",
        }
        for section_id, title in section_titles.items():
            section = CollapsibleSection(title, section_id=section_id)
            content = QWidget()
            content_layout = QVBoxLayout(content)
            for definition in CHARACTER_DETAIL_DEFINITIONS:
                if definition.section_id != section_id:
                    continue
                detail = DetailFieldContainer(
                    definition.field_id,
                    definition.label,
                    getattr(self, definition.widget_attribute),
                )
                detail.hide_requested.connect(self._on_hide_detail)
                self._detail_fields[definition.field_id] = detail
                content_layout.addWidget(detail)
            section.set_content_widget(content)
            section.expanded_changed.connect(
                lambda expanded, sid=section_id: self._on_section_expanded(
                    sid, expanded
                )
            )
            self._detail_sections[section_id] = section
            form.addWidget(section)

        self._add_detail_btn = QPushButton("+ 添加详情")
        self._add_detail_menu = SearchableAddMenu(self)
        self._add_detail_menu.item_selected.connect(self._on_add_detail)
        self._add_detail_btn.clicked.connect(self._open_add_detail_menu)
        form.addWidget(self._add_detail_btn)
        self._reset_fields_btn = QPushButton("按角色重要性重置可见字段")
        self._reset_fields_btn.clicked.connect(self._reset_visible_fields)
        form.addWidget(self._reset_fields_btn)
        self._layout_notice = QLabel()
        self._layout_notice.setStyleSheet("color: #777;")
        form.addWidget(self._layout_notice)

        form.addStretch()
        scroll.setWidget(container)
        return scroll

    def _open_add_detail_menu(self) -> None:
        visible = set(self._current_layout.visible_fields) if self._current_layout else set()
        populated = (
            populated_character_fields(self._gather_core(self._current_id))
            if self._current_id
            else set()
        )
        category_labels = {
            "characterization": "角色塑造",
            "motivation_history": "动机与经历",
            "identity_details": "身份细节",
            "capabilities": "能力",
        }
        self._add_detail_menu.set_items(
            [
                AddMenuItem(
                    definition.field_id,
                    definition.label,
                    category_labels[definition.section_id],
                    definition.description,
                    definition.keywords,
                )
                for definition in CHARACTER_DETAIL_DEFINITIONS
            ] + [
                AddMenuItem(
                    "__create_custom__", "+ Create custom detail", "Custom",
                    "Author-defined detail field", ("custom", "detail"),
                )
            ],
            visible_ids=visible,
            populated_ids=populated,
        )
        self._add_detail_menu.open_below(self._add_detail_btn)

    def _sanitize_character_layout(self, layout: CharacterEditorLayout) -> None:
        supported_fields = set(self._detail_fields)
        supported_sections = set(self._detail_sections)
        unknown = (
            set(layout.visible_fields) - supported_fields
        ) | (set(layout.collapsed_sections) - supported_sections)
        if unknown:
            logger.warning("Ignoring unknown character layout IDs: %s", sorted(unknown))
        layout.visible_fields = [
            field_id for field_id in layout.visible_fields if field_id in supported_fields
        ]
        layout.collapsed_sections = [
            section_id
            for section_id in layout.collapsed_sections
            if section_id in supported_sections
        ]
        known_custom_ids = {
            field.id
            for character in self._characters.values()
            for field in character.core.custom_fields
        }
        unknown_custom_ids = set(layout.hidden_custom_field_ids) - known_custom_ids
        if unknown_custom_ids:
            logger.warning(
                "Ignoring unknown hidden custom field IDs: %s",
                sorted(unknown_custom_ids),
            )
        layout.hidden_custom_field_ids = [
            field_id for field_id in layout.hidden_custom_field_ids if field_id in known_custom_ids
        ]

    def _apply_character_layout(self, layout: CharacterEditorLayout) -> None:
        self._sanitize_character_layout(layout)
        self._current_layout = layout
        visible = set(layout.visible_fields)
        for field_id, detail in self._detail_fields.items():
            detail.setVisible(field_id in visible)
        for section_id, section in self._detail_sections.items():
            section.set_expanded(section_id not in layout.collapsed_sections)
        self._custom_section.set_expanded(not layout.custom_section_collapsed)
        self._custom_fields.set_hidden_ids(layout.hidden_custom_field_ids)
        self._recompute_section_visibility()
        self._layout_notice.clear()

    def _on_custom_section_expanded(self, expanded: bool) -> None:
        if self._current_layout is None:
            return
        self._current_layout.custom_section_collapsed = not expanded
        if self._layout_store is not None:
            self._layout_store.schedule_save()

    def _on_custom_field_visibility(self) -> None:
        if self._current_layout is None:
            return
        self._current_layout.hidden_custom_field_ids = self._custom_fields.hidden_ids()
        if self._layout_store is not None:
            self._layout_store.schedule_save()

    def _set_detail_field_visible(
        self,
        field_id: str,
        visible: bool,
        *,
        persist: bool = True,
        customized: bool = True,
    ) -> None:
        if self._current_layout is None or field_id not in self._detail_fields:
            return
        visible_fields = set(self._current_layout.visible_fields)
        if visible:
            visible_fields.add(field_id)
        else:
            visible_fields.discard(field_id)
        self._current_layout.visible_fields = sorted(visible_fields)
        self._current_layout.visibility_customized |= customized
        self._detail_fields[field_id].setVisible(visible)
        self._recompute_section_visibility()
        if persist and self._layout_store is not None:
            self._layout_store.schedule_save()

    def _recompute_section_visibility(self) -> None:
        visible = set(self._current_layout.visible_fields) if self._current_layout else set()
        for section_id, section in self._detail_sections.items():
            section.setVisible(
                any(
                    definition.field_id in visible
                    for definition in CHARACTER_DETAIL_DEFINITIONS
                    if definition.section_id == section_id
                )
            )

    def _on_add_detail(self, field_id: str) -> None:
        if field_id == "__create_custom__":
            detail = self._show_custom_detail_dialog()
            if detail is None:
                return
            label, value_type, include = detail
            self._custom_fields.add_empty_field(label, value_type, include)
            self._custom_section.set_expanded(True)
            return
        self._set_detail_field_visible(field_id, True)
        definition = next(
            item for item in CHARACTER_DETAIL_DEFINITIONS if item.field_id == field_id
        )
        section = self._detail_sections[definition.section_id]
        section.set_expanded(True)
        self._on_section_expanded(definition.section_id, True)
        self._detail_fields[field_id].focus_editor()

    def _show_custom_detail_dialog(
        self,
    ) -> tuple[str, CharacterCustomFieldType, bool] | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Create custom detail")
        form = QFormLayout(dialog)
        label = QLineEdit()
        field_type = QComboBox()
        for value_type, text in (
            (CharacterCustomFieldType.TEXT, "短文本"),
            (CharacterCustomFieldType.LONG_TEXT, "长文本"),
            (CharacterCustomFieldType.STRING_LIST, "列表"),
        ):
            field_type.addItem(text, value_type)
        include = QCheckBox("用于生成")
        include.setChecked(True)
        form.addRow("名称", label)
        form.addRow("类型", field_type)
        form.addRow("", include)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add")
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        value_type = field_type.currentData()
        return (
            label.text(),
            value_type if isinstance(value_type, CharacterCustomFieldType) else CharacterCustomFieldType.TEXT,
            include.isChecked(),
        )

    def _on_hide_detail(self, field_id: str) -> None:
        if self._current_id is None:
            return
        populated = field_id in populated_character_fields(
            self._gather_core(self._current_id)
        )
        self._set_detail_field_visible(field_id, False)
        if populated:
            label = next(
                item.label
                for item in CHARACTER_DETAIL_DEFINITIONS
                if item.field_id == field_id
            )
            self._layout_notice.setText(f'“{label}”已隐藏，内容仍会保留。')

    def _on_section_expanded(self, section_id: str, expanded: bool) -> None:
        if self._current_layout is None:
            return
        collapsed = set(self._current_layout.collapsed_sections)
        if expanded:
            collapsed.discard(section_id)
        else:
            collapsed.add(section_id)
        self._current_layout.collapsed_sections = sorted(collapsed)
        if self._layout_store is not None:
            self._layout_store.schedule_save()

    def _on_tier_changed(self) -> None:
        if self._populating or self._current_id is None or self._current_layout is None:
            return
        tier = self._core_tier.currentData()
        if not isinstance(tier, CharacterTier):
            return
        if (
            self._current_id not in self._persisted_character_ids
            and not self._current_layout.visibility_customized
        ):
            self._current_layout.visible_fields = sorted(
                default_character_fields(tier)
                | populated_character_fields(self._gather_core(self._current_id))
            )
            self._current_layout.initialized_for_tier = tier.value
            self._apply_character_layout(self._current_layout)
            if self._layout_store is not None:
                self._layout_store.schedule_save()
        else:
            missing = default_character_fields(tier) - set(
                self._current_layout.visible_fields
            )
            self._tier_suggestion.setText(
                f"此角色现在是{character_tier_label(tier)}。"
            )
            self._tier_suggestion.setVisible(bool(missing))
            self._recommended_btn.setVisible(bool(missing))
        self.characters_changed.emit()

    def _show_recommended_fields(self) -> None:
        tier = self._core_tier.currentData()
        if not isinstance(tier, CharacterTier):
            return
        for field_id in default_character_fields(tier):
            self._set_detail_field_visible(field_id, True, persist=False)
        self._tier_suggestion.setVisible(False)
        self._recommended_btn.setVisible(False)
        if self._layout_store is not None:
            self._layout_store.schedule_save()

    def _reset_visible_fields(self) -> None:
        if self._current_id is None or self._current_layout is None:
            return
        tier = self._core_tier.currentData()
        if not isinstance(tier, CharacterTier):
            return
        target = default_character_fields(tier) | populated_character_fields(
            self._gather_core(self._current_id)
        )
        hiding = set(self._current_layout.visible_fields) - target
        if hiding and QMessageBox.question(
            self,
            "重置可见字段",
            "这会隐藏空白的非推荐字段。字段内容不会被删除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._current_layout.visible_fields = sorted(target)
        self._current_layout.visibility_customized = True
        self._apply_character_layout(self._current_layout)
        if self._layout_store is not None:
            self._layout_store.schedule_save()

    # ── State Tab ──────────────────────────────────────────────────────────

    def _build_state_tab(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QVBoxLayout(container)

        form.addWidget(QLabel("当前状态由已确认的场景事件生成。"))
        explanation = QLabel("普通“保存”只保存角色基本设定，不会修改当前状态。")
        explanation.setStyleSheet("color: #777;")
        form.addWidget(explanation)
        self._edit_state_btn = QPushButton("手动修改状态")
        self._edit_state_btn.setEnabled(False)
        self._edit_state_btn.clicked.connect(self._on_edit_state)
        form.addWidget(self._edit_state_btn)

        # Current goal
        form.addWidget(QLabel("<b>当前目标</b>"))
        self._state_goal = QLineEdit()
        self._state_goal.setPlaceholderText("角色当前场景的目标")
        form.addWidget(self._state_goal)

        # Current emotion
        form.addWidget(QLabel("<b>当前情绪</b>"))
        self._state_emotion = QLineEdit()
        self._state_emotion.setPlaceholderText("如：紧张、愤怒、平静")
        form.addWidget(self._state_emotion)

        # Current location
        form.addWidget(QLabel("<b>当前位置</b>"))
        self._state_location = QLineEdit()
        self._state_location.setPlaceholderText("角色现在在哪")
        form.addWidget(self._state_location)

        # Current power level
        form.addWidget(QLabel("<b>当前修为</b>"))
        self._state_power = QLineEdit()
        self._state_power.setPlaceholderText("如：炼气三层")
        form.addWidget(self._state_power)

        # Current relationships
        form.addWidget(QLabel("<b>当前关系</b>（角色名 → 关系描述）"))
        self._state_relationships = KeyValueTable(["角色名", "关系描述"])
        form.addWidget(self._state_relationships)

        # Current knowledge
        form.addWidget(QLabel("<b>已知信息</b>"))
        self._state_knowledge = StringListEditor()
        form.addWidget(self._state_knowledge)

        # Current secrets
        form.addWidget(QLabel("<b>隐藏秘密</b>"))
        self._state_secrets = StringListEditor()
        form.addWidget(self._state_secrets)

        # Current status
        form.addWidget(QLabel("<b>当前状态</b>"))
        self._state_status = QLineEdit()
        self._state_status.setPlaceholderText("如：受伤、隐藏身份、备战考核")
        form.addWidget(self._state_status)

        # Last updated scene
        form.addWidget(QLabel("<b>最后更新场景</b>"))
        self._state_last_scene = QLineEdit()
        self._state_last_scene.setPlaceholderText("scene-001")
        self._state_last_scene.setReadOnly(True)
        form.addWidget(self._state_last_scene)

        self._saved_state_summary = QLabel()
        self._saved_state_summary.setStyleSheet("color: #777;")
        form.addWidget(self._saved_state_summary)
        self._presence_panel = StoryUsagePanel(title="Scene presence")
        self._presence_panel.scene_requested.connect(self.scene_requested)
        form.addWidget(self._presence_panel)

        for field in (
            self._state_goal,
            self._state_emotion,
            self._state_location,
            self._state_power,
            self._state_status,
        ):
            field.setReadOnly(True)
        self._state_relationships.set_read_only(True)
        self._state_knowledge.set_read_only(True)
        self._state_secrets.set_read_only(True)

        form.addStretch()
        scroll.setWidget(container)
        return scroll

    # ── List Management ────────────────────────────────────────────────────

    def _refresh_character_list(self) -> None:
        """Reload character list from disk."""
        if self._project_dir is None:
            return
        self._characters.clear()
        self._list.clear()

        ids = list_character_ids(self._project_dir)
        for cid in ids:
            try:
                char = load_character(self._project_dir, cid)
                self._characters[cid] = char
                self._add_to_list(char)
            except (ValueError, FileNotFoundError):
                continue

    def _add_to_list(self, character: Character) -> None:
        """Add a character entry to the list widget with tier badge."""
        label = f"{character.core.name} · {character_tier_label(character.core.tier)}"
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, character.core.id)
        color = TIER_COLORS.get(character.core.tier, QColor("#95a5a6"))
        item.setForeground(color)
        self._list.addItem(item)

    def _on_list_selection_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        if current is None or self._selection_change_in_progress:
            return
        if self._core_dirty and previous is not None:
            name = self._core_name.text().strip() or "未命名角色"
            draft_note = "\n\n放弃修改会移除这个尚未保存的新角色。" if self._current_id not in self._persisted_character_ids else ""
            reply = QMessageBox.question(
                self,
                "未保存的修改",
                f"角色「{name}」有未保存的修改。{draft_note}",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Save:
                if not self.save_current_character():
                    self._restore_list_selection(previous)
                    return
            elif reply == QMessageBox.StandardButton.Discard:
                self._discard_current_changes()
            else:
                self._restore_list_selection(previous)
                return
        char_id = current.data(Qt.ItemDataRole.UserRole)
        self._select_character(char_id)

    def _restore_list_selection(self, item: QListWidgetItem) -> None:
        self._selection_change_in_progress = True
        try:
            blocker = QSignalBlocker(self._list)
            self._list.setCurrentItem(item)
            del blocker
        finally:
            self._selection_change_in_progress = False

    def _discard_current_changes(self) -> None:
        if self._project_dir is None or self._current_id is None:
            return
        char_id = self._current_id
        if char_id not in self._persisted_character_ids:
            self._characters.pop(char_id, None)
            if self._layout_store is not None:
                self._layout_store.layout.characters.pop(char_id, None)
                self._layout_store.schedule_save()
            for row in range(self._list.count()):
                item = self._list.item(row)
                if item is not None and item.data(Qt.ItemDataRole.UserRole) == char_id:
                    self._list.takeItem(row)
                    break
            self._baseline_core = None
            self.characters_changed.emit()
        else:
            character = load_character(self._project_dir, char_id)
            self._characters[char_id] = character
            self._populating = True
            try:
                self._populate_core_tab(character.core)
            finally:
                self._populating = False
            self._baseline_core = character.core.model_copy(deep=True)
        self._set_core_dirty(False)

    def _select_character(self, char_id: str) -> None:
        """Populate detail tabs with the selected character's data."""
        char = self._characters.get(char_id)
        if char is None:
            self._clear_detail()
            return
        self._current_id = char_id
        self._populating = True
        try:
            self._populate_core_tab(char.core)
            self._populate_state_tab(char.state)
            if self._layout_store is not None:
                layout = self._layout_store.character_layout(char_id)
                if not layout.visible_fields and char_id not in self._persisted_character_ids:
                    layout.visible_fields = sorted(initial_character_fields(char.core))
                    layout.initialized_for_tier = char.core.tier.value
                self._apply_character_layout(layout)
        finally:
            self._populating = False
        self._baseline_core = char.core.model_copy(deep=True)
        self._set_core_dirty(char_id not in self._persisted_character_ids)
        persisted = char_id in self._persisted_character_ids
        self._edit_state_btn.setEnabled(persisted)
        self._edit_state_btn.setToolTip(
            "" if persisted else "请先保存角色基本设定，再修改角色状态。"
        )
        self._detail_tabs.setVisible(True)
        self._refresh_presence()
        # Populate history tab
        if self._project_dir is not None:
            char_dir = self._project_dir / "characters" / char_id
            self._history_tab.set_character(char_dir, self._current_scene_id)

    def _clear_detail(self) -> None:
        """Clear all detail fields."""
        self._populating = True
        self._current_id = None
        self._detail_tabs.setVisible(False)
        self._core_name.clear()
        self._core_tier.setCurrentIndex(1)  # supporting
        self._core_aliases.set_items([])
        self._core_identity.clear()
        self._core_age.clear()
        self._core_appearance.clear()
        self._core_personality.clear()
        self._core_background.clear()
        self._core_goal.clear()
        self._core_motive.clear()
        self._core_speech.clear()
        self._core_skills.set_items([])
        self._core_weaknesses.set_items([])
        self._custom_fields.set_fields([])
        self._element_relations.set_relations([])

        self._state_goal.clear()
        self._state_emotion.clear()
        self._state_location.clear()
        self._state_power.clear()
        self._state_relationships.set_rows([])
        self._state_knowledge.set_items([])
        self._state_secrets.set_items([])
        self._state_status.clear()
        self._state_last_scene.clear()
        self._baseline_core = None
        self._current_layout = None
        self._presence_panel.clear()
        self._populating = False
        self._set_core_dirty(False)
        self._edit_state_btn.setEnabled(False)

    # ── Populate ───────────────────────────────────────────────────────────

    def _populate_core_tab(self, core: CharacterCore) -> None:
        self._core_name.setText(core.name)
        idx = self._core_tier.findData(core.tier)
        if idx >= 0:
            self._core_tier.setCurrentIndex(idx)
        self._core_aliases.set_items(core.aliases)
        self._core_identity.setText(core.identity)
        self._core_age.setText(str(core.age))
        self._core_appearance.setPlainText(core.appearance)
        self._core_personality.setPlainText(core.personality)
        self._core_background.setPlainText(core.background)
        self._core_goal.setText(core.long_term_goal or "")
        self._core_motive.setText(core.hidden_motive or "")
        self._core_speech.setText(core.speech_style)
        self._core_skills.set_items(core.core_skills)
        self._core_weaknesses.set_items(core.core_weaknesses)
        self._custom_fields.set_fields(core.custom_fields)
        self._element_relations.set_relations(core.element_relations)
        if self._project_dir is not None:
            try:
                self._element_relations.set_elements(BibleElementRepository(self._project_dir).load_all())
            except FileNotFoundError:
                self._element_relations.set_elements([])

    def _populate_state_tab(self, state: CharacterState) -> None:
        self._state_goal.setText(state.current_goal)
        self._state_emotion.setText(state.current_emotion)
        self._state_location.setText(state.current_location)
        self._state_power.setText(state.current_power_level or "")
        rel_rows = [[k, v] for k, v in state.current_relationships.items()]
        self._state_relationships.set_rows(rel_rows if rel_rows else [["", ""]])
        self._state_knowledge.set_items(state.current_knowledge)
        self._state_secrets.set_items(state.current_secrets)
        self._state_status.setText(state.current_status)
        self._state_last_scene.setText(state.last_updated_scene or "")
        self._saved_state_summary.setText(
            f"已保存状态：{state.current_status or '—'} · 当前位置：{state.current_location or '—'}"
        )

    def _reload_state_tab(self) -> None:
        """Reload the current character's state from disk."""
        if self._project_dir is None or self._current_id is None:
            return
        try:
            char = load_character(self._project_dir, self._current_id)
            self._characters[self._current_id] = char
            self._populate_state_tab(char.state)
            self._refresh_presence()
        except Exception:
            logger.exception("Failed to reload state for %s", self._current_id)

    # ── Gather ─────────────────────────────────────────────────────────────

    def _refresh_presence(self) -> None:
        if self._project_dir is None or self._current_id is None:
            self._presence_panel.clear()
            return
        usages = StoryUsageService(self._project_dir).character_presence(self._current_id)
        self._presence_panel.set_usage(ElementUsageSummary(self._current_id, tuple(usages)))

    def _gather_core(self, char_id: str) -> CharacterCore:
        tier = self._core_tier.currentData()
        if not isinstance(tier, CharacterTier):
            tier = CharacterTier.SUPPORTING
        stored = self._baseline_core or self._characters[char_id].core

        return CharacterCore(
            id=char_id,
            name=self._core_name.text().strip(),
            aliases=self._core_aliases.get_items(),
            tier=tier,
            identity=self._core_identity.text().strip(),
            age=self._core_age.text().strip(),
            appearance=self._core_appearance.toPlainText().strip(),
            personality=self._core_personality.toPlainText().strip(),
            background=self._core_background.toPlainText().strip(),
            long_term_goal=self._core_goal.text().strip() or None,
            hidden_motive=self._core_motive.text().strip() or None,
            speech_style=self._core_speech.text().strip(),
            core_skills=self._core_skills.get_items(),
            core_weaknesses=self._core_weaknesses.get_items(),
            custom_fields=self._custom_fields.fields(),
            element_relations=self._element_relations.relations(),
            definition_revision=stored.definition_revision,
            definition_updated_at=stored.definition_updated_at,
        )

    def _recompute_core_dirty(self) -> None:
        if self._populating or self._current_id is None:
            return
        current = self._gather_core(self._current_id)
        self._set_core_dirty(
            self._current_id not in self._persisted_character_ids
            or self._semantic_core(current) != self._semantic_core(self._baseline_core)
        )

    @staticmethod
    def _semantic_core(core: CharacterCore | None) -> dict | None:
        if core is None:
            return None
        return core.model_dump(
            exclude={"definition_revision", "definition_updated_at"}
        )

    def _set_core_dirty(self, dirty: bool) -> None:
        if self._core_dirty == dirty:
            return
        self._core_dirty = dirty
        self._unsaved_label.setVisible(dirty)
        self._save_btn.setEnabled(dirty)
        self._update_current_list_item()
        self.dirty_changed.emit(dirty)

    def _update_current_list_item(self) -> None:
        if self._current_id is None:
            return
        if self._baseline_core is None and self._current_id not in self._characters:
            return
        core = self._gather_core(self._current_id)
        suffix = " *" if self._core_dirty else ""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == self._current_id:
                item.setText(f"{core.name} · {character_tier_label(core.tier)}{suffix}")
                item.setForeground(TIER_COLORS.get(core.tier, QColor("#95a5a6")))
                return

    def _gather_state(self, char_id: str) -> CharacterState:
        relationships: dict[str, str] = {}
        for row in range(self._state_relationships.rowCount()):
            name = read_table_cell(self._state_relationships._table, row, 0)
            desc = read_table_cell(self._state_relationships._table, row, 1)
            if name:
                relationships[name] = desc

        return CharacterState(
            character_id=char_id,
            current_goal=self._state_goal.text().strip(),
            current_emotion=self._state_emotion.text().strip(),
            current_location=self._state_location.text().strip(),
            current_power_level=self._state_power.text().strip() or None,
            current_relationships=relationships,
            current_knowledge=self._state_knowledge.get_items(),
            current_secrets=self._state_secrets.get_items(),
            current_status=self._state_status.text().strip(),
            last_updated_scene=self._state_last_scene.text().strip() or None,
        )

    # ── Actions ────────────────────────────────────────────────────────────

    def _on_add_character(self) -> None:
        """Create a new character with a default name."""
        if self._project_dir is None:
            return
        from uuid import uuid4

        char_id = str(uuid4())
        core = CharacterCore(id=char_id, name="新角色")
        state = CharacterState(character_id=char_id)
        character = Character(core=core, state=state)

        self._characters[char_id] = character
        if self._layout_store is not None:
            self._layout_store.layout.characters[char_id] = CharacterEditorLayout(
                visible_fields=sorted(
                    default_character_fields(CharacterTier.SUPPORTING)
                ),
                initialized_for_tier=CharacterTier.SUPPORTING.value,
            )
            self._layout_store.schedule_save()
        self._add_to_list(character)

        # Select the new character
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == char_id:
                self._list.setCurrentRow(i)
                break
        current = self._list.currentItem()
        if current is None or current.data(Qt.ItemDataRole.UserRole) != char_id:
            self._characters.pop(char_id, None)
            self._list.takeItem(self._list.count() - 1)
            if self._layout_store is not None:
                self._layout_store.layout.characters.pop(char_id, None)
                self._layout_store.schedule_save()
        else:
            self.characters_changed.emit()

    def _on_delete_character(self) -> None:
        """Delete the selected character with confirmation."""
        if self._current_id is None or self._project_dir is None:
            return

        char = self._characters.get(self._current_id)
        name = self._core_name.text().strip() or (char.core.name if char else "未知")
        message = f"确定删除角色「{name}」吗？"
        if self._core_dirty:
            message += "\n\n该角色还有未保存的修改。删除后，已保存内容和未保存修改都会丢失。"
        else:
            message += "删除后无法恢复。"
        reply = QMessageBox.question(
            self,
            "确认删除",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted_id = self._current_id
        delete_character(self._project_dir, deleted_id)
        if self._layout_store is not None:
            self._layout_store.layout.characters.pop(deleted_id, None)
            self._layout_store.schedule_save()
        self._refresh_character_list()
        self.saved.emit()
        self.characters_changed.emit()

        # Select first character or clear
        if self._characters:
            first_id = next(iter(self._characters))
            self._list.setCurrentRow(0)
            self._select_character(first_id)
        else:
            self._clear_detail()

    def _on_edit_state(self) -> None:
        if (
            self._project_dir is None
            or self._current_id is None
            or self._current_id not in self._persisted_character_ids
        ):
            return
        from app.ui.character_state_edit_dialog import CharacterStateEditDialog

        char_dir = self._project_dir / "characters" / self._current_id
        persisted = load_character(self._project_dir, self._current_id)
        opened_at_event_id = get_latest_event_id(char_dir)
        dialog = CharacterStateEditDialog(persisted.state, self)
        if not dialog.exec():
            return
        proposed = dialog.gathered_state()
        if proposed == persisted.state:
            return

        changed_labels = [
            label
            for attribute, label in (
                ("current_goal", "当前目标"),
                ("current_emotion", "当前情绪"),
                ("current_location", "当前位置"),
                ("current_power_level", "当前修为"),
                ("current_status", "当前状态"),
                ("current_relationships", "当前关系"),
                ("current_knowledge", "已知信息"),
                ("current_secrets", "隐藏秘密"),
            )
            if getattr(persisted.state, attribute) != getattr(proposed, attribute)
        ]
        reply = QMessageBox.question(
            self,
            "确认手动修改状态",
            "将记录以下状态修改：\n" + "、".join(changed_labels),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if get_latest_event_id(char_dir) != opened_at_event_id:
            QMessageBox.warning(
                self,
                "状态已变化",
                "角色状态在编辑期间已发生变化。为避免覆盖新状态，请重新打开编辑窗口。",
            )
            return

        event = commit_character_state_edit(
            char_dir,
            persisted.state,
            proposed,
            scene_id=self._current_scene_id,
            bus=self._bus,
            source="manual_event",
        )
        if event is not None:
            self._reload_state_tab()
            self._history_tab.set_character(char_dir, self._current_scene_id)

    def save_current_character(self) -> bool:
        """Persist the current Character Definition, if changed."""
        if self._project_dir is None or self._current_id is None:
            return True
        if not self._core_dirty:
            return True

        name = self._core_name.text().strip()
        if not name:
            QMessageBox.warning(self, "保存失败", "角色姓名不能为空")
            return False

        try:
            was_new = self._current_id not in self._persisted_character_ids
            core = self._gather_core(self._current_id)
            char_dir = self._project_dir / "characters" / self._current_id
            if (char_dir / "definition.yaml").exists():
                save_character_definition(self._project_dir, core)
            else:
                save_character(
                    self._project_dir,
                    Character(core=core, state=CharacterState(character_id=self._current_id)),
                )

            saved_character = load_character(self._project_dir, self._current_id)
            self._characters[self._current_id] = saved_character
            self._persisted_character_ids.add(self._current_id)
            self._baseline_core = saved_character.core.model_copy(deep=True)
            self._populating = True
            try:
                self._populate_core_tab(saved_character.core)
                self._populate_state_tab(saved_character.state)
                self._refresh_presence()
            finally:
                self._populating = False
            self._set_core_dirty(False)
            self._edit_state_btn.setEnabled(True)
            self._edit_state_btn.setToolTip("")
            self.saved.emit()
            if was_new:
                self.characters_changed.emit()
            return True
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))
            return False

    def _on_save(self) -> None:
        self.save_current_character()

