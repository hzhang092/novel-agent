"""Presentation wrapper for an existing story Detail Field editor."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget


class DetailFieldContainer(QWidget):
    hide_requested = pyqtSignal(str)

    def __init__(
        self,
        field_id: str,
        label: str,
        editor: QWidget,
        *,
        hideable: bool = True,
        help_text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.field_id = field_id
        self.editor = editor

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        field_label = QLabel(label)
        field_label.setBuddy(editor)
        header.addWidget(field_label)
        header.addStretch()
        if hideable:
            hide_button = QToolButton()
            hide_button.setText("从编辑器隐藏")
            hide_button.setToolTip(
                "隐藏不会删除内容，也不会影响生成上下文。"
            )
            hide_button.setAccessibleName(f"Hide {label} from editor")
            hide_button.clicked.connect(lambda: self.hide_requested.emit(field_id))
            header.addWidget(hide_button)
        layout.addLayout(header)
        if help_text:
            layout.addWidget(QLabel(help_text))
        layout.addWidget(editor)

    def focus_editor(self) -> None:
        self.window().activateWindow()
        self.editor.setFocus(Qt.FocusReason.OtherFocusReason)
