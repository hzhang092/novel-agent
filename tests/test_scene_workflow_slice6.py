from types import SimpleNamespace

import pytest

from app.application.errors import OperationBlockedError
from app.application.scene_workflow import (
    SceneWorkflow,
    SceneWorkflowObserver,
    choose_resume_chapter,
    prose_instruction_requires_plan_patch,
    resolve_chapter_target,
)
from app.pipeline.agents.writer import (
    WriterAgent,
    count_chinese_characters,
    provider_target_warning,
)
from app.pipeline.pipeline import GenerationResult
from app.pipeline.pipeline import ScenePipeline
from app.providers.base import MockProvider
from app.storage.models import (
    ChapterLength,
    ChapterOutline,
    Project,
    SceneGenerationRecord,
    SceneOutline,
    ScenePlan,
    VolumeOutline,
)
from app.storage.project_files import (
    create_project,
    save_project,
    save_scene_generation_record,
    save_volume_outline,
    set_active_scene_prose_version,
)


def _project_with_chapter(tmp_path, *, chapter_id="chapter-1", target_word_count=3000):
    project_dir = create_project(
        tmp_path,
        Project(title="Story", chapter_length=ChapterLength(preset="short")),
    )
    save_volume_outline(
        project_dir,
        VolumeOutline(
            id="volume-1",
            chapters=[
                ChapterOutline(
                    id=chapter_id,
                    target_word_count=target_word_count,
                    scenes=[SceneOutline(id=f"scene-{chapter_id}")],
                )
            ],
        ),
    )
    return project_dir


def test_length_defaults_resolve_to_chinese_character_targets():
    project = Project(title="Story", chapter_length=ChapterLength(preset="short"))

    assert ChapterLength(preset="short").resolved_target == 2000
    assert ChapterLength(preset="standard").resolved_target == 3000
    assert ChapterLength(preset="long").resolved_target == 5000
    assert resolve_chapter_target(project, ChapterOutline(target_word_count=3000)) == 2000
    assert resolve_chapter_target(project, ChapterOutline(target_word_count=5000)) == 5000
    assert resolve_chapter_target(
        project,
        ChapterOutline(
            chapter_length_override=ChapterLength(preset="standard")
        ),
    ) == 3000
    assert resolve_chapter_target(
        project,
        ChapterOutline(target_word_count=3000),
        ChapterLength(preset="custom", target_chinese_characters=4200),
    ) == 4200


def test_character_count_and_provider_target_warning():
    assert count_chinese_characters("中A文，\n字") == 3

    provider = SimpleNamespace(model="tiny", max_output_characters=2000)
    assert "tiny" in provider_target_warning(provider, 3000)
    assert provider_target_warning(provider, 2000) == ""
    token_provider = SimpleNamespace(model="token-model", max_output_tokens=4000)
    assert "2000" in provider_target_warning(token_provider, 3000)


@pytest.mark.asyncio
async def test_writer_makes_one_provider_call_without_stitching():
    class RecordingProvider(MockProvider):
        def __init__(self):
            super().__init__(stream_tokens=["一段完整正文"])
            self.calls = 0
            self.max_tokens = 0

        async def generate_stream(self, *args, **kwargs):
            self.calls += 1
            self.max_tokens = kwargs["max_tokens"]
            async for token in super().generate_stream(*args, **kwargs):
                yield token

    provider = RecordingProvider()
    result = []
    async for token in WriterAgent().generate_stream(provider, {}, target_characters=3000):
        result.append(token)

    assert result == ["一段完整正文"]
    assert provider.calls == 1
    assert provider.max_tokens == 6000
    assert "加强现场的紧张感" in WriterAgent().build_prompt(
        {"revision_instruction": "加强现场的紧张感"}
    )


