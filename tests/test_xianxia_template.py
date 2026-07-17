"""Tests for the typed Xianxia Story Template."""

from collections import Counter

from app.storage.bible_models import (
    BibleElementType,
    FactionElement,
    HistoricalEventElement,
    PowerRealm,
    PowerSystemElement,
    TerminologyElement,
    WorldOverview,
)
from app.storage.models import StyleGuide
from app.utils.template_merge import StoryTemplate
from app.utils.xianxia_template import get_xianxia_template


def test_xianxia_template_builds_thirteen_typed_story_elements() -> None:
    template = get_xianxia_template()

    assert isinstance(template, StoryTemplate)
    assert template.template_id == "xianxia"
    assert template.name == "修仙"
    assert template.world_overview == WorldOverview(
        geography=(
            "东荒大陆，广袤无垠。东部临海，西部荒漠，南部群山，北部冰原。"
            "中央为中原九州，修士云集之地。"
        ),
        rules=[
            "修士不可对凡人出手，违者天谴",
            "秘境百年开启一次，进入者限骨龄三十以下",
            "元婴以上修士不得在凡人城市全力出手",
            "宗门大比每十年一次，决定资源分配",
        ],
        taboos=["修炼魔功", "背叛师门", "残害同门", "勾结魔道"],
        technology_level="修仙文明，凡人处于封建时代",
        social_structure="宗门制，强者为尊。宗门 > 皇朝 > 世家 > 凡人。",
    )
    assert len(template.elements) == 13
    assert Counter(element.element_type for element in template.elements) == {
        BibleElementType.FACTION: 5,
        BibleElementType.TERMINOLOGY: 6,
        BibleElementType.HISTORICAL_EVENT: 1,
        BibleElementType.POWER_SYSTEM: 1,
    }
    expected_elements = [
        FactionElement(
            id="xianxia-faction-1",
            name="青云宗",
            description="正道第一宗门，以剑修闻名，坐落于青云山脉。",
            goals=["维护大陆秩序，对抗魔道势力"],
        ),
        FactionElement(
            id="xianxia-faction-2",
            name="魔渊殿",
            description="魔道最强势力，隐藏于地底魔渊，行事诡秘。",
            goals=["收集上古魔器，打开魔界通道"],
        ),
        FactionElement(
            id="xianxia-faction-3",
            name="天机阁",
            description="中立的商业情报组织，遍布大陆各城。",
            goals=["收集天下情报，垄断修炼资源交易"],
        ),
        FactionElement(
            id="xianxia-faction-4",
            name="散修联盟",
            description="无门无派的散修聚集组织，以自由为信条。",
            goals=["为散修争取修炼资源，互帮互助"],
        ),
        FactionElement(
            id="xianxia-faction-5",
            name="大楚皇朝",
            description="凡间最强世俗政权，皇室拥有祖传修炼功法。",
            goals=["统一大陆，皇权凌驾于宗门之上"],
        ),
        HistoricalEventElement(
            id="xianxia-history-1",
            name="世界历史",
            description=(
                "万年前神魔大战，仙界通道崩毁，大陆灵气溃散。"
                "千年前灵气复苏，修仙文明重新崛起。"
                "五百年前正魔大战，双方元气大伤，进入冷战期。"
                "如今大陆表面和平，暗流涌动。"
            ),
        ),
        PowerSystemElement(
            id="xianxia-power-1",
            name="修仙体系",
            always_include=True,
            realms=[
                PowerRealm(name="炼气", abilities=["灵气感知，基础法术"]),
                PowerRealm(name="筑基", abilities=["御器飞行，法术增强"]),
                PowerRealm(name="金丹", abilities=["金丹领域，本命法宝"]),
                PowerRealm(name="元婴", abilities=["元婴出窍，神识覆盖"]),
                PowerRealm(name="化神", abilities=["化神分魂，法则初悟"]),
                PowerRealm(name="炼虚", abilities=["虚空穿梭，炼化空间"]),
                PowerRealm(name="合体", abilities=["身与道合，神通大成"]),
                PowerRealm(name="大乘", abilities=["渡劫准备，天地共鸣"]),
                PowerRealm(name="渡劫", abilities=["飞升仙界的最后一步"]),
            ],
            limitations=[
                "每个大境界需要突破瓶颈",
                "突破需要大量灵石或天材地宝",
                "修炼速度受灵根资质限制",
                "高境界修士出手会受到天道压制",
            ],
            costs=["修炼消耗灵石", "突破失败可能导致修为倒退", "使用禁术消耗寿元"],
            rare_resources=[
                "灵石（下品/中品/上品/极品）",
                "万年灵芝",
                "天火",
                "玄冰晶",
                "龙血草",
                "空间石",
            ],
            forbidden_methods=["血祭之术", "吞噬他人修为", "夺舍", "炼制活人傀儡", "逆转阴阳"],
        ),
        TerminologyElement(
            id="xianxia-term-1",
            name="灵石",
            definition="修炼资源货币，分下品/中品/上品/极品",
        ),
        TerminologyElement(
            id="xianxia-term-2",
            name="灵根",
            definition="修炼天赋，分金木水火土五行及变异灵根",
        ),
        TerminologyElement(
            id="xianxia-term-3",
            name="秘境",
            definition="上古遗迹，内有天材地宝和传承",
        ),
        TerminologyElement(
            id="xianxia-term-4",
            name="天劫",
            definition="突破大境界时天道降下的考验",
        ),
        TerminologyElement(
            id="xianxia-term-5", name="神识", definition="修士的精神感知能力"
        ),
        TerminologyElement(
            id="xianxia-term-6", name="丹田", definition="存储灵气的核心"
        ),
    ]
    assert [
        element.model_dump(exclude={"created_at", "updated_at"})
        for element in template.elements
    ] == [
        element.model_dump(exclude={"created_at", "updated_at"})
        for element in expected_elements
    ]
    assert template.style_guide == StyleGuide(
        pacing="很快",
        dialogue_density="适中",
        description_style="简练",
        tone="热血",
        sentence_length="短句多",
        pov="第三人称",
        taboo_patterns=[
            "过度描述内心独白",
            "拖节奏的环境描写",
            "战斗中的冗长对话",
            "配角抢主角戏份",
            "女主过于被动",
        ],
        preferred_patterns=[
            "每章结尾留悬念（断章）",
            "战斗节奏明快，招式清晰",
            "打脸要有铺垫→冲突→反转→余波四步",
            "修炼突破要有仪式感",
            "主角智商在线，不无脑莽",
        ],
        freeform_notes=(
            "整体风格参考《凡人修仙传》的冷静克制 + 《斗破苍穹》的热血节奏。"
            "主角成长线清晰，金手指合理有限制。"
        ),
    )
