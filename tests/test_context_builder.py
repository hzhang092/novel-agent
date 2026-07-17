"""Tests for RetrievalEngine — deterministic context assembly."""
import pytest

from app.storage.models import Project
from app.storage.project_files import create_project


def test_engine_returns_context_dict_for_scene_with_no_data(tmp_path):
    """Even with no characters/facts/summaries, engine returns a valid context dict."""
    from app.pipeline.context_builder import RetrievalEngine

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    engine = RetrievalEngine()
    context = engine.assemble(proj_dir, scene_id="nonexistent-scene")

    assert isinstance(context, dict)
    for key in ["scene_info", "world_rules", "characters", "outline_context",
                 "recent_summaries", "canon_facts", "style_guide"]:
        assert key in context, f"Missing key: {key}"
    assert context["characters"]["major"] == []
    assert context["characters"]["supporting"] == []
    assert context["characters"]["background"] == []


def test_characters_are_tiered_by_tier_in_context(tmp_path):
    """Major chars get full cards, supporting get name+relationship, background get name-only."""
    from app.pipeline.context_builder import RetrievalEngine
    from app.storage.models import (
        Character, CharacterCore, CharacterState,
        ChapterOutline, SceneOutline, VolumeOutline,
    )
    from app.storage.project_files import create_project, save_character, save_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    major_char = Character(
        core=CharacterCore(
            id="char-linxuan", name="林轩", tier="major", personality="坚韧不拔",
            background="孤儿出身", long_term_goal="成为最强",
        ),
        state=CharacterState(
            character_id="char-linxuan", current_emotion="坚定",
            current_goal="通过考核", current_location="广场",
        ),
    )
    supporting_char = Character(
        core=CharacterCore(id="char-su", name="苏清鸾", tier="supporting", personality="清冷高傲", speech_style="简短"),
        state=CharacterState(character_id="char-su", current_relationships={"林轩": "同门"}),
    )
    bg_char = Character(
        core=CharacterCore(id="char-bg", name="杂役弟子甲", tier="background"),
        state=CharacterState(character_id="char-bg"),
    )
    save_character(proj_dir, major_char)
    save_character(proj_dir, supporting_char)
    save_character(proj_dir, bg_char)

    scene = SceneOutline(title="测试场景", participating_character_ids=["char-linxuan", "char-su", "char-bg"])
    chapter = ChapterOutline(title="第一章", scenes=[scene])
    volume = VolumeOutline(title="第一卷", chapters=[chapter])
    save_volume_outline(proj_dir, volume)

    engine = RetrievalEngine()
    context = engine.assemble(proj_dir, scene_id=scene.id)

    chars = context["characters"]
    assert len(chars["major"]) == 1
    assert chars["major"][0]["core"]["name"] == "林轩"
    assert "state" in chars["major"][0]
    assert len(chars["supporting"]) == 1
    assert chars["supporting"][0]["name"] == "苏清鸾"
    assert "relationship" in chars["supporting"][0]
    assert "state" not in chars["supporting"][0]
    assert len(chars["background"]) == 1
    assert chars["background"][0]["name"] == "杂役弟子甲"


def test_pov_character_is_included_without_being_a_participant(tmp_path):
    from app.pipeline.context_builder import RetrievalEngine
    from app.storage.models import (
        Character, CharacterCore, CharacterState,
        ChapterOutline, SceneOutline, VolumeOutline,
    )
    from app.storage.project_files import create_project, save_character, save_volume_outline

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="char-hero", name="林轩", tier="major"),
            state=CharacterState(character_id="char-hero"),
        ),
    )
    scene = SceneOutline(
        id="scene-1",
        title="测试",
        pov_character_id="char-hero",
        participating_character_ids=[],
    )
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            title="第一卷",
            chapters=[ChapterOutline(title="第一章", scenes=[scene])],
        ),
    )

    context = RetrievalEngine().assemble(proj_dir, scene_id="scene-1")

    assert context["characters"]["major"][0]["core"]["id"] == "char-hero"
    assert "state" in context["characters"]["major"][0]
    assert "char-hero" in context["read_points"]


