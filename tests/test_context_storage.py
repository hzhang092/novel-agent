"""Tests for canon facts and scene summary file I/O."""
import pytest

from app.storage.models import CanonFact, Project, SceneSummary
from app.storage.project_files import create_project


def test_save_and_load_canon_facts_round_trip(tmp_path):
    """Save multiple canon facts, reload, verify all fields."""
    from app.storage.project_files import save_canon_facts, load_canon_facts

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    facts = [
        CanonFact(
            description="落云宗位于东荒",
            category="world",
            source_scene_id="scene-1",
            importance=4,
            tags=["落云宗", "东荒", "地理"],
        ),
        CanonFact(
            description="林轩拥有神秘血脉",
            category="character",
            source_scene_id="scene-2",
            importance=5,
            tags=["林轩", "血脉"],
        ),
    ]
    save_canon_facts(proj_dir, facts)
    loaded = load_canon_facts(proj_dir)

    assert len(loaded) == 2
    assert loaded[0].description == "落云宗位于东荒"
    assert loaded[0].category == "world"
    assert loaded[0].source_scene_id == "scene-1"
    assert loaded[0].importance == 4
    assert loaded[0].tags == ["落云宗", "东荒", "地理"]
    assert loaded[1].description == "林轩拥有神秘血脉"
    assert loaded[1].category == "character"
    assert loaded[1].importance == 5


def test_load_canon_facts_empty_file(tmp_path):
    """When no facts have been saved, load returns empty list."""
    from app.storage.project_files import load_canon_facts

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    result = load_canon_facts(proj_dir)
    assert result == []


def test_save_canon_facts_overwrites(tmp_path):
    """Saving overwrites previous facts, not appends."""
    from app.storage.project_files import save_canon_facts, load_canon_facts

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    facts_a = [CanonFact(description="事实A", category="world", source_scene_id="s1")]
    save_canon_facts(proj_dir, facts_a)

    facts_b = [CanonFact(description="事实B", category="plot", source_scene_id="s2")]
    save_canon_facts(proj_dir, facts_b)

    loaded = load_canon_facts(proj_dir)
    assert len(loaded) == 1
    assert loaded[0].description == "事实B"


def test_save_canon_facts_keeps_original_when_serialization_fails(tmp_path, monkeypatch):
    """A failed replacement must not overwrite the existing canon file."""
    import yaml
    from app.storage import project_files
    from app.storage.project_files import save_canon_facts

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_canon_facts(
        proj_dir,
        [CanonFact(description="原有事实", category="world", source_scene_id="s1")],
    )
    facts_path = proj_dir / "canon" / "facts.yaml"
    original = facts_path.read_bytes()

    def fail_dump(*args, **kwargs):
        raise yaml.YAMLError("serialization failed")

    monkeypatch.setattr(project_files.yaml, "safe_dump", fail_dump)

    with pytest.raises(yaml.YAMLError):
        save_canon_facts(
            proj_dir,
            [CanonFact(description="新事实", category="world", source_scene_id="s2")],
        )

    assert facts_path.read_bytes() == original


def test_save_canon_facts_keeps_original_when_replace_fails(tmp_path, monkeypatch):
    """A failed atomic replacement must leave the original canon file intact."""
    from app.storage import project_files
    from app.storage.project_files import save_canon_facts

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_canon_facts(
        proj_dir,
        [CanonFact(description="原有事实", category="world", source_scene_id="s1")],
    )
    facts_path = proj_dir / "canon" / "facts.yaml"
    original = facts_path.read_bytes()

    def fail_replace(*args, **kwargs):
        raise PermissionError("destination is locked")

    monkeypatch.setattr(project_files.os, "replace", fail_replace)

    with pytest.raises(PermissionError):
        save_canon_facts(
            proj_dir,
            [CanonFact(description="新事实", category="world", source_scene_id="s2")],
        )

    assert facts_path.read_bytes() == original
    assert not list((proj_dir / "canon").glob(".facts.*.tmp"))


def test_save_and_load_scene_summaries_round_trip(tmp_path):
    """Save scene summaries, reload, verify."""
    from app.storage.project_files import save_scene_summaries, load_scene_summaries

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    summaries = [
        SceneSummary(
            scene_id="scene-1",
            chapter_id="ch-1",
            summary="林轩通过考核",
            new_facts=["落云宗考核分为三关"],
            character_state_changes={"char-1": "emotion: determined"},
            relationship_changes=["林轩与苏清鸾初次交谈"],
            open_threads=["神秘考核官的来历"],
        ),
        SceneSummary(
            scene_id="scene-2",
            chapter_id="ch-1",
            summary="林轩展现隐藏实力",
            new_facts=["林轩拥有火属性灵根"],
            character_state_changes={"char-1": "power_level: 练气三层"},
            relationship_changes=[],
            open_threads=["神秘血脉觉醒预兆"],
        ),
    ]
    save_scene_summaries(proj_dir, summaries)
    loaded = load_scene_summaries(proj_dir)

    assert len(loaded) == 2
    assert loaded[0].scene_id == "scene-1"
    assert loaded[0].summary == "林轩通过考核"
    assert loaded[0].new_facts == ["落云宗考核分为三关"]
    assert loaded[0].character_state_changes == {"char-1": "emotion: determined"}
    assert loaded[0].open_threads == ["神秘考核官的来历"]
    assert loaded[1].scene_id == "scene-2"


def test_load_scene_summaries_empty_file(tmp_path):
    """When no summaries saved, load returns empty list."""
    from app.storage.project_files import load_scene_summaries

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    result = load_scene_summaries(proj_dir)
    assert result == []


def test_load_canon_facts_corrupt_yaml(tmp_path):
    """Loading corrupt canon facts file raises ValueError."""
    from app.storage.project_files import load_canon_facts

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    facts_path = proj_dir / "canon" / "facts.yaml"
    facts_path.write_text(": invalid : yaml :", encoding="utf-8")

    with pytest.raises(ValueError):
        load_canon_facts(proj_dir)
