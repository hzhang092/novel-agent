from app.pipeline.bible_element_selector import BibleElementSelector, BibleSelectionSeed
from app.storage.bible_models import BibleElementRelation, FactionElement


def test_explicit_references_are_uncapped_and_keep_input_order():
    first = FactionElement(id="first", name="First")
    second = FactionElement(id="second", name="Second")

    selected = BibleElementSelector().select(
        [first, second],
        {"world_element_ids": ["second", "first"]},
        max_auto_elements=0,
    )

    assert [item.element.id for item in selected] == ["first", "second"]
    assert [(item.score, item.reasons) for item in selected] == [
        (1000, ("explicit_scene_reference",)),
        (1000, ("explicit_scene_reference",)),
    ]


def test_always_include_is_uncapped_deduplicated_and_follows_explicit_items():
    always = FactionElement(id="always", name="Always", always_include=True, importance=4)
    explicit = FactionElement(
        id="explicit", name="Explicit", always_include=True, importance=5
    )
    duplicate = always.model_copy(update={"name": "Ignored duplicate"})

    selected = BibleElementSelector().select(
        [always, explicit, duplicate],
        {"world_element_ids": ["explicit"]},
        max_auto_elements=0,
    )

    assert [item.element.id for item in selected] == ["explicit", "always"]
    assert [(item.score, item.reasons) for item in selected] == [
        (1000, ("explicit_scene_reference", "always_include")),
        (840, ("always_include",)),
    ]


def test_text_matches_use_planned_scores_and_exact_reasons():
    elements = [
        FactionElement(id="name", name="Moon Gate", importance=1),
        FactionElement(
            id="alias", name="Hidden Order", aliases=["Black Sect"], importance=2
        ),
        FactionElement(id="substring", name="Jade Seal", importance=3),
        FactionElement(id="tag", name="Iron Guard", tags=["war"], importance=4),
        FactionElement(
            id="tag-substring", name="Quiet Hall", tags=["forbidden"], importance=5
        ),
        FactionElement(
            id="typed",
            name="Crown Keepers",
            description="Obsidian Crown",
            importance=2,
        ),
    ]
    scene = {
        "scene_title": "black sect",
        "location": "ＭＯＯＮ ＧＡＴＥ",
        "scene_goal": "Steal the jade seal tonight",
        "conflict": "WAR",
        "required_plot_beats": [],
        "emotional_turn": "The obsidian crown awakens",
        "ending_hook": "",
        "constraints": ["Avoid forbidden rites"],
        "participating_characters": [],
    }

    selected = BibleElementSelector().select(elements, scene)

    assert [item.element.id for item in selected] == [
        "name",
        "alias",
        "substring",
        "tag",
        "tag-substring",
        "typed",
    ]
    assert [(item.score, item.reasons) for item in selected] == [
        (410, ("exact_name",)),
        (400, ("exact_alias",)),
        (330, ("name_or_alias_substring",)),
        (290, ("exact_tag",)),
        (230, ("tag_substring",)),
        (140, ("summary_or_typed_field_substring",)),
    ]


def test_relationship_expansion_is_incoming_and_outgoing_but_not_recursive():
    root = FactionElement(
        id="root",
        name="Root",
        relationships=[BibleElementRelation(kind="uses", target_element_id="out")],
    )
    outgoing = FactionElement(
        id="out",
        name="Outgoing",
        importance=2,
        relationships=[BibleElementRelation(kind="related_to", target_element_id="deep")],
    )
    incoming = FactionElement(
        id="in",
        name="Incoming",
        importance=3,
        relationships=[BibleElementRelation(kind="controls", target_element_id="root")],
    )
    deep = FactionElement(id="deep", name="Deep")

    selected = BibleElementSelector().select(
        [root, outgoing, incoming, deep],
        {"world_element_ids": ["root"]},
    )

    assert [item.element.id for item in selected] == ["root", "in", "out"]
    assert [(item.score, item.reasons) for item in selected] == [
        (1000, ("explicit_scene_reference",)),
        (110, ("related_to:root:controls",)),
        (100, ("related_to:root:uses",)),
    ]


def test_an_element_selected_by_text_and_relationship_is_returned_once():
    root = FactionElement(
        id="root",
        name="Root",
        relationships=[BibleElementRelation(kind="uses", target_element_id="candidate")],
    )
    candidate = FactionElement(
        id="candidate", name="Candidate", tags=["war"], importance=2
    )

    selected = BibleElementSelector().select(
        [root, candidate],
        {"world_element_ids": ["root"], "conflict": "war"},
    )

    assert [item.element.id for item in selected] == ["root", "candidate"]
    assert selected[1].score == 270
    assert selected[1].reasons == ("exact_tag", "related_to:root:uses")


def test_automatic_cap_uses_score_then_importance_then_input_order():
    first = FactionElement(id="first", name="First", tags=["war"], importance=3)
    second = FactionElement(id="second", name="Second", tags=["war"], importance=3)
    highest = FactionElement(id="highest", name="Highest", tags=["war"], importance=5)
    related = FactionElement(id="related", name="Related", importance=5)
    root = FactionElement(
        id="root",
        name="Root",
        relationships=[BibleElementRelation(kind="uses", target_element_id="related")],
    )
    always = FactionElement(id="always", name="Always", always_include=True)
    irrelevant = FactionElement(id="irrelevant", name="Irrelevant", importance=5)

    selected = BibleElementSelector().select(
        [first, second, highest, related, root, always, irrelevant],
        {"world_element_ids": ["root"], "conflict": "war"},
        max_auto_elements=2,
    )

    assert [item.element.id for item in selected] == ["root", "always", "highest", "first"]
    assert [item.score for item in selected] == [1000, 830, 300, 280]


def test_character_connection_seed_selects_element_with_traceable_reason():
    faction = FactionElement(id="faction", name="Jade Sect")

    selected = BibleElementSelector().select(
        [faction],
        {},
        character_seeds=[
            BibleSelectionSeed(
                element_id="faction",
                reason="character_relation:hero:member_of",
                score=650,
            )
        ],
    )

    assert [(item.element.id, item.score, item.reasons) for item in selected] == [
        ("faction", 650, ("character_relation:hero:member_of",))
    ]


def test_character_connection_seed_expands_one_relationship_hop_only():
    faction = FactionElement(
        id="faction",
        name="Jade Sect",
        relationships=[
            BibleElementRelation(kind="uses", target_element_id="power")
        ],
    )
    power = FactionElement(
        id="power",
        name="Moon Art",
        relationships=[
            BibleElementRelation(kind="related_to", target_element_id="deep")
        ],
    )
    deep = FactionElement(id="deep", name="Deep")

    selected = BibleElementSelector().select(
        [faction, power, deep],
        {},
        character_seeds=[
            BibleSelectionSeed(
                element_id="faction",
                reason="character_relation:hero:uses",
                score=650,
            )
        ],
    )

    assert [item.element.id for item in selected] == ["faction", "power"]
    assert selected[1].reasons == ("related_to:faction:uses",)
