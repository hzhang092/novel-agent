"""Tests for model validation and compatibility behavior not covered elsewhere."""

import pytest
from pydantic import ValidationError

from app.storage.models import (
    CanonFact,
    CharacterCore,
    CharacterState,
    CharacterTier,
    ContinuityState,
    PowerSystem,
    Project,
    SceneOutline,
    SceneSummary,
    StoryOutline,
    VolumeOutline,
)


def test_character_tier_values():
    assert [tier.value for tier in CharacterTier] == [
        "major",
        "supporting",
        "background",
    ]


def test_character_core_name_required():
    with pytest.raises(ValidationError):
        CharacterCore()


def test_storage_model_defaults():
    core = CharacterCore(name="林轩")
    state = CharacterState(character_id=core.id)
    scene = SceneOutline()
    project = Project(title="修仙之路")

    assert core.tier == CharacterTier.SUPPORTING
    assert core.aliases == []
    assert state.current_goal == ""
    assert state.current_relationships == {}
    assert PowerSystem().realms == []
    assert scene.id != ""
    assert scene.title == ""
    assert project.language == "zh-CN"
    assert project.llm_provider == "ollama"
    assert project.id != ""


def test_story_outline_and_continuity_models():
    outline = StoryOutline(
        premise="废材少年逆天改命",
        themes=["成长", "复仇"],
        ending="林轩成为最强修士",
        volumes=[VolumeOutline(title="第一卷：落云宗")],
    )
    continuity = ContinuityState(
        recent_summaries=[SceneSummary(scene_id="s1")],
        active_open_threads=["神秘力量来源"],
        current_character_states={"林轩": "备战考核"},
        new_canon_facts_since_last_scene=["林轩拥有神秘力量"],
    )

    assert outline.themes == ["成长", "复仇"]
    assert outline.volumes[0].title == "第一卷：落云宗"
    assert continuity.recent_summaries[0].scene_id == "s1"


def test_canon_fact_importance_range():
    for importance in (0, 6):
        with pytest.raises(ValidationError):
            CanonFact(
                description="test",
                category="world",
                source_scene_id="s1",
                importance=importance,
            )


def test_project_required_and_legacy_optional_fields():
    with pytest.raises(ValidationError):
        Project(genre="玄幻")
    assert Project(title="test").genre is None


def test_state_change_rejects_unknown_field():
    from app.storage.models import SetFieldChange

    with pytest.raises(ValidationError):
        SetFieldChange(type="set_field", field="goals", value="avenge master")


def test_generation_read_points_parse_legacy_and_nested_shapes():
    from app.storage.models import parse_generation_read_points

    legacy = parse_generation_read_points(
        {"char-1": {"checkpoint_id": "checkpoint-1", "event_id": 4}}
    )
    nested = parse_generation_read_points(
        {
            "characters": {"char-1": {"checkpoint_id": "checkpoint-1"}},
            "bible_elements": {
                "faction-1": {
                    "revision": 3,
                    "selection_reasons": ["explicit_scene_reference"],
                }
            },
        }
    )

    assert legacy.characters["char-1"]["event_id"] == 4
    assert legacy.bible_elements == {}
    assert nested.characters["char-1"]["checkpoint_id"] == "checkpoint-1"
    assert nested.bible_elements["faction-1"]["revision"] == 3
