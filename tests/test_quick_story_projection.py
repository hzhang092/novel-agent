from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QScrollArea

from app.storage.models import (
    QuickCharacterProjection,
    QuickStoryProjection,
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
        pass

    def story_projection(self):
        return projection()


@pytest.fixture
def fake_application(monkeypatch):
    quick_planning = FakeQuickPlanning()
    application = SimpleNamespace(
        project_dir="unused",
        quick_planning=quick_planning,
        story_designer=SimpleNamespace(
            is_empty_project=lambda: False,
            can_generate_bootstrap=lambda: False,
        ),
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
            approved_proposal=SimpleNamespace(
                revision=2,
                logline="被贬入凡间的剑仙追查契约术失控的真相",
            ),
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
    assert "故事提案 · v2" in view.approved_proposal_label.text()
    assert "被贬入凡间的剑仙" in view.approved_proposal_label.text()
    buttons = view.quick_projection_actions.parentWidget().findChildren(type(view.generate_button))
    next(button for button in buttons if button.text() == "高级角色：林默").click()
    next(button for button in buttons if button.text() == "高级世界设定").click()
    next(button for button in buttons if button.text() == "高级能力：契约术").click()

    assert character_spy.count() == 1
    assert world_spy.count() == 2
    assert character_spy.at(0) == ["hero-1"]
    assert world_spy.at(0) == ["overview"]
    assert world_spy.at(1) == ["power-1"]


def test_quick_story_hides_deferred_controls_and_has_a_scroll_container(
    qtbot, fake_application
):
    view = QuickStoryView()
    qtbot.addWidget(view)

    assert view.findChild(QScrollArea) is not None
    assert not hasattr(view, "generate_brief_button")
    assert not hasattr(view, "story_patch_edit")
    assert not hasattr(view, "generate_story_patch_button")


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


def test_quick_story_shows_only_the_current_creation_stage(qtbot, fake_application, monkeypatch):
    planning = SimpleNamespace(
        story_brief=None,
        provisional_destination="",
        approved_proposal=None,
        approved_brief=None,
        active_draft=None,
    )
    fake_application.story_designer = SimpleNamespace(
        is_empty_project=lambda: True,
        can_generate_bootstrap=lambda: True,
    )
    monkeypatch.setattr("app.ui.quick_story_view.load_planning", lambda _: planning)
    view = QuickStoryView()
    qtbot.addWidget(view)
    view._application = fake_application
    view.bind_application(fake_application)

    assert not view.brief_section.isHidden()
    assert view.proposal_section.isHidden()
    assert view.bootstrap_section.isHidden()
    assert view.projection_section.isHidden()

    proposal = SimpleNamespace(
        revision=2,
        title="标题",
        logline="一句话",
        main_characters=[],
        core_conflict="冲突",
        story_promises=[],
        ending_direction="结局",
    )
    planning.active_draft = SimpleNamespace(
        revision=1,
        proposal=proposal,
    )
    view.bind_application(fake_application)

    assert view.brief_section.isHidden()
    assert not view.proposal_section.isHidden()
    assert view.bootstrap_section.isHidden()
    assert view.projection_section.isHidden()

    planning.active_draft = None
    planning.approved_proposal = proposal
    view.bind_application(fake_application)

    assert view.brief_section.isHidden()
    assert view.proposal_section.isHidden()
    assert not view.bootstrap_section.isHidden()
    assert view.projection_section.isHidden()

    planning.approved_proposal = None
    fake_application.story_designer = SimpleNamespace(
        is_empty_project=lambda: False,
        can_generate_bootstrap=lambda: False,
    )
    view.bind_application(fake_application)

    assert view.brief_section.isHidden()
    assert view.proposal_section.isHidden()
    assert view.bootstrap_section.isHidden()
    assert not view.projection_section.isHidden()
