"""Character editor widget — list + detail with Core/State tabs."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
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

import logging

from app.storage.models import Character, CharacterCore, CharacterState, CharacterTier
from app.storage.project_files import (
    delete_character,
    list_character_ids,
    load_character,
    save_character,
    save_character_definition,
)
from app.storage.character_events import get_latest_event_id
from app.storage.state_repository import commit_character_state_edit

logger = logging.getLogger(__name__)
from app.ui.display_labels import character_tier_label
from app.ui.widgets import KeyValueTable, StringListEditor, read_table_cell

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

    def __init__(self, parent: QWidget | None = None) -> None:
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
        self._setup_ui()
        self._connect_definition_changes()

    # ── Public API ─────────────────────────────────────────────────────────

    def load_project_dir(self, project_dir: Path) -> None:
        """Load all characters from disk and populate the list."""
        self._project_dir = project_dir
        self._refresh_character_list()
        self._persisted_character_ids = set(self._characters)
        if self._characters:
            first_id = next(iter(self._characters))
            self._list.setCurrentRow(0)
            self._select_character(first_id)
        else:
            self._clear_detail()

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
        for editor in (
            self._core_aliases,
            self._core_skills,
            self._core_weaknesses,
        ):
            editor.changed.connect(self._recompute_core_dirty)

    # ── Core Tab ───────────────────────────────────────────────────────────

    def _build_core_tab(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QVBoxLayout(container)

        # Name + Tier row
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
        form.addLayout(row1)

        # Aliases
        form.addWidget(QLabel("<b>别称</b>"))
        self._core_aliases = StringListEditor()
        form.addWidget(self._core_aliases)

        # Identity
        form.addWidget(QLabel("<b>身份</b>"))
        self._core_identity = QLineEdit()
        self._core_identity.setPlaceholderText("如：落云宗外门弟子")
        form.addWidget(self._core_identity)

        # Age
        form.addWidget(QLabel("<b>年龄</b>"))
        self._core_age = QLineEdit()
        self._core_age.setPlaceholderText("如：17")
        form.addWidget(self._core_age)

        # Appearance
        form.addWidget(QLabel("<b>外貌</b>"))
        self._core_appearance = QTextEdit()
        self._core_appearance.setPlaceholderText("描述角色外貌特征...")
        self._core_appearance.setMaximumHeight(80)
        form.addWidget(self._core_appearance)

        # Personality
        form.addWidget(QLabel("<b>性格</b>"))
        self._core_personality = QTextEdit()
        self._core_personality.setPlaceholderText("描述角色性格...")
        self._core_personality.setMaximumHeight(80)
        form.addWidget(self._core_personality)

        # Background
        form.addWidget(QLabel("<b>背景</b>"))
        self._core_background = QTextEdit()
        self._core_background.setPlaceholderText("角色背景故事...")
        self._core_background.setMaximumHeight(100)
        form.addWidget(self._core_background)

        # Long-term goal
        form.addWidget(QLabel("<b>长期目标</b>"))
        self._core_goal = QLineEdit()
        self._core_goal.setPlaceholderText("角色最终追求的目标")
        form.addWidget(self._core_goal)

        # Hidden motive
        form.addWidget(QLabel("<b>隐藏动机</b>"))
        self._core_motive = QLineEdit()
        self._core_motive.setPlaceholderText("不为人知的深层动机")
        form.addWidget(self._core_motive)

        # Speech style
        form.addWidget(QLabel("<b>说话风格</b>"))
        self._core_speech = QLineEdit()
        self._core_speech.setPlaceholderText("如：沉稳少言、活泼多话")
        form.addWidget(self._core_speech)

        # Core skills
        form.addWidget(QLabel("<b>核心技能</b>"))
        self._core_skills = StringListEditor()
        form.addWidget(self._core_skills)

        # Core weaknesses
        form.addWidget(QLabel("<b>核心弱点</b>"))
        self._core_weaknesses = StringListEditor()
        form.addWidget(self._core_weaknesses)

        form.addStretch()
        scroll.setWidget(container)
        return scroll

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
            for row in range(self._list.count()):
                item = self._list.item(row)
                if item is not None and item.data(Qt.ItemDataRole.UserRole) == char_id:
                    self._list.takeItem(row)
                    break
            self._baseline_core = None
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

    def _reload_state_tab(self) -> None:
        """Reload the current character's state from disk."""
        if self._project_dir is None or self._current_id is None:
            return
        try:
            char = load_character(self._project_dir, self._current_id)
            self._characters[self._current_id] = char
            self._populate_state_tab(char.state)
        except Exception:
            logger.exception("Failed to reload state for %s", self._current_id)

    # ── Gather ─────────────────────────────────────────────────────────────

    def _gather_core(self, char_id: str) -> CharacterCore:
        tier = self._core_tier.currentData()
        if not isinstance(tier, CharacterTier):
            tier = CharacterTier.SUPPORTING

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
        )

    def _recompute_core_dirty(self) -> None:
        if self._populating or self._current_id is None:
            return
        current = self._gather_core(self._current_id)
        self._set_core_dirty(
            self._current_id not in self._persisted_character_ids
            or current != self._baseline_core
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

        delete_character(self._project_dir, self._current_id)
        self._refresh_character_list()
        self.saved.emit()

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
            finally:
                self._populating = False
            self._set_core_dirty(False)
            self._edit_state_btn.setEnabled(True)
            self._edit_state_btn.setToolTip("")
            self.saved.emit()
            return True
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))
            return False

    def _on_save(self) -> None:
        self.save_current_character()

