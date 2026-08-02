"""Chess 符咒名称解析与评分入口。"""

from difflib import SequenceMatcher
import re
from collections import Counter

from tasks.Chess.badge.badge_hand_icons import (
    BADGE_FILE_INDEX,
    BADGE_QUALITY_INDEX,
)
from tasks.Chess.strategy.shikigami_catalog import SHIKIGAMI_BONDS_BY_ROMAJI


# 只有经济、经验需要维护静态分数；未登记项按 0 分处理。
ECONOMY_GRIGRI_SCORE_BY_NAME: dict[str, float] = {
    '轮入之道': 10,
    '轮入之道·贰': 10,
    '轮入之道·叁': 10,
    '折上加折': 10,
    '卜卦·吉': 9,
    '卜卦·正吉': 9,
    '金运·小吉': 9,
    '金运·中吉': 9,
    '金运·大吉': 9,
    '剥金符咒': 8,
    '剥金符咒·贰': 8,
    '剥金符咒·叁': 8,
    '鬼神助力': 8,
    '鬼神助力·贰': 8,
    '鬼神助力·叁': 8,
    '赏金': 8,
    '赏金·贰': 8,
    '化厄为吉': 7,
    '化厄为吉·贰': 7,
    '招财吉鬼': 7,
    '招财吉鬼·贰': 7,
    '招财吉鬼·叁': 7,
    '吉运达摩': 7,
    '厚积薄发': 6,
    '厚积薄发·贰': 6,
    '百鬼夜行': 6,
    '百鬼夜行·贰': 6,
    '洪福·大': 6,
    '洪福·小': 6,
    '修行·大': 5,
    '修行·小': 5,
    '吞金鬼咒': 5,
    '吞金鬼咒·贰': 5,
    '不为所动': 5,
    '索签': 4,
    '奉纳符': 0,
    '奉纳符·贰': 0,
}
EXPERIENCE_GRIGRI_SCORE_BY_NAME: dict[str, float] = {
    '捷径': 10,
    '捷径·贰': 10,
    '返金符咒': 10,
    '返金符咒·贰': 10,
    '寻山问卦': 9,
    '寻山问卦·贰': 9,
    '切磋技艺': 9,
    '经验御守': 8,
    '经验御守·贰': 8,
    '经验御守·叁': 8,
    '招福达摩': 7,
    '招福达摩·贰': 7,
}
DEFAULT_GRIGRI_SCORE = 0.0


def _names(value: str) -> frozenset[str]:
    return frozenset(value.split())


GRIGRI_NAMES_BY_CATEGORY: dict[str, frozenset[str]] = {
    'bond': _names("""
流火朱印·贰 流火朱印 狐妖朱印·贰 狐妖朱印 寒霜朱印·贰 寒霜朱印
鬼火朱印·贰 鬼火朱印 甲胄朱印·贰 甲胄朱印 护佑朱印·贰 护佑朱印
强体朱印·贰 强体朱印 锻刃朱印·贰 锻刃朱印 嗜战朱印·贰 嗜战朱印
分裂朱印·贰 分裂朱印 易形朱印·贰 易形朱印 追击朱印·贰 追击朱印
海国朱印·贰 海国朱印 平安京朱印·贰 平安京朱印 毒灾朱印·贰 毒灾朱印
七角山朱印·贰 七角山朱印 荒川朱印·贰 荒川朱印 冥府朱印·贰 冥府朱印
大江山朱印·贰 大江山朱印 强运朱印·贰 强运朱印 黑夜山朱印·贰 黑夜山朱印
"""),
    'emblem': _names("""
流火纹章·贰 流火纹章 狐妖纹章·贰 狐妖纹章 随机纹章 鬼火纹章·贰
鬼火纹章 甲胄纹章·贰 甲胄纹章 护佑纹章·贰 护佑纹章 强体纹章·贰
强体纹章 锻刃纹章·贰 锻刃纹章 嗜战纹章·贰 嗜战纹章 分裂纹章·贰
分裂纹章 易形纹章·贰 易形纹章 追击纹章·贰 追击纹章 寒霜纹章·贰
寒霜纹章 海国纹章·贰 海国纹章 平安京纹章·贰 平安京纹章
毒灾纹章·贰 毒灾纹章 七角山纹章·贰 七角山纹章 荒川纹章·贰 荒川纹章
冥府纹章·贰 冥府纹章 大江山纹章·贰 大江山纹章
"""),
    'economy': _names("""
不为所动 轮入之道·叁 轮入之道·贰 轮入之道 百鬼夜行·贰 百鬼夜行
索签 折上加折 厚积薄发·贰 厚积薄发 化厄为吉·贰 化厄为吉
剥金符咒·叁 剥金符咒·贰 剥金符咒 吞金鬼咒·贰 吞金鬼咒 赏金·贰 赏金
卜卦·正吉 卜卦·吉 修行·大 修行·小 洪福·大 洪福·小 吉运达摩
金运·大吉 金运·中吉 金运·小吉
鬼神助力·叁 鬼神助力·贰 鬼神助力
招财吉鬼·叁 招财吉鬼·贰 招财吉鬼
奉纳符·贰 奉纳符
"""),
    'experience': _names("""
寻山问卦·贰 寻山问卦 捷径·贰 捷径 切磋技艺 招福达摩·贰 招福达摩
经验御守·叁 经验御守·贰 经验御守 返金符咒·贰 返金符咒
"""),
    'soul': _names("""
秘魂上宾 优选御魂·贰 优选御魂 应声虫御祝 青女房御祝 蚌之御祝 木魅御祝
涅槃御祝 被服御祝 镜之御祝 招财猫御祝 阴摩罗御祝 网切御祝 蝠之御祝
狰之御祝 伤魂鸟御祝 破势御祝
"""),
    'functional': _names("""
首领猎人 御火符咒 不屈灵符·叁 不屈灵符·贰 不屈灵符 气愈灵符·叁
气愈灵符·贰 气愈灵符 强躯灵符·叁 强躯灵符·贰 强躯灵符 大妖灵符·叁
大妖灵符·贰 大妖灵符 小鬼灵符·叁 小鬼灵符·贰 小鬼灵符 神赐符咒·叁
神赐符咒·贰 神赐符咒 勇气符咒·叁 勇气符咒·贰 勇气符咒 狂野符咒·叁
狂野符咒·贰 狂野符咒 鲜血之拥·叁 鲜血之拥·贰 鲜血之拥 破军之势·叁
破军之势·贰 破军之势 蓝调·贰 蓝调 紫气东来 纵横急行 祸福相依
"""),
    'shikigami': _names("""
惊喜召唤 升贺之礼 多号机·贰 多号机 中坚之力 天降之鬼 齐心协力
"""),
}

