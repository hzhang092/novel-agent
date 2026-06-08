"""Tests for Repository canon facts and scene summary delegation."""
from app.storage.models import CanonFact, Project, SceneSummary
from app.storage.repository import Repository


def test_repository_save_and_load_canon_facts(tmp_path):
    repo = Repository(tmp_path)
    project = Project(title="测试", genre="玄幻")
    proj_dir = repo.create(project)

    facts = [
        CanonFact(description="事实A", category="world", source_scene_id="s1", importance=4),
        CanonFact(description="事实B", category="plot", source_scene_id="s2", importance=3),
    ]
    repo.save_canon_facts(proj_dir, facts)

    loaded = repo.load_canon_facts(proj_dir)
    assert len(loaded) == 2
    assert loaded[0].description == "事实A"
    assert loaded[1].description == "事实B"


def test_repository_load_canon_facts_no_file(tmp_path):
    repo = Repository(tmp_path)
    project = Project(title="测试", genre="玄幻")
    proj_dir = repo.create(project)

    result = repo.load_canon_facts(proj_dir)
    assert result == []


def test_repository_save_and_load_scene_summaries(tmp_path):
    repo = Repository(tmp_path)
    project = Project(title="测试", genre="玄幻")
    proj_dir = repo.create(project)

    summaries = [
        SceneSummary(
            scene_id="s1", chapter_id="ch-1", summary="测试摘要",
            new_facts=[], character_state_changes={},
            relationship_changes=[], open_threads=[],
        ),
    ]
    repo.save_scene_summaries(proj_dir, summaries)

    loaded = repo.load_scene_summaries(proj_dir)
    assert len(loaded) == 1
    assert loaded[0].scene_id == "s1"
    assert loaded[0].summary == "测试摘要"


def test_repository_load_scene_summaries_no_file(tmp_path):
    repo = Repository(tmp_path)
    project = Project(title="测试", genre="玄幻")
    proj_dir = repo.create(project)

    result = repo.load_scene_summaries(proj_dir)
    assert result == []
