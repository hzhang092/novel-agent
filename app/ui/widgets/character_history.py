"""CharacterHistoryWidget — displays event-sourced state change history."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.storage.character_events import load_events, load_events_for_scene
from app.storage.models import CharacterStateEvent

SOURCE_LABELS = {
    "ai": "AI",
    "user": "用户",
    "manual_event": "手动",
    "system": "系统",
}
SOURCE_COLORS = {
    "ai": "#3498db",
    "user": "#e67e22",
    "manual_event": "#9b59b6",
    "system": "#95a5a6",
}


class CharacterHistoryWidget(QWidget):
    """Scrollable timeline showing character state changes, grouped by scene."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._char_dir: Path | None = None
        self._current_scene_id: str = ""
        self._events: list[CharacterStateEvent] = []
        self._setup_ui()

    def set_character(self, char_dir: Path, current_scene_id: str = "") -> None:
        """Load events for a character directory and render."""
        self._char_dir = char_dir
        self._current_scene_id = current_scene_id
        self._refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # View toggle
        toggle_layout = QVBoxLayout()
        self._scene_view_btn = QPushButton("场景变化")
        self._scene_view_btn.setCheckable(True)
        self._scene_view_btn.setChecked(True)
        self._scene_view_btn.clicked.connect(lambda: self._switch_view("scene"))
        self._timeline_view_btn = QPushButton("完整历史")
        self._timeline_view_btn.setCheckable(True)
        self._timeline_view_btn.clicked.connect(lambda: self._switch_view("timeline"))
        toggle_layout.addWidget(self._scene_view_btn)
        toggle_layout.addWidget(self._timeline_view_btn)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(8, 8, 8, 8)
        self._content_layout.setSpacing(4)
        self._content_layout.addStretch()
        scroll.setWidget(self._content_widget)

        layout.addLayout(toggle_layout)
        layout.addWidget(scroll)

    def _switch_view(self, view: str) -> None:
        self._scene_view_btn.setChecked(view == "scene")
        self._timeline_view_btn.setChecked(view == "timeline")
        self._render()

    def _refresh(self) -> None:
        if self._char_dir is None:
            return
        self._events = load_events(self._char_dir)
        self._render()

    def _render(self) -> None:
        self._clear_content()
        if self._scene_view_btn.isChecked():
            scene_events = [e for e in self._events if e.scene_id == self._current_scene_id]
            self._render_scene_diff(scene_events)
        else:
            self._render_timeline(self._events)

    def _render_scene_diff(self, events: list[CharacterStateEvent]) -> None:
        if not events:
            self._add_label("该场景无状态变化", "color: #888; font-size: 12px;")
            return

        for event in events:
            if event.invalidated:
                continue
            scene_name = event.scene_id or "故事起点"
            source_badge = SOURCE_LABELS.get(event.source, event.source)
            source_color = SOURCE_COLORS.get(event.source, "#888")

            header = QLabel(
                f"<b>{scene_name}</b> "
                f"<span style='color:{source_color};'>[{source_badge}]</span>"
            )
            header.setStyleSheet("font-size: 13px; padding-top: 4px;")
            self._content_layout.insertWidget(self._content_layout.count() - 1, header)

            for change in event.changes:
                text = self._format_change(change)
                label = QLabel(f"  {text}")
                label.setStyleSheet("color: #ccc; font-size: 12px; padding: 1px 0;")
                self._content_layout.insertWidget(self._content_layout.count() - 1, label)

    def _render_timeline(self, events: list[CharacterStateEvent]) -> None:
        if not events:
            self._add_label("暂无历史记录", "color: #888; font-size: 12px;")
            return

        current_scene: str | None = None
        for event in events:
            if event.scene_id != current_scene:
                current_scene = event.scene_id
                scene_name = event.scene_id or "故事起点"
                scene_label = QLabel(f"<b>━━ {scene_name}</b>")
                scene_label.setStyleSheet("color: #f39c12; padding-top: 8px; font-size: 13px;")
                self._content_layout.insertWidget(self._content_layout.count() - 1, scene_label)

            if event.invalidated:
                inv = QLabel(f"  <i>[已作废]</i>")
                inv.setStyleSheet("color: #c0392b; font-size: 11px;")
                self._content_layout.insertWidget(self._content_layout.count() - 1, inv)
                continue

            source_badge = SOURCE_LABELS.get(event.source, event.source)
            source_color = SOURCE_COLORS.get(event.source, "#888")

            for change in event.changes:
                text = self._format_change(change)
                label = QLabel(
                    f"  <span style='color:{source_color};'>[{source_badge}]</span> {text}"
                )
                label.setStyleSheet("font-size: 12px; padding: 1px 0;")
                self._content_layout.insertWidget(self._content_layout.count() - 1, label)

    def _format_change(self, change) -> str:
        if change.type == "set_field":
            arrow = f"{change.old} → {change.value}" if change.old else change.value
            return f"{change.field}: {arrow}"
        elif change.type == "relationship_change":
            arrow = f"{change.old} → {change.relationship}" if change.old else change.relationship
            return f"关系 [{change.target_character_id}]: {arrow}"
        elif change.type == "knowledge_add":
            return f"+ 知识: {change.fact}"
        elif change.type == "knowledge_remove":
            return f"- 知识: {change.fact}"
        elif change.type == "secret_add":
            return f"+ 秘密: {change.fact}"
        elif change.type == "secret_remove":
            return f"- 秘密: {change.fact}"
        return str(change.type)

    def _add_label(self, text: str, style: str = "") -> None:
        label = QLabel(text)
        if style:
            label.setStyleSheet(style)
        self._content_layout.insertWidget(self._content_layout.count() - 1, label)

    def _clear_content(self) -> None:
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
