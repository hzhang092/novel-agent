import os
from pathlib import Path

import pytest

from app.storage.bible_models import (
    BibleElementRelation,
    FactionElement,
    PowerRealm,
    PowerSystemElement,
    TerminologyElement,
    WorldOverview,
)
from app.storage.bible_repository import WorldBibleService
from app.storage.models import ChapterOutline, Project, SceneOutline, VolumeOutline
from app.storage.project_files import (
    create_project,
    load_all_volumes,
    load_project,
    save_volume_outline,
)


def project_dir(tmp_path: Path) -> Path:
    return create_project(tmp_path, Project(title="故事", genre="玄幻"))


def test_save_element_creates_updates_and_synchronizes_compatibility_outputs(tmp_path):
    path = project_dir(tmp_path)
    service = WorldBibleService(path)

    created = service.save_element(FactionElement(id="f1", name="青云宗", description="剑修宗门"))
    saved = service.save_element(created.model_copy(update={"description": "天下第一剑宗"}))

    assert saved.revision == 2
    assert load_project(path).world_setting.factions == [
        {"name": "青云宗", "description": "天下第一剑宗", "goals": ""}
    ]
    assert "天下第一剑宗" in (path / "world.md").read_text(encoding="utf-8")


def test_apply_snapshot_saves_mutual_new_relations_and_preserves_revision_semantics(tmp_path):
    path = project_dir(tmp_path)
    service = WorldBibleService(path)
    unchanged = service.save_element(FactionElement(id="unchanged", name="旧友"))
    changed = service.save_element(
        FactionElement(id="changed", name="青云宗", description="旧描述")
    )
    previous_content_revision = service.load().manifest.content_revision
    first_new = FactionElement(
        id="new-a",
        name="新势力甲",
        relationships=[BibleElementRelation(kind="uses", target_element_id="new-b")],
    )
    second_new = FactionElement(
        id="new-b",
        name="新势力乙",
        relationships=[BibleElementRelation(kind="uses", target_element_id="new-a")],
    )

    saved = service.apply_snapshot(
        WorldOverview(geography="东荒"),
        [
            first_new,
            unchanged.model_copy(update={"revision": 99}),
            changed.model_copy(update={"description": "新描述", "revision": 99}),
            second_new,
        ],
    )

    assert [element.id for element in saved] == [
        "new-a",
        "unchanged",
        "changed",
        "new-b",
    ]
    by_id = {element.id: element for element in saved}
    assert by_id["new-a"].revision == 1
    assert by_id["new-b"].revision == 1
    assert by_id["unchanged"].revision == unchanged.revision
    assert by_id["changed"].revision == changed.revision + 1
    assert service.load().manifest.content_revision == previous_content_revision + 1
    assert [element.id for element in service.load().elements] == [
        "new-a",
        "unchanged",
        "changed",
        "new-b",
    ]
    project = load_project(path)
    assert project.world_setting.geography == "东荒"
    assert [faction["name"] for faction in project.world_setting.factions] == [
        "新势力甲",
        "旧友",
        "青云宗",
        "新势力乙",
    ]


def test_apply_snapshot_deletes_omitted_elements_and_unlinks_scene_references(tmp_path):
    path = project_dir(tmp_path)
    service = WorldBibleService(path)
    removed = service.save_element(FactionElement(id="removed", name="旧势力"))
    retained = service.save_element(FactionElement(id="retained", name="新势力"))
    save_volume_outline(
        path,
        VolumeOutline(
            id="v1",
            chapters=[
                ChapterOutline(
                    id="c1",
                    scenes=[
                        SceneOutline(
                            id="s1",
                            world_element_ids=[removed.id, retained.id, removed.id],
                        )
                    ],
                )
            ],
        ),
    )

    saved = service.apply_snapshot(WorldOverview(), [retained])

    assert [element.id for element in saved] == [retained.id]
    assert not (path / "bible" / "elements" / "removed.yaml").exists()
    assert load_all_volumes(path)[0].chapters[0].scenes[0].world_element_ids == [
        retained.id
    ]
    assert [faction["name"] for faction in load_project(path).world_setting.factions] == [
        "新势力"
    ]


