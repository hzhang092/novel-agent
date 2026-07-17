from pathlib import Path

import pytest
import yaml

from app.storage.bible_models import (
    BibleElementRelation,
    BibleManifest,
    BibleRelationKind,
    FactionElement,
    PowerSystemElement,
    TerminologyElement,
)
from app.storage.bible_repository import BibleElementRepository


def repository(tmp_path: Path) -> BibleElementRepository:
    elements_dir = tmp_path / "bible" / "elements"
    elements_dir.mkdir(parents=True)
    (tmp_path / "bible" / "manifest.yaml").write_text(
        yaml.safe_dump(BibleManifest().model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return BibleElementRepository(tmp_path)


def test_create_load_update_noop_and_delete(tmp_path):
    repo = repository(tmp_path)
    created = repo.create(FactionElement(id="f1", name="青云宗"))

    assert repo.load("f1") == created
    assert [element.id for element in repo.load_all()] == ["f1"]
    assert repo.load_manifest().element_order == ["f1"]

    no_op = repo.save(created.model_copy(update={"updated_at": created.updated_at}))
    assert no_op.revision == 1
    assert repo.load_manifest().content_revision == 2

    updated = repo.save(created.model_copy(update={"summary": "正道第一宗门"}))
    assert updated.revision == 2
    assert repo.load_manifest().content_revision == 3

    repo.delete("f1")
    assert repo.load_all() == []
    assert repo.load_manifest().content_revision == 4


def test_create_and_save_use_atomic_replace(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    replacements: list[tuple[Path, Path]] = []
    from app.storage import bible_repository

    real_replace = bible_repository.os.replace

    def record_replace(source, target):
        replacements.append((Path(source), Path(target)))
        real_replace(source, target)

    monkeypatch.setattr(bible_repository.os, "replace", record_replace)
    repo.create(FactionElement(id="f1", name="青云宗"))

    assert any(source.suffix == ".tmp" and target.name == "f1.yaml" for source, target in replacements)
    assert replacements[-1][1].name == "manifest.yaml"


def test_primary_power_system_and_reorder_are_persisted(tmp_path):
    repo = repository(tmp_path)
    repo.create(PowerSystemElement(id="p1", name="九重天境"))
    repo.create(PowerSystemElement(id="p2", name="灵术"))
    repo.set_primary_power_system("p2")
    repo.reorder(["p2", "p1"])

    manifest = repo.load_manifest()
    assert manifest.primary_power_system_id == "p2"
    assert manifest.element_order == ["p2", "p1"]


def test_rejects_duplicate_normalized_terminology_names(tmp_path):
    repo = repository(tmp_path)
    repo.create(TerminologyElement(id="t1", name="Spirit Stone"))

    with pytest.raises(ValueError, match="unique"):
        repo.create(TerminologyElement(id="t2", name="ＳＰＩＲＩＴ ＳＴＯＮＥ"))


def test_graph_validation_rejects_missing_self_duplicate_and_symmetric_edges(tmp_path):
    repo = repository(tmp_path)
    first = repo.create(FactionElement(id="f1", name="青云宗"))
    second = repo.create(FactionElement(id="f2", name="魔渊殿"))

    with pytest.raises(ValueError, match="itself"):
        repo.save(first.model_copy(update={"relationships": [
            BibleElementRelation(kind="related_to", target_element_id="f1")
        ]}))
    with pytest.raises(ValueError, match="missing"):
        repo.save(first.model_copy(update={"relationships": [
            BibleElementRelation(kind="uses", target_element_id="gone")
        ]}))
    relation = BibleElementRelation(kind="opposed_to", target_element_id="f2")
    with pytest.raises(ValueError, match="duplicate"):
        repo.save(first.model_copy(update={"relationships": [relation, relation]}))

    first = repo.save(first.model_copy(update={"relationships": [relation]}))
    with pytest.raises(ValueError, match="symmetric"):
        repo.save(second.model_copy(update={"relationships": [
            BibleElementRelation(kind="opposed_to", target_element_id="f1")
        ]}))


def test_inbound_relationships_are_derived(tmp_path):
    repo = repository(tmp_path)
    first = repo.create(FactionElement(id="f1", name="青云宗"))
    repo.create(FactionElement(id="f2", name="魔渊殿"))
    relation = BibleElementRelation(
        kind=BibleRelationKind.OPPOSED_TO,
        target_element_id="f2",
        note="长期敌对",
    )
    repo.save(first.model_copy(update={"relationships": [relation]}))

    inbound = repo.get_inbound_relations("f2")
    assert [(source.id, edge.note) for source, edge in inbound] == [("f1", "长期敌对")]
