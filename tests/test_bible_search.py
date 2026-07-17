from app.domain.bible_search import search_elements
from app.storage.bible_models import (
    BibleElementRelation,
    FactionElement,
    LocationElement,
    TerminologyElement,
)


def elements():
    return [
        FactionElement(
            id="f1",
            name="青云宗",
            aliases=["QingYun"],
            summary="正道第一宗门",
            tags=["宗门", "正道"],
            importance=4,
            relationships=[BibleElementRelation(kind="opposed_to", target_element_id="f2")],
        ),
        FactionElement(id="f2", name="魔渊殿", summary="魔道势力", importance=5),
        LocationElement(id="l1", name="青云山脉", atmosphere="云雾缭绕", tags=["宗门"]),
        TerminologyElement(id="t1", name="Spirit Stone", aliases=["灵石"], definition="修炼货币"),
    ]


def test_search_ranks_exact_name_alias_tag_and_substring_matches():
    items = elements()

    assert search_elements(items, query="青云宗", target_names={"f2": "魔渊殿"})[0].id == "f1"
    assert search_elements(items, query="ＱＩＮＧＹＵＮ")[0].id == "f1"
    assert search_elements(items, query="灵石")[0].id == "t1"
    assert [item.id for item in search_elements(items, query="青云")] == ["f1", "l1"]


def test_search_matches_all_terms_and_type_specific_or_relationship_text():
    items = elements()

    assert [item.id for item in search_elements(items, query="正道 宗门")] == ["f1"]
    assert [item.id for item in search_elements(items, query="云雾")] == ["l1"]
    assert [item.id for item in search_elements(
        items, query="魔渊殿", target_names={"f2": "魔渊殿"}
    )] == ["f2", "f1"]


def test_search_filters_by_type_tags_always_include_and_reference():
    items = elements()
    items[1] = items[1].model_copy(update={"always_include": True})

    assert [item.id for item in search_elements(items, type_filter="faction", tag_filters=["宗门"])] == ["f1"]
    assert [item.id for item in search_elements(items, always_included=True)] == ["f2"]
    assert [item.id for item in search_elements(items, referenced_ids={"l1"})] == ["l1"]


def test_importance_breaks_equal_rank_before_manifest_order():
    low = FactionElement(id="low", name="甲宗", summary="共同文本", importance=2)
    high = FactionElement(id="high", name="乙宗", summary="共同文本", importance=5)

    assert [item.id for item in search_elements([low, high], query="共同")] == ["high", "low"]
