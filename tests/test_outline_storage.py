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
        pov_character_id="char-linxuan",
        participating_character_ids=["char-linxuan", "char-su", "char-elder"],
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
    assert sc.pov_character_id == "char-linxuan"
    assert sc.participating_character_ids == ["char-linxuan", "char-su", "char-elder"]
    assert sc.scene_goal == "林轩通过第一关考核"
    assert sc.conflict == "林轩修为低微，被其他弟子嘲笑"
    assert sc.required_plot_beats == ["入场", "嘲笑", "反击", "考核结果"]
    assert sc.emotional_turn == "紧张→受挫→坚定→成功"
    assert sc.ending_hook == "考核官露出意味深长的笑容"
    assert sc.constraints == ["林轩不能使用神秘力量"]


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

    delete_volume_outline(proj_dir, "nonexistent-id")


def test_list_and_load_all_volumes(tmp_path):
    """List and load-all cover empty and populated outline directories."""
    from app.storage.project_files import (
        list_volume_ids,
        load_all_volumes,
        save_volume_outline,
    )

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)
    assert list_volume_ids(proj_dir) == []
    assert load_all_volumes(proj_dir) == []

    ids = []
    for title in ["第一卷", "第二卷", "第三卷"]:
        volume = VolumeOutline(title=title)
        save_volume_outline(proj_dir, volume)
        ids.append(volume.id)

    result = list_volume_ids(proj_dir)
    assert set(result) == set(ids)
    loaded = load_all_volumes(proj_dir)
    assert {volume.title for volume in loaded} == {"第一卷", "第二卷", "第三卷"}


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
