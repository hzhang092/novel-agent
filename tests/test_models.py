"""Tests for Pydantic data models."""

import pytest
from pydantic import ValidationError

from app.storage.models import (
    CanonFact,
    ChapterOutline,
    Character,
    CharacterCore,
    CharacterState,
    CharacterTier,
    ContinuityState,
    PowerSystem,
    Project,
    SceneGenerationRecord,
    SceneOutline,
    SceneSummary,
    StoryOutline,
    StyleGuide,
    VolumeOutline,
    WorldSetting,
)


# ── CharacterTier ──────────────────────────────────────────────────────────

def test_character_tier_values():
    assert CharacterTier.MAJOR.value == "major"
    assert CharacterTier.SUPPORTING.value == "supporting"
    assert CharacterTier.BACKGROUND.value == "background"


# ── CharacterCore ──────────────────────────────────────────────────────────

def test_character_core_minimal():
    c = CharacterCore(name="林轩")
    assert c.name == "林轩"
    assert c.tier == CharacterTier.SUPPORTING
    assert c.aliases == []


def test_character_core_full():
    c = CharacterCore(
        name="林轩",
        aliases=["轩哥", "废物"],
        tier=CharacterTier.MAJOR,
        identity="落云宗外门弟子",
        age="17",
        appearance="清秀少年，略显瘦弱",
        personality="坚韧不拔，外冷内热",
        background="从小父母失踪，被宗门收养",
        long_term_goal="成为最强修士",
        hidden_motive="寻找父母失踪的真相",
        speech_style="沉稳，少言",
        core_skills=["基础剑法", "炼药"],
        core_weaknesses=["修为低微", "冲动"],
    )
    assert c.tier == CharacterTier.MAJOR
    assert len(c.aliases) == 2
    assert len(c.core_skills) == 2


def test_character_core_name_required():
    with pytest.raises(ValidationError):
        CharacterCore()


# ── CharacterState ─────────────────────────────────────────────────────────

def test_character_state_defaults():
    s = CharacterState(character_id="abc-123")
    assert s.current_goal == ""
    assert s.current_relationships == {}


def test_character_state_full():
    s = CharacterState(
        character_id="abc-123",
        current_goal="通过宗门考核",
        current_emotion="紧张但坚定",
        current_location="落云宗广场",
        current_power_level="炼气三层",
        current_relationships={"苏清鸾": "暗恋对象，不敢接近"},
        current_knowledge=["考核有三关", "苏清鸾是内门弟子"],
        current_secrets=["体内有神秘力量"],
        current_status="备战考核",
        last_updated_scene="scene-001",
    )
    assert s.current_power_level == "炼气三层"
    assert "苏清鸾" in s.current_relationships


# ── Character (assembled) ──────────────────────────────────────────────────

def test_character_assembly():
    core = CharacterCore(name="林轩", tier=CharacterTier.MAJOR)
    state = CharacterState(character_id=core.id)
    char = Character(core=core, state=state)
    assert char.core.name == "林轩"
    assert char.state.character_id == core.id


# ── PowerSystem ────────────────────────────────────────────────────────────

def test_power_system_empty():
    ps = PowerSystem()
    assert ps.realms == []


def test_power_system_xianxia():
    ps = PowerSystem(
        realms=["炼气", "筑基", "金丹", "元婴", "化神"],
        abilities={"炼气": "灵气感知", "筑基": "御剑飞行"},
        limitations=["每个境界需要突破瓶颈"],
        costs=["修炼需要灵石"],
        rare_resources=["万年灵芝", "天火"],
        forbidden_methods=["血祭", "吞噬他人修为"],
    )
    assert len(ps.realms) == 5
    assert ps.abilities["筑基"] == "御剑飞行"


# ── WorldSetting ───────────────────────────────────────────────────────────

def test_world_setting_defaults():
    ws = WorldSetting()
    assert ws.geography == ""
    assert ws.power_system is None


