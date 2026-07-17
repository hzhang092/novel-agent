import pytest

from app.storage.bible_models import (
    BibleElementRelation,
    BibleElementType,
    FactionElement,
    LocationElement,
    TerminologyElement,
    WorldOverview,
)
from app.storage.models import PowerSystem, StyleGuide, WorldSetting
from app.utils.template_merge import (
    StoryTemplate,
    TemplateMergeMode,
    apply_story_template,
    merge_style_guide,
    merge_world_setting,
    preview_story_template_replace,
)


def _template(*elements, overview=None) -> StoryTemplate:
    return StoryTemplate(
        template_id="test",
        name="Test",
        world_overview=overview or WorldOverview(),
        elements=list(elements),
        style_guide=StyleGuide(),
    )


def test_fill_empty_elements_preserves_identity_and_author_metadata() -> None:
    existing_relation = BibleElementRelation(
        kind="located_in", target_element_id="location-1", note="作者关系"
    )
    current = FactionElement(
        id="project-faction",
        name="青云宗",
        summary="",
        tags=["作者标签"],
        importance=5,
        relationships=[existing_relation],
        description="作者描述",
        goals=[],
    )
    incoming = FactionElement(
        id="template-faction",
        name=" 青云宗 ",
        summary="模板摘要",
        tags=["模板标签"],
        importance=1,
        relationships=[],
        description="模板描述",
        goals=["模板目标"],
    )
    term = TerminologyElement(id="template-term", name="灵石", definition="货币")

    result = apply_story_template(
        WorldOverview(geography="作者地理"),
        [current, LocationElement(id="location-1", name="青云山")],
        StyleGuide(tone="作者基调"),
        _template(
            incoming,
            term,
            overview=WorldOverview(
                geography="模板地理", rules=["模板规则"], technology_level="模板科技"
            ),
        ),
        TemplateMergeMode.FILL_EMPTY,
    )

    faction = next(item for item in result.elements if item.element_type == "faction")
    added_term = next(item for item in result.elements if item.element_type == "terminology")
    assert result.world_overview.geography == "作者地理"
    assert result.world_overview.rules == ["模板规则"]
    assert result.world_overview.technology_level == "模板科技"
    assert result.style_guide.tone == "作者基调"
    assert faction.id == "project-faction"
    assert faction.summary == "模板摘要"
    assert faction.description == "作者描述"
    assert faction.goals == ["模板目标"]
    assert faction.tags == ["作者标签"]
    assert faction.importance == 5
    assert faction.relationships == [existing_relation]
    assert added_term.id != "template-term"
    assert added_term.definition == "货币"


@pytest.mark.parametrize("mode", list(TemplateMergeMode))
def test_template_application_rejects_ambiguous_project_element_identity(
    mode: TemplateMergeMode,
) -> None:
    current = [
        FactionElement(id="first", name="Spirit Order"),
        FactionElement(id="second", name="ＳＰＩＲＩＴ ＯＲＤＥＲ"),
    ]
    template = _template(FactionElement(id="template", name=" spirit order "))

    with pytest.raises(ValueError, match="Ambiguous project elements"):
        apply_story_template(
            WorldOverview(), current, StyleGuide(), template, mode
        )


def test_template_application_rejects_duplicate_template_element_identity() -> None:
    template = _template(
        FactionElement(id="first", name="Spirit Order"),
        FactionElement(id="second", name="ＳＰＩＲＩＴ ＯＲＤＥＲ"),
    )

    with pytest.raises(ValueError, match="Duplicate template elements"):
        apply_story_template(
            WorldOverview(), [], StyleGuide(), template, TemplateMergeMode.MERGE
        )