@pytest.mark.asyncio
async def test_regeneration_skips_planner_checkpoint_and_passes_revision_instruction(
    tmp_path,
):
    project_dir = _project_with_chapter(tmp_path)
    plan = ScenePlan(scene_id="scene-chapter-1", scene_goal="找到出口")
    seen = {}

    class Engine:
        def assemble(self, *_args):
            return {}

    class Planner:
        last_usage = None

        async def generate(self, *_args):
            raise AssertionError("regeneration must not call planner")

    class Writer:
        async def generate_stream(self, _provider, context, **_kwargs):
            seen.update(context)
            yield "正文"

    class Reviewer:
        last_usage = None

        async def generate(self, *_args):
            from app.storage.models import ReviewResult

            return ReviewResult(overall_pass=True)

    pipeline = ScenePipeline()
    pipeline._engine = Engine()
    pipeline._planner = Planner()
    pipeline._writer = Writer()
    pipeline._reviewer = Reviewer()
    checkpoints = []
    final = None
    provider = MockProvider()

    async for _token, result in pipeline.generate_stream(
        project_dir,
        "scene-chapter-1",
        provider,
        provider,
        provider,
        provider,
        approved_plan=plan,
        revision_instruction="加强现场的紧张感",
        target_characters=3000,
        on_plan_ready=lambda value: checkpoints.append(value),
    ):
        final = result or final

    assert checkpoints == []
    assert seen["revision_instruction"] == "加强现场的紧张感"
    assert final.plan == plan


@pytest.mark.asyncio
async def test_capacity_warning_is_emitted_before_writer_pipeline_starts(tmp_path):
    project_dir = _project_with_chapter(tmp_path)
    providers = [MockProvider() for _ in range(4)]
    providers[2].model = "small-writer"
    providers[2].max_output_characters = 1000
    warnings = []

    class Pipeline:
        async def generate_stream(self, *_args, **_kwargs):
            assert warnings
            yield None, GenerationResult(
                scene_id="scene-chapter-1", prose="正文"
            )

    workflow = SceneWorkflow(
        project_dir,
        provider_loader=lambda: tuple(providers),
        pipeline_factory=Pipeline,
    )
    workflow.start(
        "scene-chapter-1",
        "chapter-1",
        SceneWorkflowObserver(length_warning=warnings.append),
        target_characters=3000,
    )
    await workflow.task

    assert "small-writer" in warnings[0]


def test_event_character_and_hook_instructions_need_a_plan_patch():
    assert prose_instruction_requires_plan_patch("把事件改成主角杀死守卫")
    assert prose_instruction_requires_plan_patch("让林轩改为第一人称并换一个结尾钩子")
    assert not prose_instruction_requires_plan_patch("加强现场的紧张感")
    assert not prose_instruction_requires_plan_patch("让人物描写更细腻")


def test_generation_blocks_plan_sensitive_instruction_without_patch(tmp_path):
    project_dir = _project_with_chapter(tmp_path)

    with pytest.raises(OperationBlockedError, match="计划补丁"):
        SceneWorkflow(project_dir).start(
            "scene-chapter-1",
            "chapter-1",
            SceneWorkflowObserver(),
            instruction="把事件改成主角杀死守卫",
        )


@pytest.mark.asyncio
async def test_regeneration_reuses_plan_and_keeps_published_revision(tmp_path):
    project_dir = _project_with_chapter(tmp_path)
    plan = ScenePlan(scene_id="scene-chapter-1", scene_goal="找到出口")
    published = SceneGenerationRecord(
        scene_id="scene-chapter-1",
        revision_number=1,
        status="current",
        scene_plan=plan.model_dump(mode="json"),
        draft_text="已发布正文",
        final_text="已发布正文",
    )
    save_scene_generation_record(project_dir, published)
    (project_dir / "scenes" / "chapter-1" / "scene-chapter-1.v1.md").write_text(
        "已发布正文", encoding="utf-8"
    )
    set_active_scene_prose_version(
        project_dir, "chapter-1", "scene-chapter-1", "v1", published.revision_id
    )

    class Pipeline:
        def __init__(self):
            self.approved_plan = None

        async def generate_stream(self, *_args, **kwargs):
            self.approved_plan = kwargs["approved_plan"]
            yield None, GenerationResult(
                scene_id="scene-chapter-1", plan=self.approved_plan, prose="另一版正文"
            )

    pipeline = Pipeline()
    workflow = SceneWorkflow(project_dir, pipeline_factory=lambda: pipeline)
    workflow.regenerate(
        "scene-chapter-1",
        published,
        SceneWorkflowObserver(),
    )
    await workflow.task

    assert pipeline.approved_plan == plan
    draft = workflow.state.draft_record
    assert draft.status == "draft"
    assert draft.revision_number == 2
    assert draft.scene_plan == published.scene_plan
    assert workflow.state.selected_revision == draft.revision_id
    assert (
        (project_dir / "scenes" / "chapter-1" / "scene-chapter-1.v1.md").read_text(
            encoding="utf-8"
        )
        == "已发布正文"
    )


