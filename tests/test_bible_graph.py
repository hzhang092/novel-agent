import pytest

from app.domain.bible_graph import (
    relation_views,
    related_element_ids,
    unlink_element_relations,
    unlink_scene_references,
)
from app.storage.bible_models import BibleElementRelation, FactionElement
from app.storage.models import ChapterOutline, SceneOutline, VolumeOutline


def graph_elements():
    return [
        FactionElement(
            id="a",
            name="青云宗",
            relationships=[
                BibleElementRelation(kind="controls", target_element_id="b"),
                BibleElementRelation(kind="opposed_to", target_element_id="c"),
            ],
        ),
        FactionElement(id="b", name="东部联盟"),
        FactionElement(id="c", name="魔渊殿"),
        FactionElement(
            id="d",
            name="旁观者",
            relationships=[BibleElementRelation(kind="uses", target_element_id="a")],
        ),
    ]


def test_relation_views_derive_outgoing_and_inverse_labels():
    views = relation_views(graph_elements(), "b")

    assert [(view.source_id, view.target_id, view.label, view.inbound) for view in views] == [
        ("a", "b", "Controlled by", True)
    ]


def test_symmetric_relation_has_the_same_label_from_either_end():
    assert relation_views(graph_elements(), "c")[0].label == "Opposed to"
    assert relation_views(graph_elements(), "a")[1].label == "Opposed to"


def test_related_element_ids_traverses_one_outgoing_and_inbound_hop_only():
    elements = graph_elements()

    assert related_element_ids(elements, {"a"}) == {"b", "c", "d"}
    assert "b" not in related_element_ids(elements, {"d"})


def test_unlink_element_relations_removes_inbound_edges_without_mutating_input():
    elements = graph_elements()
    unlinked = unlink_element_relations(elements, "a")

    assert [element.id for element in unlinked] == ["b", "c", "d"]
    assert unlinked[-1].relationships == []
    assert elements[-1].relationships


def test_unlink_scene_references_removes_ids_from_all_volumes():
    volume = VolumeOutline(
        id="v1",
        chapters=[ChapterOutline(
            id="c1",
            scenes=[SceneOutline(id="s1", world_element_ids=["a", "b", "a"])],
        )],
    )

    cleaned = unlink_scene_references([volume], "a")

    assert cleaned[0].chapters[0].scenes[0].world_element_ids == ["b"]
    assert volume.chapters[0].scenes[0].world_element_ids == ["a", "b", "a"]


def test_relation_helpers_reject_unknown_source_element():
    with pytest.raises(KeyError):
        relation_views(graph_elements(), "missing")
