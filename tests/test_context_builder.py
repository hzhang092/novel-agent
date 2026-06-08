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
            name="林轩", tier="major", personality="坚韧不拔",
            background="孤儿出身", long_term_goal="成为最强",
        ),
        state=CharacterState(
            character_id="", current_emotion="坚定",
            current_goal="通过考核", current_location="广场",
        ),
    )
    supporting_char = Character(
        core=CharacterCore(name="苏清鸾", tier="supporting", personality="清冷高傲", speech_style="简短"),
        state=CharacterState(character_id="", current_relationships={"林轩": "同门"}),
    )
    bg_char = Character(
        core=CharacterCore(name="杂役弟子甲", tier="background"),
        state=CharacterState(character_id=""),
    )
    save_character(proj_dir, major_char)
    save_character(proj_dir, supporting_char)
    save_character(proj_dir, bg_char)

    scene = SceneOutline(title="测试场景", participating_characters=["林轩", "苏清鸾", "杂役弟子甲"])
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


def test_non_participating_characters_are_excluded(tmp_path):
    """Characters not in the scene's participating_characters list are excluded."""
    from app.pipeline.context_builder import RetrievalEngine
    from app.storage.models import (
        Character, CharacterCore, CharacterState,
        ChapterOutline, SceneOutline, VolumeOutline,
    )
    from app.storage.project_files import create_project, save_character, save_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    char_in = Character(
        core=CharacterCore(name="林轩", tier="major"),
        state=CharacterState(character_id=""),
    )
    char_out = Character(
        core=CharacterCore(name="路人乙", tier="major"),
        state=CharacterState(character_id=""),
    )
    save_character(proj_dir, char_in)
    save_character(proj_dir, char_out)

    scene = SceneOutline(title="测试", participating_characters=["林轩"])
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

    scene = SceneOutline(title="测试")
    chapter = ChapterOutline(title="第一章", scenes=[scene])
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

    scene = SceneOutline(title="测试", location="落云宗广场", participating_characters=["林轩"])
    chapter = ChapterOutline(title="第一章", scenes=[scene])
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

    scene = SceneOutline(title="测试")
    chapter = ChapterOutline(title="第一章", scenes=[scene])
    volume = VolumeOutline(title="第一卷", chapters=[chapter])
    save_volume_outline(proj_dir, volume)

    engine = RetrievalEngine(max_summaries=3)
    context = engine.assemble(proj_dir, scene_id=scene.id)

    assert len(context["recent_summaries"]) == 3
    summary_ids = {s["scene_id"] for s in context["recent_summaries"]}
    assert summary_ids == {"s7", "s8", "s9"}


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
        core=CharacterCore(name="林轩", tier="major"),
        state=CharacterState(character_id=""),
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

    scene = SceneOutline(title="测试场景", participating_characters=["林轩"])
    chapter = ChapterOutline(title="第一章", scenes=[scene])
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

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    world = WorldSetting(
        geography="东荒大陆",
        rules=["弱肉强食"],
        taboos=["不得背叛师门"],
        power_system=PowerSystem(realms=["练气", "筑基", "金丹"], abilities={"练气": "灵气感知"}),
    )
    save_world_setting(proj_dir, world)

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
