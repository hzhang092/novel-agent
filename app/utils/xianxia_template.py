"""Xianxia (修仙) genre template — pre-fills world setting and style guide
with cultivation realms, common faction types, tribulation mechanics, and
reviewer pacing rules for the web-novel format."""

from __future__ import annotations

from app.storage.models import PowerSystem, StyleGuide, WorldSetting


def get_xianxia_template() -> tuple[WorldSetting, StyleGuide]:
    """Return a pre-filled WorldSetting and StyleGuide for Xianxia novels.

    The world setting includes cultivation realms from 炼气 through 渡劫,
    common factions (宗门, 散修联盟, 魔道, 商会, 皇朝), and standard rules.
    The style guide is tuned for web-novel pacing with fast rhythm, hook-heavy
    chapter endings, and face-slapping (打脸) beat patterns.
    """
    world = WorldSetting(
        geography="东荒大陆，广袤无垠。东部临海，西部荒漠，南部群山，北部冰原。"
                  "中央为中原九州，修士云集之地。",
        power_system=PowerSystem(
            realms=[
                "炼气", "筑基", "金丹", "元婴",
                "化神", "炼虚", "合体", "大乘", "渡劫",
            ],
            abilities={
                "炼气": "灵气感知，基础法术",
                "筑基": "御器飞行，法术增强",
                "金丹": "金丹领域，本命法宝",
                "元婴": "元婴出窍，神识覆盖",
                "化神": "化神分魂，法则初悟",
                "炼虚": "虚空穿梭，炼化空间",
                "合体": "身与道合，神通大成",
                "大乘": "渡劫准备，天地共鸣",
                "渡劫": "飞升仙界的最后一步",
            },
            limitations=[
                "每个大境界需要突破瓶颈",
                "突破需要大量灵石或天材地宝",
                "修炼速度受灵根资质限制",
                "高境界修士出手会受到天道压制",
            ],
            costs=[
                "修炼消耗灵石",
                "突破失败可能导致修为倒退",
                "使用禁术消耗寿元",
            ],
            rare_resources=[
                "灵石（下品/中品/上品/极品）",
                "万年灵芝",
                "天火",
                "玄冰晶",
                "龙血草",
                "空间石",
            ],
            forbidden_methods=[
                "血祭之术",
                "吞噬他人修为",
                "夺舍",
                "炼制活人傀儡",
                "逆转阴阳",
            ],
        ),
        factions=[
            {
                "name": "青云宗",
                "description": "正道第一宗门，以剑修闻名，坐落于青云山脉。",
                "goals": "维护大陆秩序，对抗魔道势力",
            },
            {
                "name": "魔渊殿",
                "description": "魔道最强势力，隐藏于地底魔渊，行事诡秘。",
                "goals": "收集上古魔器，打开魔界通道",
            },
            {
                "name": "天机阁",
                "description": "中立的商业情报组织，遍布大陆各城。",
                "goals": "收集天下情报，垄断修炼资源交易",
            },
            {
                "name": "散修联盟",
                "description": "无门无派的散修聚集组织，以自由为信条。",
                "goals": "为散修争取修炼资源，互帮互助",
            },
            {
                "name": "大楚皇朝",
                "description": "凡间最强世俗政权，皇室拥有祖传修炼功法。",
                "goals": "统一大陆，皇权凌驾于宗门之上",
            },
        ],
        history=(
            "万年前神魔大战，仙界通道崩毁，大陆灵气溃散。"
            "千年前灵气复苏，修仙文明重新崛起。"
            "五百年前正魔大战，双方元气大伤，进入冷战期。"
            "如今大陆表面和平，暗流涌动。"
        ),
        rules=[
            "修士不可对凡人出手，违者天谴",
            "秘境百年开启一次，进入者限骨龄三十以下",
            "元婴以上修士不得在凡人城市全力出手",
            "宗门大比每十年一次，决定资源分配",
        ],
        taboos=[
            "修炼魔功",
            "背叛师门",
            "残害同门",
            "勾结魔道",
        ],
        technology_level="修仙文明，凡人处于封建时代",
        social_structure="宗门制，强者为尊。宗门 > 皇朝 > 世家 > 凡人。",
        terminology={
            "灵石": "修炼资源货币，分下品/中品/上品/极品",
            "灵根": "修炼天赋，分金木水火土五行及变异灵根",
            "秘境": "上古遗迹，内有天材地宝和传承",
            "天劫": "突破大境界时天道降下的考验",
            "神识": "修士的精神感知能力",
            "丹田": "存储灵气的核心",
        },
    )

    style = StyleGuide(
        pacing="快节奏",
        dialogue_density="对白适中",
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
        reference_passages=[],
        freeform_notes=(
            "整体风格参考《凡人修仙传》的冷静克制 + "
            "《斗破苍穹》的热血节奏。"
            "主角成长线清晰，金手指合理有限制。"
        ),
    )

    return world, style