def test_non_participating_characters_are_excluded(tmp_path):
    """Characters not in the scene's participating character ID list are excluded."""
    from app.pipeline.context_builder import RetrievalEngine
    from app.storage.models import (
        Character, CharacterCore, CharacterState,
        ChapterOutline, SceneOutline, VolumeOutline,
    )
    from app.storage.project_files import create_project, save_character, save_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    char_in = Character(
        core=CharacterCore(id="char-linxuan", name="林轩", tier="major"),
        state=CharacterState(character_id="char-linxuan"),
    )
    char_out = Character(
        core=CharacterCore(id="char-bystander", name="路人乙", tier="major"),
        state=CharacterState(character_id="char-bystander"),
    )
    save_character(proj_dir, char_in)
    save_character(proj_dir, char_out)

    scene = SceneOutline(title="测试", participating_character_ids=["char-linxuan"])
    chapter = ChapterOutline(title="第一章", scenes=[scene])
    volume = VolumeOutline(title="第一卷", chapters=[chapter])
    save_volume_outline(proj_dir, volume)

    engine = RetrievalEngine()
    context = engine.assemble(proj_dir, scene_id=scene.id)

    all_names = [
        c["core"]["name"] if "core" in c else c["name"]
        for tier in context["characters"].values()
        for c in tier
    ]
    assert "林轩" in all_names
    assert "路人乙" not in all_names


def test_characters_use_previous_scene_checkpoint_in_context(tmp_path):
    """Regenerating an older scene must not use the latest character state."""
    from app.pipeline.context_builder import RetrievalEngine
    from app.storage.character_state import save_checkpoint
    from app.storage.models import (
        Character, CharacterCore, CharacterState, CharacterStateSnapshot,
        ChapterOutline, SceneOutline, SceneStateCheckpoint, VolumeOutline,
    )
    from app.storage.project_files import create_project, save_character, save_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="char-hero", name="林轩", tier="major"),
            state=CharacterState(character_id="char-hero", current_goal="第十场后的目标"),
        ),
    )
    first = SceneOutline(id="scene-1", title="第一场", participating_character_ids=["char-hero"])
    second = SceneOutline(id="scene-2", title="第二场", participating_character_ids=["char-hero"])
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            title="第一卷",
            chapters=[ChapterOutline(title="第一章", scenes=[first, second])],
        ),
    )
    save_checkpoint(
        proj_dir / "characters" / "char-hero",
        SceneStateCheckpoint(
            scene_id="scene-1",
            checkpoint_id="cp-scene-1",
            event_id=3,
            character_id="char-hero",
            snapshot=CharacterStateSnapshot(
                character_id="char-hero",
                goal="第一场后的目标",
                last_event_id=3,
            ),
        ),
    )

    context = RetrievalEngine().assemble(proj_dir, scene_id="scene-2")

    hero = context["characters"]["major"][0]
    assert hero["state"]["current_goal"] == "第一场后的目标"
    assert context["read_points"]["char-hero"]["checkpoint_id"] == "cp-scene-1"


def test_canon_facts_filtered_by_importance(tmp_path):
    """Facts below the importance threshold are excluded unless tagged/scene-matched."""
    from app.pipeline.context_builder import RetrievalEngine
    from app.storage.models import CanonFact, ChapterOutline, SceneOutline, VolumeOutline
    from app.storage.project_files import create_project, save_canon_facts, save_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    facts = [
        CanonFact(description="高重要性事实", category="world", source_scene_id="s1", importance=5, tags=[]),
        CanonFact(description="中重要性事实", category="world", source_scene_id="s1", importance=3, tags=[]),
        CanonFact(description="低重要性事实", category="world", source_scene_id="s1", importance=1, tags=[]),
    ]
    save_canon_facts(proj_dir, facts)

    source_scene = SceneOutline(id="s1", title="事实来源")
    scene = SceneOutline(title="测试")
    chapter = ChapterOutline(title="第一章", scenes=[source_scene, scene])
    volume = VolumeOutline(title="第一卷", chapters=[chapter])
    save_volume_outline(proj_dir, volume)

    engine = RetrievalEngine(importance_threshold=3)
    context = engine.assemble(proj_dir, scene_id=scene.id)

    assert len(context["canon_facts"]) == 2
    descriptions = {f["description"] for f in context["canon_facts"]}
    assert "高重要性事实" in descriptions
    assert "中重要性事实" in descriptions
    assert "低重要性事实" not in descriptions


