"""FactApprovalPanel — batch approval UI for extracted facts and state changes."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class FactApprovalPanel(QWidget):
    """Panel showing extracted facts + state changes for user approval.

    Emits approval_batch_approved with the source scene id, approved fact
    dicts, and approved state change dicts when the user confirms.
    """

    approval_batch_approved = Signal(str, str, list, list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source_scene_id = ""
        self._source_revision_id = ""
        self._facts: list[dict] = []
        self._state_changes: list[dict] = []
        self._fact_checkboxes: list[QCheckBox] = []
        self._change_checkboxes: list[QCheckBox] = []
        self._change_locations: list[tuple[int, int | None]] = []
        self._change_editors: list[QLineEdit] = []
        self._setup_ui()

    @property
    def pending_counts(self) -> tuple[int, int]:
        """Return pending fact and state-change counts."""
        return len(self._facts), len(self._state_changes)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header
        header = QLabel("<b>设定与状态审批</b>")
        header.setStyleSheet("font-size: 14px; color: #f39c12;")
        layout.addWidget(header)

        desc = QLabel(
            "检查提取的事实与角色状态变更。勾选以批准，未勾选的将被丢弃。"
            "可以编辑每条内容的描述。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(desc)

        self._source_scene_label = QLabel("")
        self._source_scene_label.setStyleSheet("color: #888; font-size: 11px;")
        self._source_scene_label.hide()
        layout.addWidget(self._source_scene_label)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(4)
        self._content_layout.addStretch()
        scroll.setWidget(self._content_widget)
        layout.addWidget(scroll)

        # Batch action bar
        batch_layout = QHBoxLayout()
        batch_layout.addWidget(QLabel("批量操作："))

        approve_all_btn = QPushButton("全部批准")
        approve_all_btn.setStyleSheet(
            "QPushButton { padding: 4px 12px; background: #27ae60; color: white; "
            "border: none; border-radius: 3px; }"
            "QPushButton:hover { background: #2ecc71; }"
        )
        approve_all_btn.clicked.connect(self._approve_all)
        batch_layout.addWidget(approve_all_btn)

        reject_all_btn = QPushButton("全部拒绝")
        reject_all_btn.setStyleSheet(
            "QPushButton { padding: 4px 12px; background: #c0392b; color: white; "
            "border: none; border-radius: 3px; }"
            "QPushButton:hover { background: #e74c3c; }"
        )
        reject_all_btn.clicked.connect(self._reject_all)
        batch_layout.addWidget(reject_all_btn)

        batch_layout.addStretch()

        add_fact_btn = QPushButton("+ 手动添加事实")
        add_fact_btn.setStyleSheet(
            "QPushButton { padding: 4px 12px; background: #555; color: #eee; "
            "border: 1px solid #777; border-radius: 3px; }"
            "QPushButton:hover { background: #666; }"
        )
        add_fact_btn.clicked.connect(self._on_add_manual_fact)
        batch_layout.addWidget(add_fact_btn)

        layout.addLayout(batch_layout)

        # Confirm button
        confirm_layout = QHBoxLayout()
        confirm_layout.addStretch()

        self._confirm_btn = QPushButton("发布场景")
        self._confirm_btn.setStyleSheet(
            "QPushButton { padding: 8px 24px; background: #27ae60; color: white; "
            "border: none; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #2ecc71; }"
        )
        self._confirm_btn.clicked.connect(self._on_confirm)
        confirm_layout.addWidget(self._confirm_btn)

        layout.addLayout(confirm_layout)
        self.hide()

    def show_items(
        self,
        source_scene_id: str,
        source_revision_id: str,
        facts: list[dict],
        state_changes: list[dict],
    ) -> None:
        """Populate the panel with extracted facts and state changes."""
        self._source_scene_id = source_scene_id
        self._source_revision_id = source_revision_id
        self._facts = facts
        self._state_changes = state_changes
        self._source_scene_label.setText(f"来源场景：{source_scene_id}")
        self._source_scene_label.show()
        self._fact_checkboxes.clear()
        self._change_checkboxes.clear()
        self._change_locations.clear()
        self._change_editors.clear()
        self._populate()
        self.show()

    def clear_and_hide(self) -> None:
        """Clear and hide the panel."""
        self._source_scene_id = ""
        self._source_revision_id = ""
        self._facts = []
        self._state_changes = []
        self._source_scene_label.clear()
        self._source_scene_label.hide()
        self._fact_checkboxes.clear()
        self._change_checkboxes.clear()
        self._change_locations.clear()
        self._change_editors.clear()
        self._clear_content()
        self.hide()

    def _clear_content(self) -> None:
        """Remove all widgets from the content layout."""
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _populate(self) -> None:
        self._clear_content()
        self._fact_checkboxes.clear()
        self._change_checkboxes.clear()
        self._change_locations.clear()
        self._change_editors.clear()

        # Facts section
        if not self._facts and not self._state_changes:
            self._content_layout.insertWidget(
                0, QLabel("没有提取到新的设定或状态变更。仍可发布此场景。")
            )
        if self._facts:
            facts_header = QLabel(
                f"<b>提取的事实</b> <span style='color:#888;'>({len(self._facts)} 条)</span>"
            )
            self._content_layout.insertWidget(
                self._content_layout.count() - 1, facts_header
            )

            for i, fact in enumerate(self._facts):
                fact_widget = self._make_fact_row(i, fact)
                self._content_layout.insertWidget(
                    self._content_layout.count() - 1, fact_widget
                )

        # State changes section
        if self._state_changes:
            changes_header = QLabel(
                f"<b>角色状态变更</b> <span style='color:#888;'>({len(self._state_changes)} 条)</span>"
            )
            self._content_layout.insertWidget(
                self._content_layout.count() - 1, changes_header
            )

            for i, change in enumerate(self._state_changes):
                change_widget = self._make_change_row(i, change)
                self._content_layout.insertWidget(
                    self._content_layout.count() - 1, change_widget
                )

    def _make_fact_row(self, index: int, fact: dict) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 2, 4, 2)

        cb = QCheckBox()
        cb.setChecked(True)
        self._fact_checkboxes.append(cb)
        layout.addWidget(cb)

        desc = fact.get("description", "")
        category = fact.get("category", "world")
        confidence = fact.get("confidence", 1.0)
        source = fact.get("source_excerpt", "")

        # Category badge
        badge_colors = {"world": "#3498db", "character": "#e67e22", "plot": "#9b59b6"}
        badge = QLabel(f" {category} ")
        badge.setStyleSheet(
            f"background: {badge_colors.get(category, '#555')}; color: white; "
            "border-radius: 3px; font-size: 10px; padding: 1px 4px;"
        )
        layout.addWidget(badge)

        # Description (editable)
        desc_edit = QLineEdit(desc)
        desc_edit.setStyleSheet(
            "background: #3a3a3a; color: #eee; border: 1px solid #555; padding: 2px;"
        )
        desc_edit.textChanged.connect(
            lambda text, i=index: self._facts.__setitem__(
                i, {**self._facts[i], "description": text}
            )
        )
        layout.addWidget(desc_edit, stretch=1)

        # Confidence
        conf_label = QLabel(f"信:{confidence:.0%}")
        conf_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(conf_label)

        # Source tooltip
        if source:
            row.setToolTip(f"原文出处: {source[:200]}")

        return row

    def _make_change_row(self, index: int, change: dict) -> QWidget:
        row = QWidget()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(4, 2, 4, 2)

        name = change.get("character_name", "未知")
        name_label = QLabel(f"<b>{name}</b>")
        name_label.setStyleSheet("color: #e67e22;")
        layout.addWidget(name_label)

        changes_list = change.get("changes", [])
        for change_index, item in enumerate(changes_list):
            change_row = QWidget()
            change_layout = QHBoxLayout(change_row)
            change_layout.setContentsMargins(16, 0, 0, 0)
            cb = QCheckBox()
            cb.setChecked(True)
            self._change_checkboxes.append(cb)
            self._change_locations.append((index, change_index))
            change_layout.addWidget(cb)

            change_type = item.get("type", "")
            value_key = "fact"
            label = change_type
            if change_type == "set_field":
                value_key = "value"
                label = item.get("field", "")
            elif change_type == "relationship_change":
                value_key = "relationship"
                label = f"关系 {item.get('target_character_id', '')}"
            elif change_type == "knowledge_add":
                label = "+知识"
            elif change_type == "knowledge_remove":
                label = "-知识"
            elif change_type == "secret_add":
                label = "+秘密"
            elif change_type == "secret_remove":
                label = "-秘密"
            change_layout.addWidget(QLabel(label))

            editor = QLineEdit(str(item.get(value_key, "")))
            editor.textChanged.connect(
                lambda text, proposal=index, change_no=change_index, key=value_key:
                self._set_change_value(proposal, change_no, key, text)
            )
            self._change_editors.append(editor)
            change_layout.addWidget(editor, stretch=1)
            layout.addWidget(change_row)

        if not changes_list:
            cb = QCheckBox("批准旧格式状态变更")
            cb.setChecked(True)
            self._change_checkboxes.append(cb)
            self._change_locations.append((index, None))
            layout.addWidget(cb)

        return row

    def _set_change_value(
        self, proposal_index: int, change_index: int, key: str, value: str
    ) -> None:
        self._state_changes[proposal_index]["changes"][change_index][key] = value

    def _approve_all(self) -> None:
        for cb in self._fact_checkboxes + self._change_checkboxes:
            cb.setChecked(True)

    def _reject_all(self) -> None:
        for cb in self._fact_checkboxes + self._change_checkboxes:
            cb.setChecked(False)

    def _on_add_manual_fact(self) -> None:
        """Add a blank manual fact entry."""
        new_fact: dict = {
            "description": "",
            "category": "world",
            "confidence": 1.0,
            "source_excerpt": "[手动添加]",
        }
        self._facts.append(new_fact)
        self._populate()

    def _on_confirm(self) -> None:
        """Emit approved facts and state changes."""
        approved_facts = [
            self._facts[i]
            for i, cb in enumerate(self._fact_checkboxes)
            if cb.isChecked()
        ]
        selected: dict[int, list[dict] | None] = {}
        for (proposal_index, change_index), cb in zip(
            self._change_locations, self._change_checkboxes
        ):
            if not cb.isChecked():
                continue
            if change_index is None:
                selected[proposal_index] = None
            elif proposal_index not in selected:
                selected[proposal_index] = [
                    self._state_changes[proposal_index]["changes"][change_index]
                ]
            elif selected[proposal_index] is not None:
                selected[proposal_index].append(
                    self._state_changes[proposal_index]["changes"][change_index]
                )
        approved_changes = []
        for proposal_index, changes in selected.items():
            proposal = self._state_changes[proposal_index]
            approved_changes.append(
                proposal if changes is None else {**proposal, "changes": changes}
            )
        self.approval_batch_approved.emit(
            self._source_scene_id,
            self._source_revision_id,
            approved_facts,
            approved_changes,
        )