@pytest.mark.parametrize("mode", list(TemplateMergeMode))
def test_story_template_application_does_not_mutate_its_inputs(
    mode: TemplateMergeMode,
) -> None:
    overview = WorldOverview(geography="作者地理", rules=["作者规则"])
    elements = [
        FactionElement(id="project", name="青云宗", tags=["作者标签"]),
        LocationElement(id="location", name="青云山"),
    ]
    style = StyleGuide(tone="作者基调", taboo_patterns=["作者禁忌"])
    template = StoryTemplate(
        template_id="test",
        name="Test",
        world_overview=WorldOverview(rules=["模板规则"]),
        elements=[
            FactionElement(id="template", name="青云宗", tags=["模板标签"])
        ],
        style_guide=StyleGuide(taboo_patterns=["模板禁忌"]),
    )
    snapshots = (
        overview.model_copy(deep=True),
        [element.model_copy(deep=True) for element in elements],
        style.model_copy(deep=True),
        template.model_copy(deep=True),
    )

    result = apply_story_template(overview, elements, style, template, mode)
    result.world_overview.rules.append("修改结果")
    result.elements[0].tags.append("修改结果")
    result.style_guide.taboo_patterns.append("修改结果")

    assert overview == snapshots[0]
    assert elements == snapshots[1]
    assert style == snapshots[2]
    assert template == snapshots[3]


def test_merge_remaps_template_relationship_targets_to_project_ids() -> None:
    current_qingyun = FactionElement(
        id="project-qingyun",
        name="青云宗",
        goals=["已有目标"],
        relationships=[
            BibleElementRelation(
                kind="opposed_to", target_element_id="project-moyuan", note="作者说明"
            )
        ],
    )
    current_moyuan = FactionElement(id="project-moyuan", name="魔渊殿")
    template_qingyun = FactionElement(
        id="template-qingyun",
        name="青云宗",
        goals=["已有目标", "模板目标"],
        relationships=[
            BibleElementRelation(
                kind="opposed_to", target_element_id="template-moyuan", note="模板说明"
            )
        ],
    )
    template_moyuan = FactionElement(id="template-moyuan", name="魔渊殿")

    result = apply_story_template(
        WorldOverview(rules=["已有规则"]),
        [current_qingyun, current_moyuan],
        StyleGuide(),
        _template(
            template_qingyun,
            template_moyuan,
            overview=WorldOverview(rules=["已有规则", "模板规则"]),
        ),
        TemplateMergeMode.MERGE,
    )

    qingyun = next(item for item in result.elements if item.id == "project-qingyun")
    assert result.world_overview.rules == ["已有规则", "模板规则"]
    assert qingyun.goals == ["已有目标", "模板目标"]
    assert qingyun.relationships == [
        BibleElementRelation(
            kind="opposed_to", target_element_id="project-moyuan", note="作者说明"
        )
    ]


def test_replace_reports_exact_counts_and_retains_unmanaged_locations() -> None:
    current = [
        FactionElement(id="existing-qingyun", name="青云宗", description="旧内容"),
        FactionElement(id="obsolete", name="旧宗门"),
        LocationElement(id="location-1", name="青云山"),
        LocationElement(id="location-2", name="魔渊"),
        LocationElement(id="location-3", name="天机城"),
    ]
    template = _template(
        FactionElement(id="template-qingyun", name="青云宗", description="新内容"),
        TerminologyElement(id="template-term", name="灵石", definition="货币"),
        overview=WorldOverview(
            geography="新地理",
            rules=["新规则"],
            taboos=["新禁忌"],
            technology_level="新科技",
            social_structure="新社会",
        ),
    )

    preview = preview_story_template_replace(current, template)
    result = apply_story_template(
        WorldOverview(geography="旧地理"),
        current,
        StyleGuide(),
        template,
        TemplateMergeMode.REPLACE,
    )

    assert preview.overview_fields_replaced == 5
    assert preview.elements_replaced == {
        BibleElementType.FACTION: 1,
        BibleElementType.TERMINOLOGY: 1,
    }
    assert preview.unaffected_elements == {BibleElementType.LOCATION: 3}
    assert [item.id for item in result.elements if item.element_type == "location"] == [
        "location-1", "location-2", "location-3"
    ]
    factions = [item for item in result.elements if item.element_type == "faction"]
    assert len(factions) == 1
    assert factions[0].id == "existing-qingyun"
    assert factions[0].description == "新内容"
    assert all(item.id != "obsolete" for item in result.elements)


