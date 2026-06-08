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
