"""Project-scoped scene generation lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.application.errors import OperationBlockedError


class ProjectRunGuard:
    """One non-waiting generation lease for a project."""

    def __init__(self) -> None:
        self._owner: str | None = None

    @property
    def active_owner(self) -> str | None:
        return self._owner

    def acquire(self, owner: str) -> bool:
        if self._owner is not None:
            return False
        self._owner = owner
        return True

    def release(self, owner: str) -> None:
        if self._owner == owner:
            self._owner = None


@dataclass
class SceneWorkflowState:
    scene_id: str | None = None
    chapter_id: str | None = None
    planner_decision: dict[str, Any] | None = None
    artifacts: list[Any] = field(default_factory=list)
    partial_prose: str = ""
    draft_record: Any = None
    selected_revision: str | None = None
    memory_facts: list[dict] = field(default_factory=list)
    memory_changes: list[dict] = field(default_factory=list)
    active: bool = False
    source_revisions: dict[str, Any] = field(default_factory=dict)


class SceneWorkflow:
    """Owns scene-run state; Qt presentations only render and command it."""

    def __init__(self, project_dir: Path, *, event_bus: object | None = None) -> None:
        self.project_dir = Path(project_dir)
        self.event_bus = event_bus
        self.run_guard = ProjectRunGuard()
        self.state = SceneWorkflowState()
        self._task: Any = None

    def start(
        self,
        scene_id: str,
        chapter_id: str | None = None,
        source_revisions: dict[str, Any] | None = None,
    ) -> None:
        if not self.run_guard.acquire("scene_workflow"):
            raise OperationBlockedError("Another project generation is already active")
        self.state = SceneWorkflowState(
            scene_id=scene_id,
            chapter_id=chapter_id,
            active=True,
            source_revisions=source_revisions or {},
        )

    def receive_plan(self, plan: dict[str, Any]) -> None:
        self.state.planner_decision = plan

    def append_prose(self, text: str) -> None:
        self.state.partial_prose += text

    def add_artifact(self, artifact: Any) -> None:
        self.state.artifacts.append(artifact)

    def save_draft(self, record: Any) -> None:
        self.state.draft_record = record
        self.state.selected_revision = getattr(record, "revision_id", None)

    def select_revision(self, revision_id: str) -> None:
        self.state.selected_revision = revision_id

    def set_memory_selections(
        self, facts: list[dict], changes: list[dict]
    ) -> None:
        self.state.memory_facts = facts
        self.state.memory_changes = changes

    def finish(self) -> None:
        self.state.active = False
        self._task = None
        self.run_guard.release("scene_workflow")

    def cancel(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self.finish()

    def set_task(self, task: Any) -> None:
        self._task = task

    def retry(self) -> str | None:
        return self.state.scene_id

    def publish(
        self,
        scene_id: str,
        revision_id: str,
        approved_facts: list[dict],
        approved_changes: list[dict],
    ) -> None:
        """Publish through the existing atomic revision seam."""
        from app.storage.timeline_repository import publish_scene_revision

        publish_scene_revision(
            self.project_dir,
            scene_id,
            revision_id,
            approved_facts,
            approved_changes,
            self.event_bus,
        )
