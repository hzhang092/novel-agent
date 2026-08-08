import asyncio

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

import app.ui.quick_story_view as quick_story_view
from app.application.errors import StoryDesignerProviderError
from app.application.project_context import build_project_application
from app.application.story_designer import StoryDesignerService
from app.providers.base import MockProvider
from app.storage.bible_models import TerminologyElement, WorldOverview
from app.storage.models import (
    Character,
    CharacterCore,
    CharacterState,
    ChapterOutline,
    Project,
    ProviderConfig,
    SceneOutline,
    StoryBootstrap,
    StoryBrief,
    StoryProposal,
    StyleGuide,
    VolumeOutline,
)
from app.storage.project_files import (
    create_project,
    create_quick_project,
    load_planning,
    load_project,
    save_volume_outline,
)
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


def _bootstrap() -> StoryBootstrap:
    characters = [
        Character(core=CharacterCore(id=f"quick-{index}", name=f"角色{index}"), state=CharacterState(character_id=f"quick-{index}"))
        for index in range(2)
    ]
    return StoryBootstrap(
        overview=WorldOverview(geography="城市", rules=["旧规则"]),
        elements=[TerminologyElement(id="quick-term", name="旧术语", definition="旧定义")],
        characters=characters, style=StyleGuide(tone="旧语气", reference_passages=["高级字段"]),
        arcs=[VolumeOutline(id="quick-arc", title="第一弧", chapters=[ChapterOutline(id="quick-chapter", scenes=[SceneOutline(id="quick-scene")])])],
    )


def _button(view: QuickStoryView, text: str) -> QPushButton:
    return next(button for button in view.findChildren(QPushButton) if button.text() == text)


def test_story_view_saves_brief_and_none_romance_clears_romance_chip(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="故事"))
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(build_project_application(project_dir))

    view._chips["relationship_tags"]["恋人"] .setChecked(True)
    view.romance_combo.setCurrentIndex(view.romance_combo.findData("none"))
    view.target_combo.setCurrentIndex(view.target_combo.findData("ongoing"))
    view.ending_edit.setText("可调整的远方")
    qtbot.mouseClick(_button(view, "保存草稿"), Qt.MouseButton.LeftButton)

    brief = load_planning(project_dir).story_brief
    assert brief is not None
    assert view.action_status_label.text() == "故事意向已保存"
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


def test_story_brief_conditional_rows_follow_selected_modes_and_persist_cleanly(
    tmp_path, qtbot
):
    project_dir = create_project(tmp_path, Project(title="条件字段"))
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(build_project_application(project_dir))

    assert view.custom_target.isHidden()
    assert view.ending_edit.isHidden()
    assert view.chapter_chars.isHidden()

    view.target_combo.setCurrentIndex(view.target_combo.findData("custom"))
    assert not view.custom_target.isHidden()
    assert view.ending_edit.isHidden()
    view.target_combo.setCurrentIndex(view.target_combo.findData("ongoing"))
    assert view.custom_target.isHidden()
    assert not view.ending_edit.isHidden()
    view.chapter_combo.setCurrentIndex(view.chapter_combo.findData("custom"))
    assert not view.chapter_chars.isHidden()

    view.custom_target.setValue(77)
    view.chapter_chars.setValue(4321)
    view._save_brief()
    saved = load_planning(project_dir).story_brief
    assert saved.custom_target_chapters is None
    assert saved.chapter_length.target_chinese_characters == 4321
    assert load_planning(project_dir).provisional_destination == ""

    view.target_combo.setCurrentIndex(view.target_combo.findData("custom"))
    view.chapter_combo.setCurrentIndex(view.chapter_combo.findData("standard"))
    view.chapter_chars.setValue(9999)
    view._save_brief()
    saved = load_planning(project_dir).story_brief
    assert saved.custom_target_chapters == 77
    assert saved.chapter_length.target_chinese_characters == 3000

    reopened = QuickStoryView()
    qtbot.addWidget(reopened)
    reopened.bind_application(build_project_application(project_dir))
    assert not reopened.custom_target.isHidden()
    assert reopened.chapter_chars.isHidden()


