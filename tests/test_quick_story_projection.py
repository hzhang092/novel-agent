from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.storage.models import (
    QuickCharacterProjection,
    QuickStoryProjection,
    StoryPatchPreview,
    WorldOverview,
)
from app.ui.quick_story_view import QuickStoryView


def projection() -> QuickStoryProjection:
    return QuickStoryProjection(
        main_characters=[
            QuickCharacterProjection(
                id="hero-1",
                name="林默",
                identity="调查员",
                personality="谨慎",
            )
        ],
        core_setting=WorldOverview(geography="浮空城", rules=["契约不可违"]),
    )


class FakeQuickPlanning:
    def __init__(self) -> None:
        self.preview = StoryPatchPreview(
            operations=[
                {
                    "target": "character",
                    "target_id": "hero-1",
                    "field": "personality",
                    "value": "更谨慎",
                }
            ],
            changes=["主角更谨慎"], consequences=["后续规划沿用新性格"]
        )
        self.applied = []

    def story_projection(self):
        return projection()

    async def generate_story_patch(self, instruction):
        self.instruction = instruction
        return self.preview

    def apply_story_patch(self, preview):
        self.applied.append(preview)

    def cancel_story_patch(self, preview):
        self.cancelled = preview


@pytest.fixture
def fake_application(monkeypatch):
    quick_planning = FakeQuickPlanning()
    application = SimpleNamespace(
        project_dir="unused",
        quick_planning=quick_planning,
        story_bible=SimpleNamespace(
            load_editor_snapshot=lambda: SimpleNamespace(
                bible=SimpleNamespace(
                    elements=[
                        SimpleNamespace(
                            id="power-1",
                            name="契约术",
                            element_type=SimpleNamespace(value="power_system"),
                        )
                    ]
                )
            )
        ),
    )
    monkeypatch.setattr(
        "app.ui.quick_story_view.load_planning",
        lambda _: SimpleNamespace(
            approved_proposal=object(),
            approved_brief=SimpleNamespace(premise="追查契约术失控的真相"),
        ),
    )
    return application


def test_refresh_renders_projection_and_emits_exact_deep_targets(qtbot, fake_application):
    view = QuickStoryView()
    qtbot.addWidget(view)
    view._application = fake_application
    character_spy = QSignalSpy(view.character_requested)
    world_spy = QSignalSpy(view.world_element_requested)

    view.refresh_quick_projection()

    assert "林默" in view.quick_projection_label.text()
    assert "浮空城" in view.quick_projection_label.text()
    assert "追查契约术失控的真相" in view.approved_brief_label.text()
    buttons = view.quick_projection_actions.parentWidget().findChildren(type(view.generate_button))
    next(button for button in buttons if button.text() == "高级角色：林默").click()
    next(button for button in buttons if button.text() == "高级世界设定").click()
    next(button for button in buttons if button.text() == "高级能力：契约术").click()

    assert character_spy.count() == 1
    assert world_spy.count() == 2
    assert character_spy.at(0) == ["hero-1"]
    assert world_spy.at(0) == ["overview"]
    assert world_spy.at(1) == ["power-1"]


def test_existing_canonical_project_does_not_need_guided_planning(
    qtbot, fake_application, monkeypatch
):
    monkeypatch.setattr(
        "app.ui.quick_story_view.load_planning",
        lambda _: SimpleNamespace(
            approved_proposal=None,
            approved_brief=None,
        ),
    )
    view = QuickStoryView()
    qtbot.addWidget(view)
    view._application = fake_application

    view.refresh_quick_projection()

    assert "林默" in view.quick_projection_label.text()
    assert "浮空城" in view.quick_projection_label.text()


@pytest.mark.asyncio
async def test_story_patch_is_reviewed_then_explicitly_applied_or_cancelled(
    qtbot, fake_application
):
    view = QuickStoryView()
    qtbot.addWidget(view)
    view._application = fake_application
    view.refresh_quick_projection()
    view.story_patch_edit.setText("让主角更谨慎")

    await view._generate_story_patch()

    assert "主角更谨慎" in view.story_patch_label.text()
    assert fake_application.quick_planning.applied == []
    view.cancel_story_patch_button.click()
    assert fake_application.quick_planning.applied == []
    assert view.story_patch_label.text() == ""

    await view._generate_story_patch()
    view.apply_story_patch_button.click()
    assert fake_application.quick_planning.applied == [fake_application.quick_planning.preview]
