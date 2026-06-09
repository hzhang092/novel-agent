"""Tests for scene prose (.md) and generation record I/O."""
import pytest

from app.storage.models import Project, SceneGenerationRecord
from app.storage.project_files import create_project


def test_save_and_load_scene_prose_round_trip(tmp_path):
    """Save prose to scenes/<chapter>/scene-NNN.md and load it back."""
    from app.storage.project_files import save_scene_prose, load_scene_prose

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    prose = "林轩站在落云宗的山门前，望着远处的云海。\n\n## 第一节\n\n风吹过..."
    save_scene_prose(proj_dir, chapter_id="ch-1", scene_id="scene-1", prose=prose)

    loaded = load_scene_prose(proj_dir, chapter_id="ch-1", scene_id="scene-1")
    assert loaded == prose


def test_load_scene_prose_missing_file(tmp_path):
    """Loading prose for a scene that has no saved file returns empty string."""
    from app.storage.project_files import load_scene_prose

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    result = load_scene_prose(proj_dir, chapter_id="ch-1", scene_id="scene-1")
    assert result == ""


def test_save_and_load_scene_generation_record(tmp_path):
    """Save and load a SceneGenerationRecord as JSON."""
    from app.storage.project_files import save_scene_generation_record, load_scene_generation_record

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    # Create a minimal outline so the scene can be resolved to a chapter
    from app.storage.models import VolumeOutline, ChapterOutline, SceneOutline
    from app.storage.project_files import save_volume_outline
    scene = SceneOutline(id="scene-1", title="测试场景")
    chapter = ChapterOutline(id="ch-1", title="第一章", scenes=[scene])
    volume = VolumeOutline(id="vol-1", title="第一卷", chapters=[chapter])
    save_volume_outline(proj_dir, volume)

    record = SceneGenerationRecord(
        scene_id="scene-1",
        generation_mode="standard",
        scene_plan={"beats": ["开场冲突", "发展", "高潮"]},
        character_intents={"char-1": {"emotion": "愤怒"}},
        draft_text="林轩推门而入。",
        final_text="林轩推门而入。",
    )
    save_scene_generation_record(proj_dir, record)

    loaded = load_scene_generation_record(proj_dir, "scene-1")
    assert loaded is not None
    assert loaded.scene_id == "scene-1"
    assert loaded.generation_mode == "standard"
    assert loaded.scene_plan == {"beats": ["开场冲突", "发展", "高潮"]}
    assert loaded.draft_text == "林轩推门而入。"


def test_load_scene_generation_record_missing(tmp_path):
    """Loading a record that doesn't exist returns None."""
    from app.storage.project_files import load_scene_generation_record

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    result = load_scene_generation_record(proj_dir, "scene-1")
    assert result is None


def test_save_scene_prose_creates_chapter_dir(tmp_path):
    """Saving prose creates the chapter subdirectory if needed."""
    from app.storage.project_files import save_scene_prose

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    save_scene_prose(proj_dir, chapter_id="ch-2", scene_id="scene-5", prose="...")
    chapter_dir = proj_dir / "scenes" / "ch-2"
    assert chapter_dir.exists()
    assert (chapter_dir / "scene-5.md").exists()


def test_overwrite_scene_prose(tmp_path):
    """Saving prose twice overwrites the previous content."""
    from app.storage.project_files import save_scene_prose, load_scene_prose

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    save_scene_prose(proj_dir, chapter_id="ch-1", scene_id="scene-1", prose="第一版")
    save_scene_prose(proj_dir, chapter_id="ch-1", scene_id="scene-1", prose="第二版")

    loaded = load_scene_prose(proj_dir, chapter_id="ch-1", scene_id="scene-1")
    assert loaded == "第二版"