def test_story_projection_offers_outline_continuation_only_with_chapters(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="继续"))
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(build_project_application(project_dir))

    assert view.continue_outline_button.isHidden()

    save_volume_outline(
        project_dir,
        VolumeOutline(
            id="volume-1",
            chapters=[
                ChapterOutline(
                    id="chapter-1",
                    scenes=[SceneOutline(id="scene-1")],
                )
            ],
        ),
    )
    view.refresh_quick_projection()

    assert not view.continue_outline_button.isHidden()
    assert view.continue_outline_button.isEnabled()
    with qtbot.waitSignal(view.outline_requested, timeout=1000):
        view.continue_outline_button.click()


@pytest.mark.asyncio
async def test_story_view_proposal_actions_keep_project_folder_and_adopt_title(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="固定目录"))
    application = build_project_application(project_dir)
    application.story_designer._provider_factory = lambda: MockProvider(structured_response=_proposal())
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(application)
    qtbot.mouseClick(view.generate_button, Qt.MouseButton.LeftButton)
    await view._proposal_task

    assert "暂定远方" in view.proposal_label.text()
    assert view.action_status_label.text() == "故事提案已生成"
    await view._adopt_proposal()

    assert load_project(project_dir).title == "生成标题"
    assert project_dir.name == "固定目录"


@pytest.mark.asyncio
async def test_generating_proposal_reports_progress_and_reenables_actions(tmp_path, qtbot):
    started = asyncio.Event()
    release = asyncio.Event()

    class WaitingProvider(MockProvider):
        async def generate_structured(self, *args, **kwargs):
            started.set()
            await release.wait()
            return await super().generate_structured(*args, **kwargs)

    project_dir = create_project(tmp_path, Project(title="进度提示"))
    application = build_project_application(project_dir)
    application.story_designer._provider_factory = lambda: WaitingProvider(
        structured_response=_proposal()
    )
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(application)

    qtbot.mouseClick(view.generate_button, Qt.MouseButton.LeftButton)
    await started.wait()

    assert view.action_status_label.text() == "正在生成故事提案…"
    assert not view.save_button.isEnabled()
    assert not view.generate_button.isEnabled()

    release.set()
    await view._proposal_task

    assert view.action_status_label.text() == "故事提案已生成"
    assert view.save_button.isEnabled()
    assert not view.generate_button.isEnabled()


@pytest.mark.asyncio
async def test_adjusting_proposal_uses_shared_busy_state_and_restores_draft_actions(
    tmp_path, qtbot
):
    started = asyncio.Event()
    release = asyncio.Event()

    class WaitingProvider(MockProvider):
        async def generate_structured(self, *args, **kwargs):
            started.set()
            await release.wait()
            return await super().generate_structured(*args, **kwargs)

    project_dir = create_project(tmp_path, Project(title="调整进度"))
    application = build_project_application(project_dir)
    application.story_designer._provider_factory = lambda: MockProvider(
        structured_response=_proposal()
    )
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(application)
    await view._generate_proposal()

    application.story_designer._provider_factory = lambda: WaitingProvider(
        structured_response=_proposal()
    )
    view.adjust_edit.setText("更紧张")
    view.adjust_button.click()
    await started.wait()

    assert view.action_status_label.text() == "正在调整故事提案…"
    assert not view.save_button.isEnabled()
    assert not view.adopt_button.isEnabled()
    assert not view.adjust_button.isEnabled()
    assert not view.another_button.isEnabled()
    active_task = view._proposal_task
    view.another_button.click()
    assert view._proposal_task is active_task

    release.set()
    await active_task

    assert view.action_status_label.text() == "故事提案已调整"
    assert view.adopt_button.isEnabled()
    assert view.adjust_button.isEnabled()
    assert view.another_button.isEnabled()


