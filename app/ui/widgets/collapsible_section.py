"""Reusable collapsible editor section."""

from PySide6.QtCore import Qt, QSignalBlocker, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class _HeaderButton(QPushButton):
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            self.click()
            return
        super().keyPressEvent(event)


class CollapsibleSection(QWidget):
    expanded_changed = Signal(bool)
    hide_requested = Signal()

    def __init__(
        self,
        title: str,
        *,
        section_id: str,
        collapsible: bool = True,
        hideable: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.section_id = section_id
        self._collapsible = collapsible
        self._content: QWidget | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        self._header = _HeaderButton(f"⌄  {title}")
        self._header.setObjectName("collapsible-section-header")
        self._header.setAccessibleName(f"{title} section")
        self._header.setCheckable(collapsible)
        self._header.setChecked(True)
        self._header.setFlat(True)
        self._header.clicked.connect(self._toggle)
        header.addWidget(self._header, stretch=1)

        self._summary = QLabel()
        header.addWidget(self._summary)

        if hideable:
            hide_button = QToolButton()
            hide_button.setText("⋯")
            hide_button.setAccessibleName(f"Hide {title} section")
            hide_button.setToolTip("Hide section")
            hide_button.clicked.connect(self.hide_requested)
            header.addWidget(hide_button)
        layout.addLayout(header)

    def set_content_widget(self, widget: QWidget) -> None:
        if self._content is not None:
            self.layout().removeWidget(self._content)
        self._content = widget
        self.layout().addWidget(widget)
        widget.setVisible(self.is_expanded())

    def content_widget(self) -> QWidget | None:
        return self._content

    def is_expanded(self) -> bool:
        return not self._collapsible or self._header.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        expanded = expanded or not self._collapsible
        with QSignalBlocker(self._header):
            self._header.setChecked(expanded)
        self._apply_expanded(expanded)

    def set_summary(self, summary: str) -> None:
        self._summary.setText(summary)

    def _toggle(self, checked: bool) -> None:
        if not self._collapsible:
            return
        self._apply_expanded(checked)
        self.expanded_changed.emit(checked)

    def _apply_expanded(self, expanded: bool) -> None:
        self._header.setText(
            f"{'⌄' if expanded else '›'}  {self._header.text()[3:]}"
        )
        if self._content is not None:
            self._content.setVisible(expanded)
