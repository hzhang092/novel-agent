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


def test_load_scene_prose_prefers_latest_versioned_file(tmp_path):
    """Versioned generated prose should be reloaded by default."""
    from app.storage.project_files import load_scene_prose

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)
    chapter_dir = proj_dir / "scenes" / "ch-1"
    chapter_dir.mkdir(parents=True)

    (chapter_dir / "scene-1.md").write_text("legacy", encoding="utf-8")
    (chapter_dir / "scene-1.v1.md").write_text("first generated", encoding="utf-8")
    (chapter_dir / "scene-1.v2.md").write_text("latest generated", encoding="utf-8")

    loaded = load_scene_prose(proj_dir, chapter_id="ch-1", scene_id="scene-1")
    assert loaded == "latest generated"


def test_load_scene_prose_falls_back_to_legacy_file(tmp_path):
    """Legacy unversioned prose remains readable when no vN files exist."""
    from app.storage.project_files import load_scene_prose

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)
    chapter_dir = proj_dir / "scenes" / "ch-1"
    chapter_dir.mkdir(parents=True)

    (chapter_dir / "scene-1.md").write_text("legacy", encoding="utf-8")

    loaded = load_scene_prose(proj_dir, chapter_id="ch-1", scene_id="scene-1")
    assert loaded == "legacy"


def test_load_scene_prose_skips_unpublished_draft(tmp_path):
    from app.storage.models import ChapterOutline, SceneOutline, VolumeOutline
    from app.storage.project_files import (
        load_scene_prose,
        save_scene_generation_record,
        save_volume_outline,
    )

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[SceneOutline(id="scene-1", title="第一场")],
                )
            ],
        ),
    )
    chapter_dir = proj_dir / "scenes" / "ch-1"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "scene-1.md").write_text("accepted", encoding="utf-8")
    (chapter_dir / "scene-1.v1.md").write_text("draft", encoding="utf-8")
    save_scene_generation_record(
        proj_dir,
        SceneGenerationRecord(
            scene_id="scene-1", revision_number=1, status="draft"
        ),
    )

    assert load_scene_prose(proj_dir, "ch-1", "scene-1") == "accepted"


def test_load_scene_prose_ignores_malformed_versions(tmp_path):
    """Malformed v-suffix files should not beat valid prose files."""
    from app.storage.project_files import load_scene_prose

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)
    chapter_dir = proj_dir / "scenes" / "ch-1"
    chapter_dir.mkdir(parents=True)

    (chapter_dir / "scene-1.vx.md").write_text("bad", encoding="utf-8")
    (chapter_dir / "scene-1.md").write_text("legacy", encoding="utf-8")

    loaded = load_scene_prose(proj_dir, chapter_id="ch-1", scene_id="scene-1")
    assert loaded == "legacy"


def test_save_scene_prose_appends_version_after_generation(tmp_path):
    """Saving after generated prose exists should not be hidden by old versions."""
    from app.storage.project_files import save_scene_prose, load_scene_prose

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)
    chapter_dir = proj_dir / "scenes" / "ch-1"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "scene-1.v1.md").write_text("generated", encoding="utf-8")

    save_scene_prose(proj_dir, chapter_id="ch-1", scene_id="scene-1", prose="manual edit")

    assert (chapter_dir / "scene-1.v2.md").read_text(encoding="utf-8") == "manual edit"
    loaded = load_scene_prose(proj_dir, chapter_id="ch-1", scene_id="scene-1")
    assert loaded == "manual edit"


def test_list_scene_prose_versions_newest_first_with_legacy(tmp_path):
    from app.storage.project_files import list_scene_prose_versions

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)
    chapter_dir = proj_dir / "scenes" / "ch-1"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "scene-1.md").write_text("legacy", encoding="utf-8")
    (chapter_dir / "scene-1.v1.md").write_text("first", encoding="utf-8")
    (chapter_dir / "scene-1.v3.md").write_text("third", encoding="utf-8")
    (chapter_dir / "scene-1.vx.md").write_text("bad", encoding="utf-8")

    versions = list_scene_prose_versions(proj_dir, "ch-1", "scene-1")

    assert versions == ["v3", "v1", "legacy"]


def test_load_scene_prose_version_loads_requested_version(tmp_path):
    from app.storage.project_files import load_scene_prose_version

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)
    chapter_dir = proj_dir / "scenes" / "ch-1"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "scene-1.md").write_text("legacy", encoding="utf-8")
    (chapter_dir / "scene-1.v1.md").write_text("first", encoding="utf-8")
    (chapter_dir / "scene-1.v2.md").write_text("second", encoding="utf-8")

    assert load_scene_prose_version(proj_dir, "ch-1", "scene-1", "v1") == "first"
    assert load_scene_prose_version(proj_dir, "ch-1", "scene-1", "legacy") == "legacy"
    assert load_scene_prose_version(proj_dir, "ch-1", "scene-1", "missing") == ""


def test_set_active_scene_prose_version_writes_marker(tmp_path):
    from app.storage.project_files import (
        get_active_scene_prose_version,
        set_active_scene_prose_version,
    )

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    set_active_scene_prose_version(proj_dir, "ch-1", "scene-1", "v2")

    assert get_active_scene_prose_version(proj_dir, "ch-1", "scene-1") == "v2"
    assert (proj_dir / "scenes" / "ch-1" / "scene-1.active.yaml").exists()


def test_load_scene_prose_prefers_active_version(tmp_path):
    from app.storage.project_files import load_scene_prose, set_active_scene_prose_version

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)
    chapter_dir = proj_dir / "scenes" / "ch-1"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "scene-1.v1.md").write_text("chosen", encoding="utf-8")
    (chapter_dir / "scene-1.v2.md").write_text("newest", encoding="utf-8")
    set_active_scene_prose_version(proj_dir, "ch-1", "scene-1", "v1")

    assert load_scene_prose(proj_dir, "ch-1", "scene-1") == "chosen"


def test_load_scene_prose_status_reports_missing_active_fallback(tmp_path):
    from app.storage.project_files import (
        load_scene_prose_status,
        set_active_scene_prose_version,
    )

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)
    chapter_dir = proj_dir / "scenes" / "ch-1"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "scene-1.v2.md").write_text("fallback", encoding="utf-8")
    set_active_scene_prose_version(proj_dir, "ch-1", "scene-1", "v1")

    prose, version, active_missing = load_scene_prose_status(proj_dir, "ch-1", "scene-1")

    assert prose == "fallback"
    assert version == "v2"
    assert active_missing is True


def test_load_scene_prose_status_corrupt_active_marker_falls_back(tmp_path):
    from app.storage.project_files import load_scene_prose_status

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)
    chapter_dir = proj_dir / "scenes" / "ch-1"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "scene-1.v2.md").write_text("fallback", encoding="utf-8")
    (chapter_dir / "scene-1.active.yaml").write_text("[", encoding="utf-8")

    prose, version, active_missing = load_scene_prose_status(proj_dir, "ch-1", "scene-1")

    assert prose == "fallback"
    assert version == "v2"
    assert active_missing is True


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