def test_canon_facts_matched_by_tag_relevance(tmp_path):
    """Facts with tags matching scene keywords are included even below threshold."""
    from app.pipeline.context_builder import RetrievalEngine
    from app.storage.models import CanonFact, ChapterOutline, SceneOutline, VolumeOutline
    from app.storage.project_files import create_project, save_canon_facts, save_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    facts = [
        CanonFact(description="不相关的事实", category="world", source_scene_id="s1", importance=1, tags=["其他"]),
        CanonFact(description="落云宗相关", category="world", source_scene_id="s1", importance=1, tags=["落云宗", "宗门"]),
    ]
    save_canon_facts(proj_dir, facts)

    source_scene = SceneOutline(id="s1", title="事实来源")
    scene = SceneOutline(title="测试", location="落云宗广场")
    chapter = ChapterOutline(title="第一章", scenes=[source_scene, scene])
    volume = VolumeOutline(title="第一卷", chapters=[chapter])
    save_volume_outline(proj_dir, volume)

    engine = RetrievalEngine(importance_threshold=3)
    context = engine.assemble(proj_dir, scene_id=scene.id)

    descriptions = {f["description"] for f in context["canon_facts"]}
    assert "落云宗相关" in descriptions
    assert "不相关的事实" not in descriptions


def test_recent_summaries_capped_by_max_summaries(tmp_path):
    """Only the last N summaries are returned."""
    from app.pipeline.context_builder import RetrievalEngine
    from app.storage.models import ChapterOutline, SceneOutline, SceneSummary, VolumeOutline
    from app.storage.project_files import create_project, save_scene_summaries, save_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    summaries = [
        SceneSummary(
            scene_id=f"s{i}", chapter_id="ch-1", summary=f"摘要{i}",
            new_facts=[], character_state_changes={},
            relationship_changes=[], open_threads=[],
        )
        for i in range(10)
    ]
    save_scene_summaries(proj_dir, summaries)

    scene = SceneOutline(id="s10", title="测试")
    chapter = ChapterOutline(
        title="第一章",
        scenes=[
            *[SceneOutline(id=f"s{i}", title=f"第{i}场") for i in range(10)],
            scene,
        ],
    )
    volume = VolumeOutline(title="第一卷", chapters=[chapter])
    save_volume_outline(proj_dir, volume)

    engine = RetrievalEngine(max_summaries=3)
    context = engine.assemble(proj_dir, scene_id=scene.id)

    assert len(context["recent_summaries"]) == 3
    summary_ids = {s["scene_id"] for s in context["recent_summaries"]}
    assert summary_ids == {"s7", "s8", "s9"}


def test_summaries_and_facts_only_use_prior_story_scenes(tmp_path):
    from app.pipeline.context_builder import RetrievalEngine
    from app.storage.models import CanonFact, ChapterOutline, SceneOutline, SceneSummary, VolumeOutline
    from app.storage.project_files import create_project, save_canon_facts, save_scene_summaries, save_volume_outline

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    scenes = [SceneOutline(id=f"scene-{i}", title=f"第{i}场") for i in range(1, 5)]
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            title="第一卷",
            chapters=[ChapterOutline(id="chapter-1", title="第一章", scenes=scenes)],
        ),
    )
    save_scene_summaries(
        proj_dir,
        [
            SceneSummary(scene_id="scene-4", chapter_id="chapter-1", summary="未来摘要"),
            SceneSummary(scene_id="scene-3", chapter_id="chapter-1", summary="当前场摘要"),
            SceneSummary(scene_id="missing-scene", chapter_id="chapter-1", summary="未知来源摘要"),
            SceneSummary(scene_id="scene-2", chapter_id="chapter-1", summary="第二场摘要"),
            SceneSummary(scene_id="scene-1", chapter_id="chapter-1", summary="第一场摘要"),
        ],
    )
    save_canon_facts(
        proj_dir,
        [
            CanonFact(description="第一场事实", category="plot", source_scene_id="scene-1", importance=5),
            CanonFact(description="当前场事实", category="plot", source_scene_id="scene-3", importance=5),
            CanonFact(description="第四场事实", category="plot", source_scene_id="scene-4", importance=5),
            CanonFact(description="未知来源事实", category="plot", source_scene_id="missing-scene", importance=5),
        ],
    )

    context = RetrievalEngine(max_summaries=2).assemble(proj_dir, scene_id="scene-3")

    assert [item["scene_id"] for item in context["recent_summaries"]] == ["scene-1", "scene-2"]
    assert [item["description"] for item in context["canon_facts"]] == ["第一场事实"]