def test_merge_style_preserves_scalars_and_deduplicates_trimmed_patterns() -> None:
    current = StyleGuide(
        pacing="偏慢",
        dialogue_density="",
        taboo_patterns=[" 已有禁忌 "],
        preferred_patterns=["共有偏好"],
        reference_passages=[" 已有段落 "],
    )
    template = StyleGuide(
        pacing="很快",
        dialogue_density="适中",
        taboo_patterns=["已有禁忌", " 新禁忌 ", "新禁忌"],
        preferred_patterns=[" 共有偏好 ", "模板偏好"],
        reference_passages=["已有段落", " 新段落 "],
    )

    result = merge_style_guide(current, template, TemplateMergeMode.MERGE)

    assert result.pacing == "偏慢"
    assert result.dialogue_density == "适中"
    assert result.taboo_patterns == ["已有禁忌", "新禁忌"]
    assert result.preferred_patterns == ["共有偏好", "模板偏好"]
    assert result.reference_passages == ["已有段落", "新段落"]


def test_legacy_fill_empty_merge_helpers_remain_compatible() -> None:
    current_world = WorldSetting(
        geography="已有地理",
        factions=[{"name": "已有宗门"}],
        rules=[],
    )
    template_world = WorldSetting(
        geography="模板地理",
        power_system=PowerSystem(realms=["炼气"]),
        factions=[{"name": "模板宗门"}],
        rules=["模板规则"],
    )
    current_style = StyleGuide(pacing="偏慢", taboo_patterns=["已有禁忌"])
    template_style = StyleGuide(
        pacing="很快",
        dialogue_density="适中",
        taboo_patterns=["模板禁忌"],
    )

    world = merge_world_setting(
        current_world, template_world, TemplateMergeMode.FILL_EMPTY
    )
    style = merge_style_guide(current_style, template_style, TemplateMergeMode.FILL_EMPTY)

    assert world.geography == "已有地理"
    assert world.factions == [{"name": "已有宗门"}]
    assert world.rules == ["模板规则"]
    assert world.power_system == PowerSystem(realms=["炼气"])
    assert style.pacing == "偏慢"
    assert style.dialogue_density == "适中"
    assert style.taboo_patterns == ["已有禁忌"]


def test_legacy_merge_and_replace_helpers_remain_compatible() -> None:
    current = WorldSetting(
        power_system=PowerSystem(realms=["筑基"], abilities={"筑基": "已有能力"}),
        factions=[{"name": " 青云宗 ", "description": "", "goals": "已有目标"}],
    )
    template = WorldSetting(
        power_system=PowerSystem(
            realms=["炼气", "筑基"],
            abilities={"炼气": "基础法术", "筑基": "模板能力"},
        ),
        factions=[
            {"name": "青云宗", "description": "模板描述", "goals": "模板目标"},
            {"name": "天机阁", "description": "情报组织", "goals": "收集情报"},
        ],
    )

    merged = merge_world_setting(current, template, TemplateMergeMode.MERGE)
    replaced = merge_world_setting(current, template, TemplateMergeMode.REPLACE)

    assert merged.power_system.realms == ["筑基", "炼气"]
    assert merged.power_system.abilities == {"筑基": "已有能力", "炼气": "基础法术"}
    assert merged.factions == [
        {"name": " 青云宗 ", "description": "模板描述", "goals": "已有目标"},
        {"name": "天机阁", "description": "情报组织", "goals": "收集情报"},
    ]
    assert replaced == template
    replaced.factions.append({"name": "表单修改"})
    assert len(template.factions) == 2