@pytest.mark.asyncio
async def test_bootstrap_generation_keeps_busy_status_persistent_across_stage_changes(
    tmp_path, qtbot
):
    started = asyncio.Event()
    release = asyncio.Event()

    class WaitingProvider(MockProvider):
        async def generate_structured(self, *args, **kwargs):
            started.set()
            await release.wait()
            return await super().generate_structured(*args, **kwargs)

    project_dir = create_project(tmp_path, Project(title="启动包进度"))
    application = build_project_application(project_dir)
    application.story_designer._provider_factory = lambda: MockProvider(
        structured_response=_proposal()
    )
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(application)
    await view._generate_proposal()
    await view._adopt_proposal()

    application.story_designer._provider_factory = lambda: WaitingProvider(
        structured_response=_bootstrap()
    )
    view.bootstrap_button.click()
    await started.wait()

    assert view.action_status_label.text() == "正在生成故事启动包…"
    assert not view.save_button.isEnabled()
    assert not view.bootstrap_button.isEnabled()
    assert not view.approve_bootstrap_button.isEnabled()
    view._set_creation_stage("proposal")
    assert view.action_status_label.text() == "正在生成故事启动包…"
    assert not view.action_status_label.isHidden()

    task = view._proposal_task
    release.set()
    await task

    assert view.action_status_label.text() == "故事启动包已生成"
    assert view.save_bootstrap_button.isEnabled()
    assert view.adjust_bootstrap_button.isEnabled()
    assert view.approve_bootstrap_button.isEnabled()


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
async def test_rebinding_cancels_a_late_proposal_without_updating_the_next_project(tmp_path, qtbot):
    started = asyncio.Event()
    release = asyncio.Event()

    class LateProvider(MockProvider):
        def __init__(self):
            super().__init__(structured_response=_proposal())

        async def generate_structured(self, *args, **kwargs):
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
            return await super().generate_structured(*args, **kwargs)

    first_dir = create_quick_project(tmp_path / "first", "第一本")
    first_application = build_project_application(first_dir)
    first_application.story_designer._provider_factory = LateProvider
    second_dir = create_project(tmp_path / "second", Project(title="第二本"))
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(first_application)
    view.premise_edit.setPlainText("第一本故事")
    view._start_task(view._generate_proposal())
    first_task = view._proposal_task
    await started.wait()

    view.bind_application(build_project_application(second_dir))
    release.set()
    await first_task

    assert load_planning(second_dir).active_draft is None
    assert view.proposal_label.text() == "尚未生成"
    assert view.premise_edit.toPlainText() == ""


@pytest.mark.asyncio
async def test_rebinding_before_a_queued_retry_does_not_run_it_for_the_next_project(
    tmp_path, qtbot, monkeypatch
):
    queued = []
    retries = []

    class RetryBox:
        class Icon:
            Warning = object()

        class ButtonRole:
            AcceptRole = object()
            ActionRole = object()

        class StandardButton:
            Cancel = object()

        def __init__(self, *_args, **_kwargs):
            self.retry_button = object()
            self.settings_button = object()

        def addButton(self, label, *_args):
            return self.retry_button if label == "重试" else self.settings_button

        def exec(self):
            pass

        def clickedButton(self):
            return self.retry_button

    class Timer:
        @staticmethod
        def singleShot(_delay, callback):
            queued.append(callback)

    first_dir = create_quick_project(tmp_path / "first", "第一本")
    first_application = build_project_application(first_dir)
    second_dir = create_project(tmp_path / "second", Project(title="第二本"))
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(first_application)
    monkeypatch.setattr(quick_story_view, "QMessageBox", RetryBox)
    monkeypatch.setattr(quick_story_view, "QTimer", Timer)

    async def retry():
        retries.append(True)

    view._provider_error("失败", retry)
    view.bind_application(build_project_application(second_dir))
    queued.pop()()
    await asyncio.sleep(0)

    assert retries == []


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