def test_retrieval_engine_is_deterministic(tmp_path):
    """Same inputs always produce the same context dict."""
    from app.pipeline.context_builder import RetrievalEngine
    from app.storage.models import (
        CanonFact, Character, CharacterCore, CharacterState,
        ChapterOutline, SceneOutline, SceneSummary, VolumeOutline,
    )
    from app.storage.project_files import (
        create_project, save_canon_facts, save_character,
        save_scene_summaries, save_volume_outline,
    )

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    char = Character(
        core=CharacterCore(id="char-linxuan", name="林轩", tier="major"),
        state=CharacterState(character_id="char-linxuan"),
    )
    save_character(proj_dir, char)

    facts = [CanonFact(description="测试事实", category="world", source_scene_id="s0", importance=4, tags=["测试"])]
    save_canon_facts(proj_dir, facts)

    summaries = [
        SceneSummary(scene_id="s0", chapter_id="ch-1", summary="测试摘要",
                     new_facts=[], character_state_changes={},
                     relationship_changes=[], open_threads=[]),
    ]
    save_scene_summaries(proj_dir, summaries)

    source_scene = SceneOutline(id="s0", title="事实来源")
    scene = SceneOutline(title="测试场景", participating_character_ids=["char-linxuan"])
    chapter = ChapterOutline(title="第一章", scenes=[source_scene, scene])
    volume = VolumeOutline(title="第一卷", chapters=[chapter])
    save_volume_outline(proj_dir, volume)

    engine = RetrievalEngine()
    ctx1 = engine.assemble(proj_dir, scene_id=scene.id)
    ctx2 = engine.assemble(proj_dir, scene_id=scene.id)
    assert ctx1 == ctx2


def test_world_rules_present_in_context(tmp_path):
    """World settings including power system appear in context."""
    from app.pipeline.context_builder import RetrievalEngine
    from app.storage.models import (
        ChapterOutline, PowerSystem, SceneOutline, VolumeOutline, WorldSetting,
    )
    from app.storage.project_files import create_project, save_volume_outline, save_world_setting

    world = WorldSetting(
        geography="东荒大陆",
        rules=["弱肉强食"],
        taboos=["不得背叛师门"],
        power_system=PowerSystem(realms=["练气", "筑基", "金丹"], abilities={"练气": "灵气感知"}),
    )
    project = Project(title="测试", genre="玄幻", world_setting=world)
    proj_dir = create_project(tmp_path, project)

    scene = SceneOutline(title="测试")
    chapter = ChapterOutline(title="第一章", scenes=[scene])
    volume = VolumeOutline(title="第一卷", chapters=[chapter])
    save_volume_outline(proj_dir, volume)

    engine = RetrievalEngine()
    context = engine.assemble(proj_dir, scene_id=scene.id)

    wr = context["world_rules"]
    assert wr["geography"] == "东荒大陆"
    assert "弱肉强食" in wr["rules"]
    assert "不得背叛师门" in wr["taboos"]
    assert wr["power_system"]["realms"] == ["练气", "筑基", "金丹"]


def test_style_guide_present_in_context(tmp_path):
    """Style guide traits appear in the assembled context."""
    from app.pipeline.context_builder import RetrievalEngine
    from app.storage.models import ChapterOutline, SceneOutline, StyleGuide, VolumeOutline
    from app.storage.project_files import create_project, save_style_guide, save_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    style = StyleGuide(pacing="快节奏", tone="热血", reference_passages=["参考段落1"])
    save_style_guide(proj_dir, style)

    scene = SceneOutline(title="测试")
    chapter = ChapterOutline(title="第一章", scenes=[scene])
    volume = VolumeOutline(title="第一卷", chapters=[chapter])
    save_volume_outline(proj_dir, volume)

    engine = RetrievalEngine()
    context = engine.assemble(proj_dir, scene_id=scene.id)

    sg = context["style_guide"]
    assert sg["pacing"] == "快节奏"
    assert sg["tone"] == "热血"
    assert sg["reference_passages"] == ["参考段落1"]


def test_scene_info_derives_current_names_from_character_ids(tmp_path):
    from app.pipeline.context_builder import RetrievalEngine
    from app.storage.models import Character, CharacterCore, CharacterState, ChapterOutline, SceneOutline, VolumeOutline
    from app.storage.project_files import create_project, save_character, save_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="char-hero", name="新名字", tier="major"),
            state=CharacterState(character_id="char-hero"),
        ),
    )
    scene = SceneOutline(
        id="scene-1",
        title="测试",
        pov_character_id="char-hero",
        participating_character_ids=["char-hero"],
    )
    save_volume_outline(
        proj_dir,
        VolumeOutline(title="第一卷", chapters=[ChapterOutline(title="第一章", scenes=[scene])]),
    )

    context = RetrievalEngine().assemble(proj_dir, scene_id="scene-1")

    assert context["scene_info"]["pov_character"] == "新名字"
    assert context["scene_info"]["participating_characters"] == ["新名字"]
    assert len(context["characters"]["major"]) == 1
    assert context["characters"]["major"][0]["core"]["id"] == "char-hero"


