"""Character editor widget — list + detail with Core/State tabs."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
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

from app.storage.models import Character, CharacterCore, CharacterState, CharacterTier
from app.storage.project_files import (
    delete_character,
    list_character_ids,
    load_character,
    save_character,
)
from app.ui.bible_editor import _KeyValueTable, _StringListEditor

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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_dir: Path | None = None
        self._characters: dict[str, Character] = {}  # id -> Character
        self._current_id: str | None = None
        self._setup_ui()

    # ── Public API ─────────────────────────────────────────────────────────

    def load_project_dir(self, project_dir: Path) -> None:
        """Load all characters from disk and populate the list."""
        self._project_dir = project_dir
        self._refresh_character_list()
        if self._characters:
            first_id = next(iter(self._characters))
            self._list.setCurrentRow(0)
            self._select_character(first_id)
        else:
            self._clear_detail()

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

        self._save_btn = QPushButton("保存")
        self._save_btn.setToolTip("保存当前角色修改到磁盘")
        self._save_btn.clicked.connect(self._on_save)
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
        self._core_tab = self._build_core_tab()
        self._state_tab = self._build_state_tab()
        self._detail_tabs.addTab(self._core_tab, "核心设定")
        self._detail_tabs.addTab(self._state_tab, "当前状态")
        splitter.addWidget(self._detail_tabs)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

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
        self._core_tier.addItems(["major", "supporting", "background"])
        row1.addWidget(self._core_tier)
        form.addLayout(row1)

        # Aliases
        form.addWidget(QLabel("<b>别称</b>"))
        self._core_aliases = _StringListEditor()
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
        self._core_skills = _StringListEditor()
        form.addWidget(self._core_skills)

        # Core weaknesses
        form.addWidget(QLabel("<b>核心弱点</b>"))
        self._core_weaknesses = _StringListEditor()
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
        self._state_relationships = _KeyValueTable(["角色名", "关系描述"])
        form.addWidget(self._state_relationships)

        # Current knowledge
        form.addWidget(QLabel("<b>已知信息</b>"))
        self._state_knowledge = _StringListEditor()
        form.addWidget(self._state_knowledge)

        # Current secrets
        form.addWidget(QLabel("<b>隐藏秘密</b>"))
        self._state_secrets = _StringListEditor()
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
        label = f"{character.core.name}"
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, character.core.id)
        color = TIER_COLORS.get(character.core.tier, QColor("#95a5a6"))
        item.setForeground(color)
        self._list.addItem(item)

    def _on_list_selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        char_id = current.data(Qt.ItemDataRole.UserRole)
        self._select_character(char_id)

    def _select_character(self, char_id: str) -> None:
        """Populate detail tabs with the selected character's data."""
        char = self._characters.get(char_id)
        if char is None:
            self._clear_detail()
            return
        self._current_id = char_id
        self._populate_core_tab(char.core)
        self._populate_state_tab(char.state)

    def _clear_detail(self) -> None:
        """Clear all detail fields."""
        self._current_id = None
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

    # ── Populate ───────────────────────────────────────────────────────────

    def _populate_core_tab(self, core: CharacterCore) -> None:
        self._core_name.setText(core.name)
        idx = self._core_tier.findText(core.tier.value)
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

    # ── Gather ─────────────────────────────────────────────────────────────

    def _gather_core(self, char_id: str) -> CharacterCore:
        tier_text = self._core_tier.currentText()
        try:
            tier = CharacterTier(tier_text)
        except ValueError:
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

    def _gather_state(self, char_id: str) -> CharacterState:
        relationships: dict[str, str] = {}
        for row in range(self._state_relationships.rowCount()):
            name = _cell(self._state_relationships._table, row, 0)
            desc = _cell(self._state_relationships._table, row, 1)
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
        self._select_character(char_id)

    def _on_delete_character(self) -> None:
        """Delete the selected character with confirmation."""
        if self._current_id is None or self._project_dir is None:
            return

        char = self._characters.get(self._current_id)
        name = char.core.name if char else "未知"
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除角色「{name}」吗？此操作不可撤销。",
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

    def _on_save(self) -> None:
        """Save the current character to disk."""
        if self._project_dir is None or self._current_id is None:
            return

        name = self._core_name.text().strip()
        if not name:
            QMessageBox.warning(self, "保存失败", "角色姓名不能为空")
            return

        try:
            core = self._gather_core(self._current_id)
            state = self._gather_state(self._current_id)
            character = Character(core=core, state=state)

            save_character(self._project_dir, character)
            self._characters[self._current_id] = character

            # Update list item label
            for i in range(self._list.count()):
                item = self._list.item(i)
                if item is not None and item.data(Qt.ItemDataRole.UserRole) == self._current_id:
                    item.setText(name)
                    color = TIER_COLORS.get(core.tier, QColor("#95a5a6"))
                    item.setForeground(color)
                    break

            self.saved.emit()
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))


def _cell(table, row: int, col: int) -> str:
    """Read a cell from a QTableWidget."""
    from PyQt6.QtWidgets import QTableWidget
    item = table.item(row, col)
    return item.text().strip() if item else ""
