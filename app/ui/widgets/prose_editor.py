"""ProseEditorWidget — QTextEdit with Markdown preview toggle."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import markdown


class ProseEditorWidget(QWidget):
    """Prose editor with plain-text editing mode and Markdown preview.

    Editing mode: QTextEdit with cut/copy/paste, undo/redo.
    Preview mode: QTextBrowser rendering Markdown as styled HTML.
    """

    version_selected = pyqtSignal(str)
    set_active_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._preview_on = False
        self._updating_versions = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Toolbar
        toolbar = QHBoxLayout()

        self._preview_btn = QPushButton("预览")
        self._preview_btn.setCheckable(True)
        self._preview_btn.toggled.connect(self._on_toggle_preview)
        toolbar.addWidget(self._preview_btn)

        self._version_combo = QComboBox()
        self._version_combo.setEnabled(False)
        self._version_combo.currentIndexChanged.connect(self._on_version_changed)
        toolbar.addWidget(self._version_combo)

        self._set_active_btn = QPushButton("发布此版本")
        self._set_active_btn.setEnabled(False)
        self._set_active_btn.clicked.connect(self._on_set_active)
        toolbar.addWidget(self._set_active_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Stack: editor | preview
        self._stack = QStackedWidget()

        self._editor = QTextEdit()
        self._editor.setPlaceholderText("生成的文本将在此显示...")
        self._stack.addWidget(self._editor)

        self._preview = QTextBrowser()
        self._preview.setOpenExternalLinks(False)
        self._stack.addWidget(self._preview)

        layout.addWidget(self._stack)

        # Keyboard shortcuts
        QShortcut(QKeySequence.StandardKey.Cut, self._editor, lambda: self._editor.cut())
        QShortcut(QKeySequence.StandardKey.Copy, self._editor, lambda: self._editor.copy())
        QShortcut(QKeySequence.StandardKey.Paste, self._editor, lambda: self._editor.paste())
        QShortcut(QKeySequence.StandardKey.Undo, self._editor, lambda: self._editor.undo())
        QShortcut(QKeySequence.StandardKey.Redo, self._editor, lambda: self._editor.redo())

    def _on_toggle_preview(self, checked: bool) -> None:
        """Toggle between edit and preview modes."""
        if checked:
            self._preview_on = True
            self._preview_btn.setText("编辑")
            md_text = self._editor.toPlainText()
            html = markdown.markdown(
                md_text,
                extensions=["extra", "nl2br", "sane_lists"],
            )
            styled_html = _wrap_html(html)
            self._preview.setHtml(styled_html)
            self._stack.setCurrentWidget(self._preview)
        else:
            self._preview_on = False
            self._preview_btn.setText("预览")
            self._stack.setCurrentWidget(self._editor)

    def setPlainText(self, text: str) -> None:
        """Set the editor text (mirrors QTextEdit.setPlainText)."""
        self._editor.setPlainText(text)
        self._editor.document().setModified(False)

    def toPlainText(self) -> str:
        """Get the editor text."""
        return self._editor.toPlainText()

    def append(self, text: str) -> None:
        """Append text to the editor during streaming. Falls back from preview."""
        if self._preview_on:
            self._preview_btn.setChecked(False)
        self._editor.moveCursor(self._editor.textCursor().MoveOperation.End)
        self._editor.insertPlainText(text)
        scrollbar = self._editor.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())

    def set_versions(self, versions: list[str], current: str | None = None) -> None:
        """Set selectable prose version tokens."""
        self._updating_versions = True
        self._version_combo.clear()
        for version in versions:
            label = "Legacy" if version == "legacy" else version
            if current is not None and version == current:
                label = f"已选 ({label})"
            self._version_combo.addItem(label, version)
        if current is not None:
            index = self._version_combo.findData(current)
            if index >= 0:
                self._version_combo.setCurrentIndex(index)
        self._version_combo.setEnabled(len(versions) > 1)
        self._set_active_btn.setEnabled(bool(versions))
        self._updating_versions = False

    def current_version(self) -> str:
        """Return the selected prose version token."""
        return self._version_combo.currentData() or ""

    def is_modified(self) -> bool:
        """Return whether the editor has unsaved user edits."""
        return self._editor.document().isModified()

    def _on_version_changed(self, index: int) -> None:
        if self._updating_versions or index < 0:
            return
        version = self._version_combo.itemData(index)
        if version:
            self.version_selected.emit(version)

    def _on_set_active(self) -> None:
        version = self.current_version()
        if version:
            self.set_active_requested.emit(version)


def _wrap_html(body: str) -> str:
    """Wrap rendered Markdown body in Chinese-typography-friendly CSS."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{
    font-family: "Microsoft YaHei", "SimSun", serif;
    font-size: 15px;
    line-height: 1.9;
    color: #e0e0e0;
    background: #1e1e1e;
    padding: 16px 24px;
    margin: 0;
}}
h1 {{ font-size: 20px; margin-top: 1.5em; }}
h2 {{ font-size: 17px; margin-top: 1.2em; }}
h3 {{ font-size: 15px; margin-top: 1em; }}
p {{ text-indent: 2em; margin: 0.6em 0; }}
</style>
</head>
<body>
{body}
</body>
</html>"""