def test_apply_snapshot_failure_rolls_back_all_files_and_is_retryable(
    tmp_path, monkeypatch
):
    path = project_dir(tmp_path)
    service = WorldBibleService(path)
    removed = service.save_element(FactionElement(id="removed", name="旧势力"))
    changed = service.save_element(
        FactionElement(id="changed", name="青云宗", description="旧描述")
    )
    save_volume_outline(
        path,
        VolumeOutline(
            id="v1",
            chapters=[
                ChapterOutline(
                    id="c1",
                    scenes=[SceneOutline(id="s1", world_element_ids=[removed.id])],
                )
            ],
        ),
    )
    before = {
        relative: (path / relative).read_bytes()
        for relative in (
            "bible/elements/removed.yaml",
            "bible/elements/changed.yaml",
            "bible/manifest.yaml",
            "outline/v1.yaml",
            "project.yaml",
            "world.md",
        )
    }
    target = [
        changed.model_copy(update={"description": "新描述"}),
        FactionElement(id="new", name="新势力"),
    ]
    real_replace = os.replace
    failed = False

    def fail_world_once(source, destination):
        nonlocal failed
        if Path(destination).name == "world.md" and not failed:
            failed = True
            raise OSError("world markdown replace failed")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_world_once)

    with pytest.raises(OSError, match="world markdown replace failed"):
        service.apply_snapshot(WorldOverview(geography="东荒"), target)

    assert all((path / relative).read_bytes() == content for relative, content in before.items())
    assert not (path / "bible" / "elements" / "new.yaml").exists()

    saved = service.apply_snapshot(WorldOverview(geography="东荒"), target)
    assert [element.id for element in saved] == ["changed", "new"]
    assert load_all_volumes(path)[0].chapters[0].scenes[0].world_element_ids == []


@pytest.mark.parametrize(
    "target",
    [
        [
            FactionElement(
                id="source",
                name="来源",
                relationships=[
                    BibleElementRelation(kind="uses", target_element_id="missing")
                ],
            )
        ],
        [
            TerminologyElement(id="t1", name="Spirit Stone"),
            TerminologyElement(id="t2", name="ＳＰＩＲＩＴ ＳＴＯＮＥ"),
        ],
    ],
)
def test_apply_snapshot_validates_complete_target_before_writing(tmp_path, target):
    path = project_dir(tmp_path)
    service = WorldBibleService(path)
    before_manifest = (path / "bible" / "manifest.yaml").read_bytes()
    before_project = (path / "project.yaml").read_bytes()

    with pytest.raises(ValueError):
        service.apply_snapshot(WorldOverview(), target)

    assert service.load().elements == []
    assert (path / "bible" / "manifest.yaml").read_bytes() == before_manifest
    assert (path / "project.yaml").read_bytes() == before_project


def test_failed_create_is_retryable_without_an_orphan(tmp_path, monkeypatch):
    path = project_dir(tmp_path)
    service = WorldBibleService(path)
    element = FactionElement(id="f1", name="青云宗")
    real_write = service.repository._write_yaml_atomic
    failed = False

    def fail_manifest_once(destination, data):
        nonlocal failed
        if Path(destination).name == "manifest.yaml" and not failed:
            failed = True
            raise OSError("manifest write failed")
        real_write(destination, data)

    monkeypatch.setattr(service.repository, "_write_yaml_atomic", fail_manifest_once)

    with pytest.raises(OSError, match="manifest write failed"):
        service.save_element(element)

    saved = service.save_element(element)

    assert saved.id == "f1"
    assert [item.id for item in service.load().elements] == ["f1"]
    assert load_project(path).world_setting.factions[0]["name"] == "青云宗"


def test_save_overview_keeps_element_projection_synchronized(tmp_path):
    path = project_dir(tmp_path)
    service = WorldBibleService(path)
    service.save_element(FactionElement(id="f1", name="青云宗"))

    service.save_overview(
        WorldOverview(
            geography="东荒",
            rules=["不可干涉凡人"],
            technology_level="古代",
            social_structure="宗门治理",
        )
    )

    world = load_project(path).world_setting
    assert world.geography == "东荒"
    assert world.rules == ["不可干涉凡人"]
    assert [faction["name"] for faction in world.factions] == ["青云宗"]
    markdown = (path / "world.md").read_text(encoding="utf-8")
    assert "东荒" in markdown
    assert "青云宗" in markdown


def test_reorder_and_primary_power_changes_synchronize_compatibility_outputs(tmp_path):
    path = project_dir(tmp_path)
    service = WorldBibleService(path)
    service.save_element(FactionElement(id="f1", name="第一势力"))
    service.save_element(FactionElement(id="f2", name="第二势力"))
    service.save_element(
        PowerSystemElement(id="p1", name="旧体系", realms=[PowerRealm(name="炼气")])
    )
    service.save_element(
        PowerSystemElement(id="p2", name="新体系", realms=[PowerRealm(name="筑基")])
    )

    service.reorder_elements(["f2", "f1", "p1", "p2"])
    service.set_primary_power_system("p2")

    world = load_project(path).world_setting
    assert [faction["name"] for faction in world.factions] == ["第二势力", "第一势力"]
    assert world.power_system is not None
    assert world.power_system.realms == ["筑基"]
    assert service.load().manifest.primary_power_system_id == "p2"


def test_reorder_sync_failure_rolls_back_and_is_retryable(tmp_path, monkeypatch):
    path = project_dir(tmp_path)
    service = WorldBibleService(path)
    service.save_element(FactionElement(id="f1", name="第一势力"))
    service.save_element(FactionElement(id="f2", name="第二势力"))
    original_project = (path / "project.yaml").read_bytes()
    original_world = (path / "world.md").read_bytes()
    real_replace = os.replace
    failed = False

    def fail_world_once(source, destination):
        nonlocal failed
        if Path(destination).name == "world.md" and not failed:
            failed = True
            raise OSError("world markdown replace failed")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_world_once)

    with pytest.raises(OSError, match="world markdown replace failed"):
        service.reorder_elements(["f2", "f1"])

    assert service.load().manifest.element_order == ["f1", "f2"]
    assert (path / "project.yaml").read_bytes() == original_project
    assert (path / "world.md").read_bytes() == original_world

    service.reorder_elements(["f2", "f1"])
    assert service.load().manifest.element_order == ["f2", "f1"]


