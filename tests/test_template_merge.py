from app.storage.models import PowerSystem, StyleGuide, WorldSetting
from app.utils.template_merge import (
    TemplateMergeMode,
    merge_style_guide,
    merge_world_setting,
)
from app.utils.xianxia_template import get_xianxia_template


def test_fill_empty_world_uses_template_only_for_empty_fields() -> None:
    current = WorldSetting(
        geography="已有地理",
        factions=[{"name": "已有宗门"}],
        history="已有历史",
        rules=[],
        technology_level="已有科技",
        terminology={},
    )
    template = WorldSetting(
        geography="模板地理",
        power_system=PowerSystem(realms=["炼气"]),
        factions=[{"name": "模板宗门"}],
        history="模板历史",
        rules=["模板规则"],
        technology_level="模板科技",
        terminology={"灵石": "货币"},
    )

    result = merge_world_setting(current, template, TemplateMergeMode.FILL_EMPTY)

    assert result == WorldSetting(
        geography="已有地理",
        power_system=PowerSystem(realms=["炼气"]),
        factions=[{"name": "已有宗门"}],
        history="已有历史",
        rules=["模板规则"],
        technology_level="已有科技",
        terminology={"灵石": "货币"},
    )
    assert current.power_system is None
    assert template.power_system == PowerSystem(realms=["炼气"])


def test_fill_empty_style_uses_template_only_for_empty_fields() -> None:
    current = StyleGuide(
        pacing="偏慢",
        tone="已有基调",
        taboo_patterns=["已有禁忌"],
        preferred_patterns=[],
        reference_passages=[],
    )
    template = StyleGuide(
        pacing="很快",
        dialogue_density="适中",
        tone="热血",
        taboo_patterns=["模板禁忌"],
        preferred_patterns=["模板偏好"],
        reference_passages=["模板段落"],
    )

    result = merge_style_guide(current, template, TemplateMergeMode.FILL_EMPTY)

    assert result == StyleGuide(
        pacing="偏慢",
        dialogue_density="适中",
        tone="已有基调",
        taboo_patterns=["已有禁忌"],
        preferred_patterns=["模板偏好"],
        reference_passages=["模板段落"],
    )


def test_merge_world_preserves_current_data_and_merges_power_system() -> None:
    current = WorldSetting(
        geography="已有地理",
        power_system=PowerSystem(
            realms=["筑基", "金丹"],
            abilities={"筑基": "已有能力"},
            limitations=["已有约束"],
        ),
        history="",
        rules=["共有规则", "已有规则"],
        terminology={"灵石": "已有定义"},
    )
    template = WorldSetting(
        geography="模板地理",
        power_system=PowerSystem(
            realms=["炼气", "筑基"],
            abilities={"筑基": "模板能力", "炼气": "基础法术"},
            limitations=["共有约束", "已有约束"],
            costs=["消耗灵石"],
        ),
        history="模板历史",
        rules=["模板规则", "共有规则"],
        terminology={"灵石": "模板定义", "灵根": "修炼资质"},
    )

    result = merge_world_setting(current, template, TemplateMergeMode.MERGE)

    assert result.geography == "已有地理"
    assert result.history == "模板历史"
    assert result.rules == ["共有规则", "已有规则", "模板规则"]
    assert result.terminology == {"灵石": "已有定义", "灵根": "修炼资质"}
    assert result.power_system == PowerSystem(
        realms=["筑基", "金丹", "炼气"],
        abilities={"筑基": "已有能力", "炼气": "基础法术"},
        limitations=["已有约束", "共有约束"],
        costs=["消耗灵石"],
    )
    assert current.power_system.realms == ["筑基", "金丹"]


def test_merge_world_matches_factions_by_normalized_name() -> None:
    current = WorldSetting(
        factions=[
            {
                "name": " 青云宗 ",
                "description": "",
                "goals": "已有目标",
                "note": "保留附注",
            },
            {"name": "魔渊殿", "description": "已有描述", "goals": ""},
        ]
    )
    template = WorldSetting(
        factions=[
            {"name": "青云宗", "description": "模板描述", "goals": "模板目标"},
            {"name": " 魔渊殿 ", "description": "模板魔殿", "goals": "模板魔目标"},
            {"name": "天机阁", "description": "情报组织", "goals": "收集情报"},
        ]
    )

    result = merge_world_setting(current, template, TemplateMergeMode.MERGE)

    assert result.factions == [
        {
            "name": " 青云宗 ",
            "description": "模板描述",
            "goals": "已有目标",
            "note": "保留附注",
        },
        {"name": "魔渊殿", "description": "已有描述", "goals": "模板魔目标"},
        {"name": "天机阁", "description": "情报组织", "goals": "收集情报"},
    ]


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


def test_replace_world_returns_an_independent_copy_of_complete_template() -> None:
    current = WorldSetting(geography="已有地理", rules=["已有规则"])
    template = WorldSetting(
        geography="模板地理",
        power_system=PowerSystem(realms=["炼气"]),
        rules=["模板规则"],
    )

    result = merge_world_setting(current, template, TemplateMergeMode.REPLACE)

    assert result == template
    result.rules.append("表单修改")
    result.power_system.realms.append("筑基")
    assert template.rules == ["模板规则"]
    assert template.power_system.realms == ["炼气"]


def test_replace_style_returns_an_independent_copy_of_complete_template() -> None:
    current = StyleGuide(pacing="偏慢", taboo_patterns=["已有禁忌"])
    template = StyleGuide(pacing="很快", taboo_patterns=["模板禁忌"])

    result = merge_style_guide(current, template, TemplateMergeMode.REPLACE)

    assert result == template
    result.taboo_patterns.append("表单修改")
    assert template.taboo_patterns == ["模板禁忌"]


def test_xianxia_style_values_match_current_control_options() -> None:
    _, style = get_xianxia_template()

    assert (
        style.pacing,
        style.dialogue_density,
        style.description_style,
        style.tone,
        style.sentence_length,
        style.pov,
    ) == ("很快", "适中", "简练", "热血", "短句多", "第三人称")