def test_duplicate_character_names_do_not_select_both_characters(tmp_path):
    from app.pipeline.context_builder import RetrievalEngine
    from app.storage.models import Character, CharacterCore, CharacterState, ChapterOutline, SceneOutline, VolumeOutline
    from app.storage.project_files import create_project, save_character, save_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="char-a", name="Alex", tier="major"),
            state=CharacterState(character_id="char-a"),
        ),
    )
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="char-b", name="Alex", tier="major"),
            state=CharacterState(character_id="char-b"),
        ),
    )
    scene = SceneOutline(id="scene-1", title="测试", participating_character_ids=["char-b"])
    save_volume_outline(
        proj_dir,
        VolumeOutline(title="第一卷", chapters=[ChapterOutline(title="第一章", scenes=[scene])]),
    )

    context = RetrievalEngine().assemble(proj_dir, scene_id="scene-1")

    assert [char["core"]["id"] for char in context["characters"]["major"]] == ["char-b"]
    assert context["scene_info"]["participating_characters"] == ["Alex"]


def test_missing_character_id_fails_context_assembly(tmp_path):
    from app.pipeline.context_builder import RetrievalEngine
    from app.storage.models import ChapterOutline, SceneOutline, VolumeOutline
    from app.storage.project_files import create_project, save_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)
    scene = SceneOutline(id="scene-1", title="测试", participating_character_ids=["missing-char"])
    save_volume_outline(
        proj_dir,
        VolumeOutline(title="第一卷", chapters=[ChapterOutline(title="第一章", scenes=[scene])]),
    )

    with pytest.raises(ValueError, match="Scene references missing character IDs: missing-char"):
        RetrievalEngine().assemble(proj_dir, scene_id="scene-1")


def test_world_context_selects_explicit_related_and_always_elements(tmp_path):
    from app.pipeline.context_builder import RetrievalEngine
    from app.storage.bible_migration import ensure_bible_store
    from app.storage.bible_models import (
        BibleElementRelation,
        FactionElement,
        LocationElement,
        PowerSystemElement,
    )
    from app.storage.bible_repository import BibleElementRepository
    from app.storage.models import ChapterOutline, SceneOutline, VolumeOutline, WorldSetting
    from app.storage.project_files import save_volume_outline

    project = Project(
        title="元素上下文",
        genre="玄幻",
        world_setting=WorldSetting(
            geography="东荒大陆",
            rules=["不得干涉凡人"],
            taboos=["夺舍"],
            technology_level="古代",
            social_structure="宗门治理",
        ),
    )
    project_dir = create_project(tmp_path, project)
    ensure_bible_store(project_dir)
    repo = BibleElementRepository(project_dir)
    related = repo.create(FactionElement(id="f2", name="魔渊殿"))
    power = repo.create(PowerSystemElement(
        id="p1", name="九重天境", summary="九层修炼体系", always_include=True
    ))
    repo.create(LocationElement(id="l1", name="无关海岛", description="遥远之地"))
    explicit = repo.create(FactionElement(
        id="f1",
        name="青云宗",
        summary="正道第一宗门",
        relationships=[BibleElementRelation(kind="opposed_to", target_element_id="f2")],
    ))
    repo.reorder([explicit.id, related.id, power.id, "l1"])
    repo.set_primary_power_system(power.id)
    scene = SceneOutline(id="scene-1", title="宗门议事", world_element_ids=[explicit.id])
    save_volume_outline(
        project_dir,
        VolumeOutline(
            id="v1",
            chapters=[ChapterOutline(id="c1", scenes=[scene])],
        ),
    )

    context = RetrievalEngine().assemble(project_dir, "scene-1")

    assert context["world_context"]["overview"] == {
        "geography": "东荒大陆",
        "rules": ["不得干涉凡人"],
        "taboos": ["夺舍"],
        "technology_level": "古代",
        "social_structure": "宗门治理",
    }
    assert [item["id"] for item in context["world_context"]["elements"]] == [
        "f1", "p1", "f2"
    ]
    assert "l1" not in context["world_element_read_points"]
    assert context["world_element_read_points"]["f1"]["selection_reasons"] == [
        "explicit_scene_reference"
    ]
    assert context["world_element_read_points"]["f2"]["selection_reasons"] == [
        "related_to:f1:opposed_to"
    ]
    assert context["world_element_read_points"]["p1"]["revision"] == 1
    compact = context["world_context"]["elements"][0]
    assert "revision" not in compact
    assert "created_at" not in compact
    assert compact["relationships"][0]["target_name"] == "魔渊殿"
    assert context["world_rules"]["factions"][0]["name"] == "青云宗"