GRIGRI_CATEGORY_BY_NAME = {
    name: category
    for category, names in GRIGRI_NAMES_BY_CATEGORY.items()
    for name in names
}

# 数值越大，跨类别选择时越优先。
GRIGRI_CATEGORY_TIER = {
    'economy': 3,
    'experience': 3,
    'bond': 2,
    'emblem': 2,
    'soul': 1,
    'functional': 1,
    'shikigami': 1,
    'unknown': 0,
}


def normalize_grigri_name(value) -> str:
    """统一 OCR 文本；兼容缺失/误识别的名称中点。"""
    if value is None:
        return ''
    return re.sub(r'[\s·•・．.。:：,，_\-]+', '', str(value).strip())


def grigri_names_for_quality(quality: str | None) -> tuple[str, ...]:
    return tuple(
        name for name, item_quality in BADGE_QUALITY_INDEX.items()
        if quality is None or item_quality == quality
    )


def resolve_grigri_name(
    ocr_text,
    quality: str | None = None,
) -> tuple[str | None, float]:
    """将 OCR 名称映射回图鉴中文名，返回名称和文本相似度。"""
    current = normalize_grigri_name(ocr_text)
    if not current:
        return None, 0.0

    best_name = None
    best_score = 0.0
    for name in grigri_names_for_quality(quality):
        score = SequenceMatcher(
            None,
            normalize_grigri_name(name),
            current,
        ).ratio()
        if score > best_score:
            best_name, best_score = name, score
    threshold = 0.72 if len(current) > 2 else 0.85
    return (best_name, best_score) if best_score >= threshold else (None, best_score)


def grigri_category(name: str | None) -> str:
    return GRIGRI_CATEGORY_BY_NAME.get(name, 'unknown')


def grigri_bond_name(name: str | None) -> str | None:
    """从“荒川朱印·贰/荒川纹章”中提取羁绊名。"""
    if not name:
        return None
    matched = re.fullmatch(r'(.+?)(?:朱印|纹章)(?:·[贰叁])?', name)
    return matched.group(1) if matched is not None else None


def lineup_bond_context(strategy: dict) -> dict:
    counts = Counter(
        bond
        for shikigami_name in strategy.get('shikigami', {})
        for bond in SHIKIGAMI_BONDS_BY_ROMAJI.get(shikigami_name, ())
    )
    primary = strategy.get('display_name', '')
    primary_count = counts.get(primary, 0)
    secondary = frozenset(
        bond
        for bond, count in counts.items()
        if 2 < count < primary_count
    )
    return {
        'counts': dict(counts),
        'primary': primary,
        'primary_count': primary_count,
        'secondary': secondary,
        'has_yixing': counts.get('易形', 0) > 0,
    }


def grigri_score(name: str | None, lineup=None) -> float:
    category = grigri_category(name)
    if category == 'economy':
        scores = ECONOMY_GRIGRI_SCORE_BY_NAME
    elif category == 'experience':
        scores = EXPERIENCE_GRIGRI_SCORE_BY_NAME
    elif category in ('bond', 'emblem'):
        bond = grigri_bond_name(name)
        if isinstance(lineup, dict):
            context = lineup_bond_context(lineup)
            if bond == context['primary']:
                return 10.0
            if bond in context['secondary']:
                return 9.0
            if bond == '易形' and context['has_yixing']:
                return 8.0
            return 0.0
        lineup_display_name = str(lineup or '')
        return 10.0 if bond == lineup_display_name else 0.0
    else:
        return DEFAULT_GRIGRI_SCORE
    return float(scores.get(name, DEFAULT_GRIGRI_SCORE))


def grigri_selection_key(
    name: str | None,
    lineup=None,
) -> tuple[int, float, int, int]:
    """层级、分数、同分类型优先：经验优先经济，纹章优先朱印。"""
    category = grigri_category(name)
    return (
        GRIGRI_CATEGORY_TIER[category],
        grigri_score(name, lineup),
        int(category == 'experience'),
        int(category == 'emblem'),
    )


def grigri_file(name: str) -> str:
    return BADGE_FILE_INDEX[name]