@pytest.mark.asyncio
async def test_bootstrap_cards_are_editable_while_advanced_output_is_read_only(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="启动包"))
    application = build_project_application(project_dir)
    application.story_designer._provider_factory = lambda: MockProvider(structured_response=_proposal())
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(application)
    view._save_brief()
    await view._generate_proposal()
    await view._adopt_proposal()
    application.story_designer._provider_factory = lambda: MockProvider(structured_response=_bootstrap())

    await view._generate_bootstrap()

    assert view.bootstrap_advanced.isReadOnly()
    assert view._bootstrap_fields and view._bootstrap_fields[0][0].isEnabled()
    assert view.approve_bootstrap_button.isEnabled()
    assert view.another_button.isHidden()


@pytest.mark.asyncio
async def test_bootstrap_basic_bible_and_style_cards_save_without_touching_advanced_fields(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="编辑启动包"))
    application = build_project_application(project_dir)
    application.story_designer._provider_factory = lambda: MockProvider(structured_response=_proposal())
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(application)
    view._save_brief()
    await view._generate_proposal()
    await view._adopt_proposal()
    application.story_designer._provider_factory = lambda: MockProvider(structured_response=_bootstrap())
    await view._generate_bootstrap()

    fields = {path: field for field, path, _is_list in view._bootstrap_fields}
    fields[("overview", "rules")].setText("新规则、第二条")
    fields[("elements", 0, "name")].setText("新术语")
    fields[("elements", 0, "definition")].setText("新定义")
    fields[("style", "tone")].setText("新语气")
    view._save_bootstrap()
    saved = load_planning(project_dir).active_draft.bootstrap

    assert saved.overview.rules == ["新规则", "第二条"]
    assert saved.elements[0].name == "新术语"
    assert saved.elements[0].definition == "新定义"
    assert saved.style.tone == "新语气"
    assert saved.style.reference_passages == ["高级字段"]


@pytest.mark.asyncio
async def test_invalid_bootstrap_card_stops_adjustment_and_approval(tmp_path, qtbot, monkeypatch):
    project_dir = create_project(tmp_path, Project(title="无效启动包"))
    application = build_project_application(project_dir)
    application.story_designer._provider_factory = lambda: MockProvider(structured_response=_proposal())
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(application)
    await view._generate_proposal()
    await view._adopt_proposal()
    application.story_designer._provider_factory = lambda: MockProvider(structured_response=_bootstrap())
    await view._generate_bootstrap()
    view._add_bootstrap_field("错误角色状态", "wrong-id", ("characters", 0, "state", "character_id"))
    errors = []
    monkeypatch.setattr(view, "_provider_error", errors.append)
    adjusted = []
    approved = []
    monkeypatch.setattr(application.story_designer, "adjust_bootstrap", lambda *_args, **_kwargs: adjusted.append(True))
    monkeypatch.setattr(application.story_designer, "approve_bootstrap", lambda **_kwargs: approved.append(True))

    await view._adjust_bootstrap()
    view._approve_bootstrap()

    assert len(errors) == 2
    assert all(message.startswith("保存失败：") for message in errors)
    assert adjusted == []
    assert approved == []


@pytest.mark.asyncio
async def test_bootstrap_label_says_adopted_after_approval(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="采用启动包"))
    application = build_project_application(project_dir)
    application.story_designer._provider_factory = lambda: MockProvider(structured_response=_proposal())
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(application)
    await view._generate_proposal()
    await view._adopt_proposal()
    application.story_designer._provider_factory = lambda: MockProvider(structured_response=_bootstrap())
    await view._generate_bootstrap()

    view._approve_bootstrap()

    assert view.bootstrap_label.text() == "已采用"
