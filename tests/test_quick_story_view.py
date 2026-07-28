import asyncio

import pytest

from app.application.errors import StoryDesignerProviderError
from app.application.project_context import build_project_application
from app.application.story_designer import StoryDesignerService
from app.providers.base import MockProvider
from app.storage.models import Project, ProviderConfig, StoryBrief, StoryProposal
from app.storage.project_files import create_project, create_quick_project, load_planning, load_project
from app.ui.quick_story_view import QuickStoryView
from app.providers.config import ProviderConfigurationError, get_configured_provider_for_step


def _proposal() -> StoryProposal:
    return StoryProposal(
        title="生成标题",
        logline="一句话",
        main_characters=["甲", "乙"],
        core_conflict="冲突",
        story_promises=["看点一", "看点二", "看点三"],
        ending_direction="暂定远方",
    )


def test_story_view_saves_brief_and_none_romance_clears_romance_chip(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="故事"))
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(build_project_application(project_dir))

    view._chips["relationship_tags"]["恋人"] .setChecked(True)
    view.romance_combo.setCurrentIndex(view.romance_combo.findData("none"))
    view.target_combo.setCurrentIndex(view.target_combo.findData("ongoing"))
    view.ending_edit.setText("可调整的远方")
    view._save_brief()

    brief = load_planning(project_dir).story_brief
    assert brief is not None
    assert "恋人" not in brief.relationship_tags
    assert brief.target_length == "ongoing"
    assert brief.premise == ""
    assert view.ending_edit.text() == "可调整的远方"

    reopened = QuickStoryView()
    qtbot.addWidget(reopened)
    reopened.bind_application(build_project_application(project_dir))
    assert reopened.ending_edit.text() == "可调整的远方"
    assert not reopened.generate_button.isHidden()
    assert not reopened.adopt_button.isEnabled()


def test_story_view_proposal_actions_keep_project_folder_and_adopt_title(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="固定目录"))
    application = build_project_application(project_dir)
    application.story_designer._provider_factory = lambda: MockProvider(structured_response=_proposal())
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(application)
    view._save_brief()

    asyncio.run(view._generate_proposal())
    assert "暂定远方" in view.proposal_label.text()
    asyncio.run(view._adopt_proposal())

    assert load_project(project_dir).title == "生成标题"
    assert project_dir.name == "固定目录"


@pytest.mark.asyncio
async def test_adjusting_or_replacing_an_unchanged_brief_keeps_the_draft_current(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="调整"))
    application = build_project_application(project_dir)
    application.story_designer._provider_factory = lambda: MockProvider(structured_response=_proposal())
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(application)

    await view._generate_proposal()
    first = load_planning(project_dir).active_draft
    assert first is not None
    view.adjust_edit.setText("更黑暗")
    await view._adjust_proposal()
    second = load_planning(project_dir).active_draft
    assert second is not None and second.revision == first.revision + 1
    await view._generate_proposal()
    assert load_planning(project_dir).active_draft.revision == second.revision + 1


def test_custom_tags_round_trip_after_reopen(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="标签"))
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(build_project_application(project_dir))
    view._custom["tone_tags"].setText("第一、第二，第三,第四")
    view._save_brief()

    reopened = QuickStoryView()
    qtbot.addWidget(reopened)
    reopened.bind_application(build_project_application(project_dir))
    reopened._save_brief()

    assert load_planning(project_dir).story_brief.tone_tags == ["第一", "第二", "第三", "第四"]


def test_story_designer_route_never_falls_back_when_missing():
    config = ProviderConfig()
    config.routing.pop("story_designer")

    with pytest.raises(ProviderConfigurationError, match="设置"):
        get_configured_provider_for_step("story_designer", config)


@pytest.mark.asyncio
async def test_cancelled_quick_proposal_keeps_the_resumable_project_folder(tmp_path, qtbot):
    started = asyncio.Event()

    class WaitingProvider(MockProvider):
        async def generate_structured(self, *args, **kwargs):
            started.set()
            await asyncio.Event().wait()

    project_dir = create_quick_project(tmp_path, "临时故事")
    application = build_project_application(project_dir)
    application.story_designer._provider_factory = WaitingProvider
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(application)
    view._start_task(view._generate_proposal())
    await started.wait()
    view.cancel_generation()
    with pytest.raises(asyncio.CancelledError):
        await view._proposal_task

    assert project_dir.is_dir()
    assert load_planning(project_dir).story_brief is not None


@pytest.mark.asyncio
async def test_story_designer_wraps_non_runtime_provider_errors_and_closes(tmp_path):
    class BrokenProvider(MockProvider):
        def __init__(self):
            super().__init__()
            self.closed = False

        async def generate_structured(self, *args, **kwargs):
            raise ValueError("bad response")

        async def close(self):
            self.closed = True

    project_dir = create_project(tmp_path, Project(title="错误"))
    provider = BrokenProvider()
    service = StoryDesignerService(project_dir, provider_factory=lambda: provider)
    service.save_brief(StoryBrief())

    with pytest.raises(StoryDesignerProviderError, match="bad response"):
        await service.generate_proposal()
    assert provider.closed
