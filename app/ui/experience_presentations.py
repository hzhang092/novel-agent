"""The two top-level creation presentations."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QStackedWidget, QWidget


class _Presentation(QWidget):
    destination_changed = Signal(str)
    destinations: tuple[tuple[str, str], ...] = ()

    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(180)
        self.sidebar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.stack = QStackedWidget()
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack)
        for label, key in self.destinations:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.sidebar.addItem(item)
        self.sidebar.currentRowChanged.connect(self._changed)

    def _changed(self, row: int) -> None:
        item = self.sidebar.item(row)
        if item is not None:
            self.destination_changed.emit(item.data(Qt.ItemDataRole.UserRole))


class DeepCreationPresentation(_Presentation):
    destinations = (("总览", "dashboard"), ("设定集", "bible"), ("大纲", "outline"), ("写作台", "workspace"))


class QuickCreationPresentation(_Presentation):
    destinations = (("故事", "story"), ("大纲", "outline"), ("写章节", "workspace"))