@pytest.mark.asyncio
async def test_save_edited_prose_creates_draft_without_analysis(tmp_path):
    project_dir = _project_with_chapter(tmp_path)
    source = SceneGenerationRecord(
        scene_id="scene-chapter-1",
        revision_number=1,
        scene_plan=ScenePlan(
            scene_id="scene-chapter-1", scene_goal="找到出口"
        ).model_dump(mode="json"),
        draft_text="旧正文",
    )
    save_scene_generation_record(project_dir, source)
    memories = []
    workflow = SceneWorkflow(project_dir, pipeline_factory=object)

    record = await workflow.save_edited_draft(
        "手工修改后的正文",
        source,
        SceneWorkflowObserver(memory=lambda *args: memories.append(args)),
        analyze=False,
    )

    assert record.status == "draft"
    assert record.draft_text == "手工修改后的正文"
    assert not record.review_overridden
    assert memories == []


def test_publish_uses_selected_revision_and_memory(tmp_path, monkeypatch):
    workflow = SceneWorkflow(tmp_path)
    workflow.select_revision("revision-2")
    workflow.set_memory_selections([{"description": "fact"}], [{"character_id": "c1"}])
    captured = {}

    def publish(project_dir, scene_id, revision_id, facts, changes, bus):
        captured.update(
            scene_id=scene_id,
            revision_id=revision_id,
            facts=facts,
            changes=changes,
            bus=bus,
        )

    monkeypatch.setattr("app.storage.timeline_repository.publish_scene_revision", publish)
    workflow.publish("scene-1")

    assert captured == {
        "scene_id": "scene-1",
        "revision_id": "revision-2",
        "facts": [{"description": "fact"}],
        "changes": [{"character_id": "c1"}],
        "bus": None,
    }


def test_resume_priority_is_last_active_then_review_then_draft_then_unwritten(tmp_path):
    project_dir = create_project(tmp_path, Project(title="Story"))
    chapters = [
        ChapterOutline(id=f"chapter-{n}", needs_review=n == 3, scenes=[SceneOutline(id=f"scene-{n}")])
        for n in range(1, 5)
    ]
    save_volume_outline(project_dir, VolumeOutline(id="volume-1", chapters=chapters))

    save_project(project_dir, Project(title="Story", last_active_chapter_id="chapter-4"))
    assert choose_resume_chapter(project_dir) == "chapter-4"

    save_project(project_dir, Project(title="Story"))
    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(scene_id="scene-2", status="draft", revision_number=1),
    )
    (project_dir / "scenes" / "chapter-2" / "scene-2.v1.md").write_text(
        "legacy draft", encoding="utf-8"
    )
    assert choose_resume_chapter(project_dir) == "chapter-3"

    chapters[2].needs_review = False
    save_volume_outline(project_dir, VolumeOutline(id="volume-1", chapters=chapters))
    assert choose_resume_chapter(project_dir) == "chapter-2"

    (project_dir / "scenes" / "chapter-2" / "scene-2.v1.gen.json").unlink()
    assert choose_resume_chapter(project_dir) == "chapter-2"
    (project_dir / "scenes" / "chapter-2" / "scene-2.v1.md").unlink(missing_ok=True)
    assert choose_resume_chapter(project_dir) == "chapter-1"
