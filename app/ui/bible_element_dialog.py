"""Minimal dialog for creating an in-memory typed Bible Element draft."""

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
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

        layout.addWidget(QLabel("Element type"))
        self._type = QComboBox()
        for element_type, (_group, label) in ELEMENT_TYPE_DETAILS.items():
            self._type.addItem(label, element_type)
        self._type.currentIndexChanged.connect(self._update_minimum_fields)
        layout.addWidget(self._type)

        self._name_label = QLabel("Name")
        layout.addWidget(self._name_label)
        self._name = QLineEdit()
        layout.addWidget(self._name)

        self._definition_label = QLabel("Definition")
        layout.addWidget(self._definition_label)
        self._definition = QTextEdit()
        self._definition.setMaximumHeight(80)
        layout.addWidget(self._definition)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if default_type is not None:
            self._type.setCurrentIndex(self._type.findData(default_type))
        self._update_minimum_fields()

    def create_draft(self) -> BibleElement:
        element_type = self._type.currentData()
        values = {"name": self._name.text().strip()}
        if element_type == BibleElementType.TERMINOLOGY:
            values["definition"] = self._definition.toPlainText().strip()
        return _ELEMENT_CLASSES[element_type](**values)

    def _update_minimum_fields(self, *_args) -> None:
        terminology = self._type.currentData() == BibleElementType.TERMINOLOGY
        self._name_label.setText("Term" if terminology else "Name")
        self._definition_label.setVisible(terminology)
        self._definition.setVisible(terminology)

