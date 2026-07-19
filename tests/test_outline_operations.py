import pytest

from app.domain.outline_operations import (
    add_chapter,
    add_scene,
    add_volume,
    delete_node,
    find_chapter,
    find_next_scene,
    find_scene,
    find_volume,
    move_node,
)
from app.storage.models import ChapterOutline, SceneOutline, VolumeOutline


def _outline():
    return (
        VolumeOutline(
            id="v1",
            chapters=[
                ChapterOutline(
                    id="c1",
                    scenes=[SceneOutline(id="s1"), SceneOutline(id="s2")],
                ),
                ChapterOutline(id="c2", scenes=[SceneOutline(id="s3")]),
            ],
        ),
        VolumeOutline(
            id="v2",
            chapters=[
                ChapterOutline(id="c3", scenes=[SceneOutline(id="s4")])
            ],
        ),
    )


def test_add_volume_preserves_existing_models_and_order():
    original = _outline()

    result = add_volume(original, VolumeOutline(id="v3"))

    assert [volume.id for volume in result] == ["v1", "v2", "v3"]
    assert result[0] is not original[0]


def test_add_chapter_at_volume_end_and_after_chapter():
    original = _outline()

    at_end = add_chapter(original, "v1", ChapterOutline(id="c-end"))
    after = add_chapter(original, "c1", ChapterOutline(id="c-after"))

    assert [chapter.id for chapter in at_end[0].chapters] == ["c1", "c2", "c-end"]
    assert [chapter.id for chapter in after[0].chapters] == ["c1", "c-after", "c2"]


def test_add_scene_at_chapter_end_and_after_scene():
    original = _outline()

    at_end = add_scene(original, "c1", SceneOutline(id="s-end"))
    after = add_scene(original, "s1", SceneOutline(id="s-after"))

    assert [scene.id for scene in at_end[0].chapters[0].scenes] == [
        "s1",
        "s2",
        "s-end",
    ]
    assert [scene.id for scene in after[0].chapters[0].scenes] == [
        "s1",
        "s-after",
        "s2",
    ]


@pytest.mark.parametrize(
    ("operation", "item"),
    [
        (add_chapter, ChapterOutline(id="new")),
        (add_scene, SceneOutline(id="new")),
    ],
)
def test_rejects_invalid_insertion_target(operation, item):
    with pytest.raises(ValueError, match="target not found"):
        operation(_outline(), "missing", item)


@pytest.mark.parametrize("node_id", ["v1", "c1", "s1"])
def test_delete_each_node_type(node_id):
    result = delete_node(_outline(), node_id)

    assert find_volume(result, node_id) is None
    assert find_chapter(result, node_id) is None
    assert find_scene(result, node_id) is None


@pytest.mark.parametrize(
    ("node_id", "expected"),
    [
        ("v1", ["v2", "v1"]),
        ("c1", ["c2", "c1"]),
        ("s1", ["s2", "s1"]),
    ],
)
def test_move_each_node_type(node_id, expected):
    result = move_node(_outline(), node_id, 1)

    if node_id.startswith("v"):
        actual = [volume.id for volume in result]
    elif node_id.startswith("c"):
        actual = [chapter.id for chapter in result[0].chapters]
    else:
        actual = [scene.id for scene in result[0].chapters[0].scenes]
    assert actual == expected


@pytest.mark.parametrize("node_id,offset", [("v1", -1), ("c1", -1), ("s1", -1)])
def test_boundary_move_is_noop(node_id, offset):
    original = _outline()

    assert move_node(original, node_id, offset) == original


def test_next_scene_crosses_chapter_and_volume_boundaries():
    volumes = _outline()

    assert find_next_scene(volumes, "s2").id == "s3"
    assert find_next_scene(volumes, "s3").id == "s4"
    assert find_next_scene(volumes, "s4") is None
    assert find_next_scene(volumes, "missing") is None


def test_find_operations_return_typed_nodes():
    volumes = _outline()

    assert find_volume(volumes, "v2").id == "v2"
    assert find_chapter(volumes, "c2").id == "c2"
    assert find_scene(volumes, "s3").id == "s3"
    assert find_volume(volumes, "missing") is None
