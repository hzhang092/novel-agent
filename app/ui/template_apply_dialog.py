"""Options for applying a Story Template to the current form."""

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from app.utils.template_merge import TemplateMergeMode


class TemplateApplyDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("应用修仙模板")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("应用范围"))
        self._world = QCheckBox("世界设定")
        self._world.setChecked(True)
        self._style = QCheckBox("写作风格")
        self._style.setChecked(True)
        layout.addWidget(self._world)
        layout.addWidget(self._style)

        layout.addWidget(QLabel("处理现有内容"))
        self._fill = QRadioButton("仅填充空白内容")
        self._fill.setChecked(True)
        self._merge = QRadioButton("合并模板内容")
        self._replace = QRadioButton("替换所选内容")
        layout.addWidget(self._fill)
        layout.addWidget(self._merge)
        layout.addWidget(self._replace)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Apply
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def apply_world(self) -> bool:
        return self._world.isChecked()

    @property
    def apply_style(self) -> bool:
        return self._style.isChecked()

    @property
    def merge_mode(self) -> TemplateMergeMode:
        if self._replace.isChecked():
            return TemplateMergeMode.REPLACE
        if self._merge.isChecked():
            return TemplateMergeMode.MERGE
        return TemplateMergeMode.FILL_EMPTY
