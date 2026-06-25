"""Tests for outline file I/O: save, load, delete, list volumes."""
import pytest

from app.storage.models import (
    ChapterOutline,
    Project,
    SceneOutline,
    VolumeOutline,
)
from app.storage.project_files import create_project


def test_save_and_load_volume_round_trip(tmp_path):
    """Save a volume with chapters and scenes, reload, verify all fields."""
    from app.storage.project_files import save_volume_outline, load_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    scene = SceneOutline(
        title="考核开始",
        location="落云宗广场",
        time="清晨",
        pov_character="林轩",
        participating_characters=["林轩", "苏清鸾", "长老"],
        scene_goal="林轩通过第一关考核",
        conflict="林轩修为低微，被其他弟子嘲笑",
        required_plot_beats=["入场", "嘲笑", "反击", "考核结果"],
        emotional_turn="紧张→受挫→坚定→成功",
        ending_hook="考核官露出意味深长的笑容",
        constraints=["林轩不能使用神秘力量"],
    )
    chapter = ChapterOutline(
        title="第一章：考核日",
        summary="宗门年度考核，林轩面临严峻考验",
        scenes=[scene],
        target_word_count=3000,
    )
    volume = VolumeOutline(
        title="第一卷：落云宗",
        summary="林轩在落云宗的成长故事",
        chapters=[chapter],
    )

    save_volume_outline(proj_dir, volume)
    loaded = load_volume_outline(proj_dir, volume.id)

    assert loaded.id == volume.id
    assert loaded.title == "第一卷：落云宗"
    assert loaded.summary == "林轩在落云宗的成长故事"
    assert len(loaded.chapters) == 1

    ch = loaded.chapters[0]
    assert ch.title == "第一章：考核日"
    assert ch.summary == "宗门年度考核，林轩面临严峻考验"
    assert ch.target_word_count == 3000
    assert len(ch.scenes) == 1

    sc = ch.scenes[0]
    assert sc.title == "考核开始"
    assert sc.location == "落云宗广场"
    assert sc.time == "清晨"
    assert sc.pov_character == "林轩"
    assert sc.participating_characters == ["林轩", "苏清鸾", "长老"]
    assert sc.scene_goal == "林轩通过第一关考核"
    assert sc.conflict == "林轩修为低微，被其他弟子嘲笑"
    assert sc.required_plot_beats == ["入场", "嘲笑", "反击", "考核结果"]
    assert sc.emotional_turn == "紧张→受挫→坚定→成功"
    assert sc.ending_hook == "考核官露出意味深长的笑容"
    assert sc.constraints == ["林轩不能使用神秘力量"]


def test_save_and_load_volume_minimal(tmp_path):
    """Save a volume with defaults, verify round-trip."""
    from app.storage.project_files import save_volume_outline, load_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    volume = VolumeOutline(title="第一卷")
    save_volume_outline(proj_dir, volume)
    loaded = load_volume_outline(proj_dir, volume.id)

    assert loaded.title == "第一卷"
    assert loaded.summary == ""
    assert loaded.chapters == []


def test_save_volume_with_multiple_chapters_and_scenes(tmp_path):
    """Verify nested hierarchy with multiple chapters, each with multiple scenes."""
    from app.storage.project_files import save_volume_outline, load_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    volume = VolumeOutline(
        title="第一卷",
        chapters=[
            ChapterOutline(
                title="第一章",
                scenes=[
                    SceneOutline(title="场景1", ending_hook="悬念A"),
                    SceneOutline(title="场景2", ending_hook=""),
                ],
            ),
            ChapterOutline(
                title="第二章",
                scenes=[
                    SceneOutline(title="场景3", ending_hook="悬念B"),
                ],
            ),
        ],
    )
    save_volume_outline(proj_dir, volume)
    loaded = load_volume_outline(proj_dir, volume.id)

    assert len(loaded.chapters) == 2
    assert len(loaded.chapters[0].scenes) == 2
    assert len(loaded.chapters[1].scenes) == 1
    assert loaded.chapters[0].scenes[0].ending_hook == "悬念A"
    assert loaded.chapters[0].scenes[1].ending_hook == ""
    assert loaded.chapters[1].scenes[0].ending_hook == "悬念B"


def test_load_volume_missing_file(tmp_path):
    """Loading a nonexistent volume raises FileNotFoundError."""
    from app.storage.project_files import load_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    with pytest.raises(FileNotFoundError):
        load_volume_outline(proj_dir, "nonexistent-id")


def test_load_volume_invalid_yaml(tmp_path):
    """Loading corrupt YAML raises ValueError."""
    from app.storage.project_files import load_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    bad_file = proj_dir / "outline" / "bad.yaml"
    bad_file.write_text(": invalid : yaml :", encoding="utf-8")

    with pytest.raises(ValueError):
        load_volume_outline(proj_dir, "bad")


def test_delete_volume(tmp_path):
    """Delete removes the volume YAML file."""
    from app.storage.project_files import (
        delete_volume_outline,
        load_volume_outline,
        save_volume_outline,
    )

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    volume = VolumeOutline(title="第一卷")
    save_volume_outline(proj_dir, volume)
    assert (proj_dir / "outline" / f"{volume.id}.yaml").exists()

    delete_volume_outline(proj_dir, volume.id)
    assert not (proj_dir / "outline" / f"{volume.id}.yaml").exists()

    with pytest.raises(FileNotFoundError):
        load_volume_outline(proj_dir, volume.id)


def test_delete_nonexistent_volume_no_error(tmp_path):
    """Deleting a nonexistent volume does not raise."""
    from app.storage.project_files import delete_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    delete_volume_outline(proj_dir, "nonexistent-id")


def test_list_volume_ids(tmp_path):
    """List returns all volume IDs in the outline directory."""
    from app.storage.project_files import list_volume_ids, save_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    ids = []
    for title in ["第一卷", "第二卷", "第三卷"]:
        volume = VolumeOutline(title=title)
        save_volume_outline(proj_dir, volume)
        ids.append(volume.id)

    result = list_volume_ids(proj_dir)
    assert set(result) == set(ids)


def test_list_volume_ids_empty_directory(tmp_path):
    """Empty outline directory returns empty list."""
    from app.storage.project_files import list_volume_ids

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    assert list_volume_ids(proj_dir) == []


def test_load_all_volumes(tmp_path):
    """Load all volumes sorted by filename."""
    from app.storage.project_files import load_all_volumes, save_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    v1 = VolumeOutline(title="第一卷")
    v2 = VolumeOutline(title="第二卷")
    save_volume_outline(proj_dir, v1)
    save_volume_outline(proj_dir, v2)

    loaded = load_all_volumes(proj_dir)
    assert len(loaded) == 2
    assert {v.title for v in loaded} == {"第一卷", "第二卷"}


def test_load_all_volumes_raises_with_bad_files(tmp_path):
    """A corrupt outline file should not be silently skipped."""
    from app.storage.project_files import load_all_volumes, save_volume_outline

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)
    save_volume_outline(proj_dir, VolumeOutline(title="第一卷"))
    bad_file = proj_dir / "outline" / "bad.yaml"
    bad_file.write_text("[", encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        load_all_volumes(proj_dir)

    message = str(exc.value)
    assert "bad.yaml" in message
    assert str(bad_file) in message


def test_load_all_volumes_empty(tmp_path):
    """Empty directory returns empty list."""
    from app.storage.project_files import load_all_volumes

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    assert load_all_volumes(proj_dir) == []