def test_delete_refuses_referenced_element_without_unlinking_and_changes_nothing(tmp_path):
    path = project_dir(tmp_path)
    service = WorldBibleService(path)
    service.save_element(FactionElement(id="target", name="目标"))
    source = service.save_element(FactionElement(id="source", name="来源"))
    service.save_element(
        source.model_copy(
            update={
                "relationships": [
                    BibleElementRelation(kind="uses", target_element_id="target")
                ]
            }
        )
    )
    save_volume_outline(
        path,
        VolumeOutline(
            id="v1",
            chapters=[
                ChapterOutline(
                    id="c1",
                    scenes=[SceneOutline(id="s1", world_element_ids=["target"])],
                )
            ],
        ),
    )

    with pytest.raises(ValueError, match="referenced"):
        service.delete_element("target")

    bible = service.load()
    assert [element.id for element in bible.elements] == ["target", "source"]
    assert bible.elements[1].relationships[0].target_element_id == "target"
    assert load_all_volumes(path)[0].chapters[0].scenes[0].world_element_ids == ["target"]


def test_delete_and_unlink_updates_relations_scenes_primary_and_compatibility(tmp_path):
    path = project_dir(tmp_path)
    service = WorldBibleService(path)
    target = service.save_element(
        PowerSystemElement(id="target", name="九重天境", realms=[PowerRealm(name="炼气")])
    )
    source = service.save_element(FactionElement(id="source", name="青云宗"))
    source = service.save_element(
        source.model_copy(
            update={
                "relationships": [
                    BibleElementRelation(kind="uses", target_element_id=target.id)
                ]
            }
        )
    )
    for volume_id in ("v1", "v2"):
        save_volume_outline(
            path,
            VolumeOutline(
                id=volume_id,
                chapters=[
                    ChapterOutline(
                        id=f"c-{volume_id}",
                        scenes=[
                            SceneOutline(
                                id=f"s-{volume_id}",
                                world_element_ids=["target", "source", "target"],
                            )
                        ],
                    )
                ],
            ),
        )

    service.delete_element("target", unlink_references=True)

    bible = service.load()
    assert [element.id for element in bible.elements] == ["source"]
    assert bible.elements[0].relationships == []
    assert bible.elements[0].revision == source.revision + 1
    assert bible.manifest.primary_power_system_id is None
    assert all(
        volume.chapters[0].scenes[0].world_element_ids == ["source"]
        for volume in load_all_volumes(path)
    )
    assert load_project(path).world_setting.power_system is None
    assert "九重天境" not in (path / "world.md").read_text(encoding="utf-8")


def test_delete_and_unlink_failure_rolls_back_every_file_and_is_retryable(
    tmp_path, monkeypatch
):
    path = project_dir(tmp_path)
    service = WorldBibleService(path)
    service.save_element(FactionElement(id="target", name="目标"))
    source = service.save_element(FactionElement(id="source", name="来源"))
    service.save_element(
        source.model_copy(
            update={
                "relationships": [
                    BibleElementRelation(kind="uses", target_element_id="target")
                ]
            }
        )
    )
    save_volume_outline(
        path,
        VolumeOutline(
            id="v1",
            chapters=[
                ChapterOutline(
                    id="c1",
                    scenes=[SceneOutline(id="s1", world_element_ids=["target"])],
                )
            ],
        ),
    )
    before = {
        relative: (path / relative).read_bytes()
        for relative in (
            "bible/elements/target.yaml",
            "bible/elements/source.yaml",
            "bible/manifest.yaml",
            "outline/v1.yaml",
            "project.yaml",
            "world.md",
        )
    }
    real_replace = os.replace
    failed = False

    def fail_world_once(source_path, destination):
        nonlocal failed
        if Path(destination).name == "world.md" and not failed:
            failed = True
            raise OSError("world markdown replace failed")
        real_replace(source_path, destination)

    monkeypatch.setattr(os, "replace", fail_world_once)

    with pytest.raises(OSError, match="world markdown replace failed"):
        service.delete_element("target", unlink_references=True)

    assert all((path / relative).read_bytes() == content for relative, content in before.items())
    bible = service.load()
    assert [element.id for element in bible.elements] == ["target", "source"]
    assert bible.elements[1].relationships[0].target_element_id == "target"
    assert load_all_volumes(path)[0].chapters[0].scenes[0].world_element_ids == [
        "target"
    ]

    service.delete_element("target", unlink_references=True)
    assert [element.id for element in service.load().elements] == ["source"]
