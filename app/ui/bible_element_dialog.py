"""Minimal dialog for creating an in-memory typed Bible Element draft."""

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.storage.bible_models import (
    BibleElement,
    BibleElementType,
    FactionElement,
    HistoricalEventElement,
    LocationElement,
    PowerSystemElement,
    TerminologyElement,
)
from app.ui.bible_element_list import ELEMENT_TYPE_DETAILS


_ELEMENT_CLASSES = {
    BibleElementType.LOCATION: LocationElement,
    BibleElementType.FACTION: FactionElement,
    BibleElementType.HISTORICAL_EVENT: HistoricalEventElement,
    BibleElementType.POWER_SYSTEM: PowerSystemElement,
    BibleElementType.TERMINOLOGY: TerminologyElement,
}


class BibleElementDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        default_type: BibleElementType | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Story Element")
        layout = QVBoxLayout(self)

        self._steps = QStackedWidget()
        type_page = QWidget()
        type_layout = QVBoxLayout(type_page)
        type_layout.addWidget(QLabel("Choose element type"))
        self._type = QComboBox()
        for element_type, (_group, label) in ELEMENT_TYPE_DETAILS.items():
            self._type.addItem(label, element_type)
        self._type.currentIndexChanged.connect(self._update_minimum_fields)
        type_layout.addWidget(self._type)
        type_layout.addStretch()
        self._steps.addWidget(type_page)

        details_page = QWidget()
        details_layout = QVBoxLayout(details_page)
        self._name_label = QLabel("Name")
        details_layout.addWidget(self._name_label)
        self._name = QLineEdit()
        details_layout.addWidget(self._name)

        self._definition_label = QLabel("Definition")
        details_layout.addWidget(self._definition_label)
        self._definition = QTextEdit()
        self._definition.setMaximumHeight(80)
        details_layout.addWidget(self._definition)
        details_layout.addStretch()
        self._steps.addWidget(details_page)
        layout.addWidget(self._steps)

        navigation = QHBoxLayout()
        self._back_button = QPushButton("Back")
        self._back_button.clicked.connect(lambda: self._set_step(0))
        self._next_button = QPushButton("Next")
        self._next_button.clicked.connect(lambda: self._set_step(1))
        navigation.addWidget(self._back_button)
        navigation.addStretch()
        navigation.addWidget(self._next_button)
        layout.addLayout(navigation)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Create")
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        if default_type is not None:
            self._type.setCurrentIndex(self._type.findData(default_type))
        self._set_step(1 if default_type is not None else 0)
        self._update_minimum_fields()

    def create_draft(self) -> BibleElement:
        element_type = self._type.currentData()
        values = {"name": self._name.text().strip()}
        if element_type == BibleElementType.TERMINOLOGY:
            values["definition"] = self._definition.toPlainText().strip()
        return _ELEMENT_CLASSES[element_type](**values)

    def accept(self) -> None:
        if not self._name.text().strip():
            QMessageBox.warning(self, "Cannot add Story Element", "Name is required.")
            self._name.setFocus()
            return
        if (
            self._type.currentData() == BibleElementType.TERMINOLOGY
            and not self._definition.toPlainText().strip()
        ):
            QMessageBox.warning(
                self,
                "Cannot add Story Element",
                "Definition is required for terminology.",
            )
            self._definition.setFocus()
            return
        super().accept()

    def _update_minimum_fields(self, *_args) -> None:
        terminology = self._type.currentData() == BibleElementType.TERMINOLOGY
        self._name_label.setText("Term" if terminology else "Name")
        self._definition_label.setVisible(terminology)
        self._definition.setVisible(terminology)

    def _set_step(self, step: int) -> None:
        self._steps.setCurrentIndex(step)
        self._back_button.setVisible(step == 1)
        self._next_button.setVisible(step == 0)
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setVisible(step == 1)