def test_world_setting_full():
    ws = WorldSetting(
        geography="东荒大陆，四面环海",
        power_system=PowerSystem(realms=["炼气", "筑基"]),
        factions=[
            {"name": "落云宗", "description": "正道第一宗门", "goals": "维护大陆和平"},
        ],
        history="万年前神魔大战，大陆分裂",
        rules=["修士不可对凡人出手", "秘境百年开启一次"],
        taboos=["修炼魔功", "背叛宗门"],
        technology_level="修仙文明",
        social_structure="宗门制，强者为尊",
        terminology={"灵石": "修炼资源货币"},
    )
    assert len(ws.factions) == 1
    assert len(ws.rules) == 2


# ── StyleGuide ─────────────────────────────────────────────────────────────

def test_style_guide_defaults():
    sg = StyleGuide()
    assert sg.pacing == ""
    assert sg.pov == ""


def test_style_guide_full():
    sg = StyleGuide(
        pacing="快节奏",
        dialogue_density="对白适中",
        description_style="简练",
        tone="热血",
        sentence_length="短句多",
        pov="第三人称",
        taboo_patterns=["过度描述内心", "拖节奏的环境描写"],
        preferred_patterns=["每章结尾留悬念", "战斗描写节奏明快"],
        reference_passages=["这是他踏入仙途的第一步..."],
        freeform_notes="整体风格参考《凡人修仙传》",
    )
    assert len(sg.taboo_patterns) == 2
    assert len(sg.reference_passages) == 1


# ── Outline hierarchy ──────────────────────────────────────────────────────

def test_scene_outline_minimal():
    so = SceneOutline()
    assert so.id != ""
    assert so.title == ""


def test_scene_outline_full():
    so = SceneOutline(
        title="考核开始",
        location="落云宗广场",
        time="清晨",
        pov_character_id="char-linxuan",
        participating_character_ids=["char-linxuan", "char-su", "char-elder"],
        scene_goal="林轩通过第一关考核",
        conflict="林轩修为最低，被其他弟子轻视",
        required_plot_beats=["展示林轩的坚韧", "苏清鸾暗中关注"],
        emotional_turn="从紧张到坚定",
        ending_hook="第二关考核内容公布时，全场震惊",
        constraints=["不可暴露神秘力量"],
    )
    assert so.pov_character_id == "char-linxuan"
    assert so.participating_character_ids == ["char-linxuan", "char-su", "char-elder"]


def test_chapter_outline():
    co = ChapterOutline(
        title="第一章：考核日",
        summary="林轩参加宗门年度考核",
        scenes=[SceneOutline(title="考核开始"), SceneOutline(title="意外发现")],
        target_word_count=5000,
    )
    assert len(co.scenes) == 2


def test_volume_outline():
    vo = VolumeOutline(
        title="第一卷：落云宗",
        summary="林轩在落云宗的成长",
        chapters=[ChapterOutline(title="第一章：考核日")],
    )
    assert len(vo.chapters) == 1


def test_story_outline():
    so = StoryOutline(
        premise="废材少年逆天改命",
        themes=["成长", "复仇", "探索"],
        ending="林轩成为最强修士",
        volumes=[VolumeOutline(title="第一卷：落云宗")],
    )
    assert so.themes == ["成长", "复仇", "探索"]


# ── SceneGenerationRecord ──────────────────────────────────────────────────

def test_scene_generation_record():
    rec = SceneGenerationRecord(
        scene_id="scene-001",
        generation_mode="standard",
    )
    assert rec.scene_id == "scene-001"
    assert rec.generation_mode == "standard"
    assert rec.draft_text == ""


# ── CanonFact ──────────────────────────────────────────────────────────────

def test_canon_fact():
    cf = CanonFact(
        description="林轩体内封印着上古力量",
        category="character",
        source_scene_id="scene-001",
        importance=5,
        tags=["林轩", "秘密", "力量"],
    )
    assert cf.importance == 5
    assert len(cf.tags) == 3


def test_canon_fact_importance_range():
    with pytest.raises(ValidationError):
        CanonFact(
            description="test",
            category="world",
            source_scene_id="s1",
            importance=6,
        )
    with pytest.raises(ValidationError):
        CanonFact(
            description="test",
            category="world",
            source_scene_id="s1",
            importance=0,
        )


