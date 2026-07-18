"""Dashboard view — project overview with token usage totals."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class DashboardView(QWidget):
    """Project overview showing token usage and project stats."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_dir: Path | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("<h2>总览</h2>")
        layout.addWidget(title)

        # Token card
        token_card = QFrame()
        token_card.setStyleSheet(
            "QFrame { background: #2a2a2a; border: 1px solid #444; border-radius: 6px; padding: 16px; }"
        )
        token_layout = QVBoxLayout(token_card)
        token_layout.setSpacing(8)

        token_header = QLabel("<b>📊 项目 Token 用量</b>")
        token_header.setStyleSheet("color: #eee; font-size: 14px;")
        token_layout.addWidget(token_header)

        self._total_label = QLabel("—")
        self._total_label.setStyleSheet("color: #888; font-size: 24px; font-weight: bold;")
        token_layout.addWidget(self._total_label)

        self._cost_label = QLabel("")
        self._cost_label.setStyleSheet("color: #888; font-size: 12px;")
        token_layout.addWidget(self._cost_label)

        layout.addWidget(token_card)
        layout.addStretch()

    def load_project_dir(self, project_dir: Path) -> None:
        """Set the project directory and refresh the display."""
        self._project_dir = project_dir
        self._refresh()

    def _refresh(self) -> None:
        """Update token totals from project data."""
        if self._project_dir is None:
            self._total_label.setText("—")
            self._cost_label.setText("")
            return

        from app.pipeline.token_tracker import TokenTracker

        tracker = TokenTracker.get()
        total = tracker.get_project_total(self._project_dir)
        if total == 0:
            self._total_label.setText("—")
            self._cost_label.setText("尚未产生 Token 用量")
        else:
            self._total_label.setText(f"{total:,} tokens")
            cost = self._calc_project_cost()
            if cost > 0:
                self._cost_label.setText(f"预估费用: ${cost:.2f} USD")
            else:
                self._cost_label.setText("")

    def _calc_project_cost(self) -> float:
        """Sum cost_usd from all entries in token_usage.jsonl."""
        if self._project_dir is None:
            return 0.0
        filepath = self._project_dir / "token_usage.jsonl"
        if not filepath.exists():
            return 0.0
        total_cost = 0.0
        with open(filepath, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    total_cost += entry.get("cost_usd", 0.0)
                except json.JSONDecodeError:
                    continue
        return total_cost
