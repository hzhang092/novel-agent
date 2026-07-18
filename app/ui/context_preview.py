# app/ui/context_preview.py
"""Context Preview panel — badge summary + expandable full context audit."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.domain.bible_relation_catalog import relation_definition
from app.storage.bible_models import BibleRelationKind


_ELEMENT_TYPE_LABELS = {
    "location": "Location",
    "faction": "Faction",
    "historical_event": "Historical event",
    "power_system": "Power system",
    "terminology": "Terminology",
}


class ContextPreviewView(QWidget):
    """Collapsed-by-default panel showing assembled context for audit.

    Badge mode shows counts: "3 facts · 2 character states · 1 summary".
    Expanding reveals the full context dict organized in labeled sections.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._context: dict | None = None
        self._expanded = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Badge bar (always visible when context is set)
        badge_style = (
            "QPushButton { text-align: left; padding: 6px 10px; "
            "border: 1px solid #555; border-radius: 4px; "
            "background: #4a4a4a; color: #eee; }"
        )
        self._badge_button = QPushButton()
        self._badge_button.setFlat(True)
        self._badge_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._badge_button.clicked.connect(self._toggle_expand)
        self._badge_button.setStyleSheet(badge_style)

        self._badge_label = QLabel()
        self._badge_button_layout = QHBoxLayout(self._badge_button)
        self._badge_button_layout.addWidget(self._badge_label)
        self._badge_button_layout.addStretch()
        self._expand_icon = QLabel("▼")
        self._badge_button_layout.addWidget(self._expand_icon)

        layout.addWidget(self._badge_button)

        # Detail panel (hidden by default)
        self._detail_panel = QWidget()
        self._detail_panel.setHidden(True)
        self._detail_layout = QVBoxLayout(self._detail_panel)
        self._detail_layout.setContentsMargins(8, 4, 8, 4)
        self._detail_layout.setSpacing(8)

        self._detail_content = QLabel()
        self._detail_content.setWordWrap(True)
        self._detail_content.setTextFormat(Qt.TextFormat.PlainText)
        self._detail_content.setStyleSheet("color: #aaa; font-size: 11px;")

        self._detail_scroll = QScrollArea()
        self._detail_scroll.setWidgetResizable(True)
        self._detail_scroll.setWidget(self._detail_content)
        self._detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._detail_scroll.setMaximumHeight(400)
        self._detail_layout.addWidget(self._detail_scroll)

        layout.addWidget(self._detail_panel)
        self.hide()

    def set_context(self, context: dict) -> None:
        """Set the assembled context dict and update the badge."""
        self._context = context
        if context is None:
            self.hide()
            return

        self._update_badge(context)
        self._build_detail(context)
        self.show()

    def _update_badge(self, context: dict) -> None:
        """Build badge text from context counts."""
        parts = []

        elements_count = len(context.get("world_context", {}).get("elements", []))
        if elements_count > 0:
            parts.append(f"{elements_count} element{'s' if elements_count != 1 else ''}")

        facts_count = len(context.get("canon_facts", []))
        if facts_count > 0:
            parts.append(f"{facts_count} fact{'s' if facts_count != 1 else ''}")

        char_states = len(context.get("characters", {}).get("major", []))
        if char_states > 0:
            parts.append(
                f"{char_states} character state{'s' if char_states != 1 else ''}"
            )

        summaries_count = len(context.get("recent_summaries", []))
        if summaries_count > 0:
            parts.append(f"{summaries_count} summar{'ies' if summaries_count != 1 else 'y'}")

        if not parts:
            parts.append("context ready")

        self._badge_label.setText(" · ".join(parts))

    def _build_detail(self, context: dict) -> None:
        """Build the full detail text for the expanded panel."""
        lines = []

        # Scene info
        scene = context.get("scene_info", {})
        if scene:
            lines.append("── 场景信息 ──")
            lines.append(f"  场景: {scene.get('scene_title', '')}")
            lines.append(f"  位置: {scene.get('location', '')} · 时间: {scene.get('time', '')}")
            lines.append(f"  POV: {scene.get('pov_character', '')}")
            lines.append(f"  参与者: {', '.join(scene.get('participating_characters', []))}")
            if scene.get("scene_goal"):
                lines.append(f"  目标: {scene.get('scene_goal')}")
            if scene.get("conflict"):
                lines.append(f"  冲突: {scene.get('conflict')}")
            if scene.get("ending_hook"):
                lines.append(f"  断章: {scene.get('ending_hook')}")
            lines.append("")

        # Characters
        chars = context.get("characters", {})
        major = chars.get("major", [])
        supporting = chars.get("supporting", [])
        background = chars.get("background", [])

        if major or supporting or background:
            lines.append("── 角色 ──")
            for mc in major:
                name = mc["core"]["name"]
                state = mc.get("state", {})
                emotion = state.get("current_emotion", "")
                goal = state.get("current_goal", "")
                lines.append(f"  ★ {name} [{emotion}] → {goal}")
            for sc in supporting:
                name = sc.get("name", "")
                rel = sc.get("relationship", "")
                lines.append(f"  · {name}" + (f" ({rel})" if rel else ""))
            for bc in background:
                lines.append(f"  • {bc.get('name', '')}")
            lines.append("")

        # Selected Story Elements
        elements = context.get("world_context", {}).get("elements", [])
        read_points = context.get("world_element_read_points", {})
        if elements:
            lines.append("── Story Elements ──")
            for element in elements:
                label = _ELEMENT_TYPE_LABELS.get(element.get("type", ""), element.get("type", ""))
                lines.append(f"  ✓ {element.get('name', '')} [{label}]")
                for reason in read_points.get(element.get("id", ""), {}).get(
                    "selection_reasons", []
                ):
                    lines.append(f"    Selected because: {self._selection_reason(reason)}")
            lines.append("")

        # World rules
        world = context.get("world_rules", {})
        if world:
            lines.append("── 世界观 ──")
            if world.get("geography"):
                lines.append(f"  地理: {world['geography'][:200]}")
            rules = world.get("rules", [])
            if rules:
                lines.append(f"  规则: {', '.join(rules[:5])}")
            taboos = world.get("taboos", [])
            if taboos:
                lines.append(f"  禁忌: {', '.join(taboos[:5])}")
            ps = world.get("power_system", {})
            if ps and ps.get("realms"):
                lines.append(f"  境界: {' → '.join(ps['realms'])}")
            lines.append("")

        # Canon facts
        facts = context.get("canon_facts", [])
        if facts:
            lines.append(f"── 正典 ({len(facts)}条) ──")
            for f in facts:
                cat = f.get("category", "")
                lines.append(f"  [{cat}] {f.get('description', '')}")
            lines.append("")

        # Recent summaries
        summaries = context.get("recent_summaries", [])
        if summaries:
            lines.append(f"── 最近摘要 ({len(summaries)}篇) ──")
            for s in summaries:
                lines.append(f"  {s.get('scene_id', '')}: {s.get('summary', '')[:120]}")
            lines.append("")

        # Style guide
        style = context.get("style_guide", {})
        if style:
            lines.append("── 风格指南 ──")
            traits = []
            if style.get("pacing"):
                traits.append(f"节奏: {style['pacing']}")
            if style.get("tone"):
                traits.append(f"基调: {style['tone']}")
            if style.get("pov"):
                traits.append(f"视角: {style['pov']}")
            if traits:
                lines.append("  " + " · ".join(traits))
            if style.get("reference_passages"):
                lines.append(f"  参考段落: {len(style['reference_passages'])} 段")
            lines.append("")

        self._detail_content.setText("\n".join(lines))

    @staticmethod
    def _selection_reason(reason: str) -> str:
        if reason == "explicit_scene_reference":
            return "explicit scene reference"
        if reason == "always_include":
            return "always included"
        if reason.startswith("related_to:"):
            try:
                kind = BibleRelationKind(reason.rsplit(":", 1)[1])
                return f"related through {relation_definition(kind).label}"
            except (ValueError, KeyError):
                return "related story element"
        return reason.replace("_", " ")

    def _toggle_expand(self) -> None:
        """Toggle the detail panel visibility."""
        self._expanded = not self._expanded
        self._detail_panel.setHidden(not self._expanded)
        self._expand_icon.setText("▲" if self._expanded else "▼")

    def clear(self) -> None:
        """Clear the context and hide the panel."""
        self._context = None
        self._detail_content.setText("")
        self.hide()
