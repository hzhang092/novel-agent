from datetime import datetime

import pytest
from PyQt6.QtCore import Qt

from app.storage.bible_models import (
    BibleElementRelation,
    BibleRelationKind,
    FactionElement,
    HistoricalEventElement,
    LocationElement,
    PowerRealm,
    PowerSystemElement,
    TerminologyElement,
)
from app.ui.bible_element_editor import BibleElementEditor


@pytest.mark.parametrize(
    "element",
    [
        FactionElement(
            id="f1", name="青云宗", aliases=["剑宗"], summary="正道宗门",
            tags=["正道"], importance=4, always_include=True,
            description="山中宗门", goals=["守护天下"], ideology="守序",
        ),
        TerminologyElement(
            id="t1", name="灵石", definition="修行货币", category="资源",
            examples=["上品灵石"],
        ),
        HistoricalEventElement(
            id="h1", name="正魔大战", time_label="百年前", description="大战爆发",
            consequences=["宗门衰落"],
        ),
        PowerSystemElement(
            id="p1", name="九重天境",
            realms=[PowerRealm(name="炼气", abilities=["御气", "强身"])],
            limitations=["需灵根"], costs=["寿元"], rare_resources=["灵石"],
            forbidden_methods=["夺舍"],
        ),
        LocationElement(
            id="l1", name="青云山", description="高山", atmosphere="清冷",
            notable_features=["剑峰"],
        ),
    ],
)
def test_editor_load_gather_round_trips_each_typed_element(element, qtbot):
    editor = BibleElementEditor()
    qtbot.addWidget(editor)

    editor.load_element(element, elements=[element])

    assert editor.gather_element() == element
    assert editor.is_dirty is False


def test_editor_common_fields_are_semantic_and_preserve_storage_metadata(qtbot):
    created = datetime(2024, 1, 1)
    updated = datetime(2024, 2, 1)
    element = FactionElement(
        id="f1", name="青云宗", revision=7, created_at=created, updated_at=updated
    )
    editor = BibleElementEditor()
    qtbot.addWidget(editor)
    dirty = []
    editor.dirty_changed.connect(dirty.append)
    editor.load_element(element)

    editor._name.setText(" 新青云宗 ")
    editor._aliases.set_items(["剑宗"])
    editor._summary.setPlainText("新的概要")
    editor._tags.set_items(["正道"])
    editor._importance.setValue(5)
    editor._always_include.setChecked(True)
    gathered = editor.gather_element()

    assert editor.is_dirty is True
    assert dirty[-1] is True
    assert (gathered.id, gathered.revision, gathered.created_at, gathered.updated_at) == (
        "f1", 7, created, updated
    )
    assert gathered.name == "新青云宗"
    assert gathered.aliases == ["剑宗"]
    assert gathered.summary == "新的概要"
    assert gathered.tags == ["正道"]
    assert gathered.importance == 5
    assert gathered.always_include is True


def test_editor_relations_use_target_ids_exclude_self_and_show_missing(qtbot):
    element = FactionElement(
        id="f1",
        name="青云宗",
        relationships=[
            BibleElementRelation(
                kind=BibleRelationKind.LOCATED_IN,
                target_element_id="missing-faction",
                note="旧敌",
            )
        ],
    )
    target = LocationElement(id="l1", name="青云宗")
    editor = BibleElementEditor()
    qtbot.addWidget(editor)
    editor.load_element(element, elements=[element, target])

    target_combo = editor._relations.cellWidget(0, 1)
    assert target_combo.findData("f1") == -1
    assert target_combo.findData("l1") >= 0
    assert "Missing" in target_combo.currentText()
    assert editor.gather_element().relationships == element.relationships


def test_relation_kind_filters_target_types_and_previews_both_directions(qtbot):
    element = FactionElement(id="f1", name="Jade Sect")
    faction = FactionElement(id="f2", name="Moon Sect")
    location = LocationElement(id="l1", name="Jade Peak")
    editor = BibleElementEditor()
    qtbot.addWidget(editor)
    editor.load_element(element, elements=[element, faction, location])

    editor._add_empty_relation()
    kind = editor._relations.cellWidget(0, 0)
    target = editor._relations.cellWidget(0, 1)
    kind.setCurrentIndex(kind.findData(BibleRelationKind.LOCATED_IN))

    assert target.view().isRowHidden(target.findData("f2"))
    assert not target.view().isRowHidden(target.findData("l1"))

    target.setCurrentIndex(target.findData("l1"))
    assert "Jade Sect — Located in → Jade Peak" in editor._relation_preview.text()
    assert "Jade Peak will display: Contains Jade Sect" in editor._relation_preview.text()


def test_relationship_target_search_matches_name_alias_and_tag(qtbot):
    element = FactionElement(
        id="f1",
        name="青云宗",
        relationships=[
            BibleElementRelation(kind=BibleRelationKind.USES, target_element_id="l1")
        ],
    )
    target = LocationElement(
        id="l1", name="Jade Mountain", aliases=["Sword Peak"], tags=["Orthodox"]
    )
    other = LocationElement(id="l2", name="Abyss", tags=["Demonic"])
    editor = BibleElementEditor()
    qtbot.addWidget(editor)
    editor.load_element(element, elements=[element, target, other])
    target_combo = editor._relations.cellWidget(0, 1)

    for query in ("jade", "SWORD", "orthodox"):
        target_combo.lineEdit().clear()
        qtbot.keyClicks(target_combo.lineEdit(), query)
        visible_ids = [
            target_combo.itemData(index)
            for index in range(target_combo.count())
            if not target_combo.view().isRowHidden(index)
        ]
        assert visible_ids == ["l1"]

    target_combo.setCurrentIndex(target_combo.findData("l1"))
    assert editor.gather_element().relationships[0].target_element_id == "l1"


def test_editor_shows_inbound_relations_with_inverse_label(qtbot):
    current = LocationElement(id="l1", name="青云山")
    source = FactionElement(id="f1", name="青云宗")
    relation = BibleElementRelation(
        kind=BibleRelationKind.CONTROLS, target_element_id="l1"
    )
    editor = BibleElementEditor()
    qtbot.addWidget(editor)
    requested = []
    editor.element_requested.connect(requested.append)

    editor.load_element(current, elements=[current, source], inbound_relations=[(source, relation)])
    item = editor._inbound.topLevelItem(0)

    assert item.text(0) == "青云宗 — Controlled by"
    editor._inbound.itemActivated.emit(item, 0)
    assert requested == ["f1"]
