"""Explicit editor for a Manual State Override."""

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from app.storage.models import CharacterState
from app.ui.widgets import KeyValueTable, StringListEditor, read_table_cell


class CharacterStateEditDialog(QDialog):
    def __init__(
        self,
        state: CharacterState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._original = state.model_copy(deep=True)
        self.setWindowTitle("手动修改状态")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("修改会记录到角色变化历史。"))

        form = QFormLayout()
        self._goal = self._line_edit("current_goal", state.current_goal)
        self._emotion = self._line_edit("current_emotion", state.current_emotion)
        self._location = self._line_edit("current_location", state.current_location)
        self._power = self._line_edit("current_power_level", state.current_power_level or "")
        self._status = self._line_edit("current_status", state.current_status)
        form.addRow("当前目标", self._goal)
        form.addRow("当前情绪", self._emotion)
        form.addRow("当前位置", self._location)
        form.addRow("当前修为", self._power)
        form.addRow("当前状态", self._status)
        layout.addLayout(form)

        self._relationships = KeyValueTable(["角色 ID", "关系描述"])
        self._relationships.set_rows([[key, value] for key, value in state.current_relationships.items()])
        layout.addWidget(QLabel("当前关系"))
        layout.addWidget(self._relationships)

        self._knowledge = StringListEditor()
        self._knowledge.set_items(state.current_knowledge)
        layout.addWidget(QLabel("已知信息"))
        layout.addWidget(self._knowledge)

        self._secrets = StringListEditor()
        self._secrets.set_items(state.current_secrets)
        layout.addWidget(QLabel("隐藏秘密"))
        layout.addWidget(self._secrets)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _line_edit(name: str, value: str) -> QLineEdit:
        editor = QLineEdit(value)
        editor.setObjectName(name)
        return editor

    def gathered_state(self) -> CharacterState:
        relationships = {}
        for row in range(self._relationships.rowCount()):
            key = read_table_cell(self._relationships._table, row, 0)
            if key:
                relationships[key] = read_table_cell(self._relationships._table, row, 1)
        return CharacterState(
            character_id=self._original.character_id,
            current_goal=self._goal.text().strip(),
            current_emotion=self._emotion.text().strip(),
            current_location=self._location.text().strip(),
            current_power_level=self._power.text().strip() or None,
            current_relationships=relationships,
            current_knowledge=self._knowledge.get_items(),
            current_secrets=self._secrets.get_items(),
            current_status=self._status.text().strip(),
            last_updated_scene=self._original.last_updated_scene,
        )
