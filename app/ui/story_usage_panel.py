"""Compact, navigable display of where a Story Bible element is used."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from app.domain.story_usage import ElementUsageSummary, SceneUsage, StoryUsageKind


_GROUPS = (
    (StoryUsageKind.EXPLICIT_OUTLINE, "Explicit outline"),
    (StoryUsageKind.GENERATION_CONTEXT, "Generation context"),
    (StoryUsageKind.PROSE_MENTION, "Mentioned in prose"),
    (StoryUsageKind.CHARACTER_PRESENCE, "Character presence"),
)


class StoryUsagePanel(QWidget):
    """Lists each distinct usage kind, with scene navigation."""

    scene_requested = Signal(str)

    def __init__(
        self, parent: QWidget | None = None, *, title: str = "Story usage"
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(title))
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.itemActivated.connect(self._request_scene)
        layout.addWidget(self._tree)
        self.setVisible(False)

    def set_usage(self, summary: ElementUsageSummary) -> None:
        self._tree.clear()
        self.setVisible(bool(summary.scenes))
        for kind, label in _GROUPS:
            scenes = [scene for scene in summary.scenes if kind in scene.usage_kinds]
            if not scenes:
                continue
            group = QTreeWidgetItem(self._tree, [f"{label} ({len(scenes)})"])
            group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for scene in scenes:
                item = QTreeWidgetItem(group, [self._scene_label(scene)])
                item.setData(0, Qt.ItemDataRole.UserRole, scene.scene_id)
                item.setToolTip(0, self._scene_details(scene))
            group.setExpanded(True)

    def clear(self) -> None:
        self._tree.clear()
        self.setVisible(False)

    @staticmethod
    def _scene_label(scene: SceneUsage) -> str:
        label = f"{scene.scene_order}. {scene.scene_title or scene.scene_id}"
        if scene.location_label:
            label += f" · {scene.location_label}"
        if (
            scene.generated_element_revision is not None
            and scene.current_element_revision is not None
            and scene.generated_element_revision != scene.current_element_revision
        ):
            label += (
                " · revision changed "
                f"({scene.generated_element_revision} → {scene.current_element_revision})"
            )
        return label

    @staticmethod
    def _scene_details(scene: SceneUsage) -> str:
        details = []
        if scene.selection_reasons:
            details.append("Selected because: " + ", ".join(
                reason.replace("_", " ") for reason in scene.selection_reasons
            ))
        if scene.matched_alias:
            details.append(f"Matched: {scene.matched_alias}")
        if scene.location_reason:
            details.append(f"Location inferred because: {scene.location_reason}")
        return "\n".join(details)

    def _request_scene(self, item: QTreeWidgetItem, _column: int) -> None:
        if scene_id := item.data(0, Qt.ItemDataRole.UserRole):
            self.scene_requested.emit(scene_id)