# ── SceneSummary ───────────────────────────────────────────────────────────

def test_scene_summary():
    ss = SceneSummary(
        scene_id="scene-001",
        summary="林轩通过考核第一关",
        new_facts=["林轩拥有神秘力量"],
        character_state_changes={"林轩": "自信增强"},
        relationship_changes=["苏清鸾开始关注林轩"],
        open_threads=["神秘力量来源"],
    )
    assert ss.summary != ""


# ── ContinuityState ────────────────────────────────────────────────────────

def test_continuity_state():
    cs = ContinuityState(
        recent_summaries=[SceneSummary(scene_id="s1")],
        active_open_threads=["神秘力量来源"],
        current_character_states={"林轩": "备战考核"},
        new_canon_facts_since_last_scene=["林轩拥有神秘力量"],
    )
    assert len(cs.recent_summaries) == 1


# ── Project ────────────────────────────────────────────────────────────────

def test_project_minimal():
    p = Project(title="修仙之路", genre="玄幻")
    assert p.title == "修仙之路"
    assert p.genre == "玄幻"
    assert p.language == "zh-CN"
    assert p.llm_provider == "ollama"
    assert p.id != ""


def test_project_full():
    p = Project(
        title="修仙之路",
        genre="玄幻",
        llm_provider="deepseek",
        world_setting=WorldSetting(geography="东荒大陆"),
        style_guide=StyleGuide(tone="热血"),
    )
    assert p.llm_provider == "deepseek"
    assert p.world_setting.geography == "东荒大陆"
    assert p.style_guide.tone == "热血"


def test_project_title_required():
    with pytest.raises(ValidationError):
        Project(genre="玄幻")


def test_project_genre_required():
    with pytest.raises(ValidationError):
        Project(title="test")

# ── State Change discriminated union tests ──────────────────────────────────

def test_state_change_discriminated_union_set_field():
    """SetFieldChange validates with correct type and known field."""
    from app.storage.models import SetFieldChange, StateChangeProposal

    change = SetFieldChange(type="set_field", field="goal", value="avenge master")
    proposal = StateChangeProposal(character_id="char-1", character_name="林枫", changes=[change])
    assert len(proposal.changes) == 1
    assert proposal.changes[0].type == "set_field"

def test_state_change_discriminated_union_rejects_unknown_field():
    """SetFieldChange rejects field names not in CHARACTER_SCALAR_FIELDS."""
    from app.storage.models import SetFieldChange

    with pytest.raises(ValidationError):
        SetFieldChange(type="set_field", field="goals", value="avenge master")

def test_character_state_event_serializes_to_dict():
    """CharacterStateEvent round-trips through model_dump."""
    from app.storage.models import CharacterStateEvent, CharacterStoredChange

    event = CharacterStateEvent(
        event_id=1,
        scene_id="scene_042",
        character_id="char-1",
        source="ai",
        changes=[CharacterStoredChange(type="set_field", field="goal", value="avenge", old="become_elder")],
    )
    d = event.model_dump(mode="json")
    assert d["event_id"] == 1
    assert d["changes"][0]["old"] == "become_elder"


def test_generation_read_points_parse_legacy_and_nested_shapes():
    from app.storage.models import parse_generation_read_points

    legacy = parse_generation_read_points({
        "char-1": {"checkpoint_id": "checkpoint-1", "event_id": 4}
    })
    nested = parse_generation_read_points({
        "characters": {"char-1": {"checkpoint_id": "checkpoint-1"}},
        "bible_elements": {
            "faction-1": {
                "revision": 3,
                "selection_reasons": ["explicit_scene_reference"],
            }
        },
    })

    assert legacy.characters["char-1"]["event_id"] == 4
    assert legacy.bible_elements == {}
    assert nested.characters["char-1"]["checkpoint_id"] == "checkpoint-1"
    assert nested.bible_elements["faction-1"]["revision"] == 3
