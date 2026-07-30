"""Chess 符咒名称解析与评分入口。"""

from difflib import SequenceMatcher
import math
import re
from collections import Counter

from tasks.Chess.badge.badge_hand_icons import (
    BADGE_FILE_INDEX,
    BADGE_QUALITY_INDEX,
)
from tasks.Chess.strategy.shikigami_catalog import SHIKIGAMI_BONDS_BY_ROMAJI


# 直接记录各符咒的实际收益；最终选择不再按类别分层。
GRIGRI_BENEFIT_BY_NAME: dict[str, float] = {
    # 金
    '金运·大吉': 56, '修行·大': 20, '卜卦·吉': 26,
    '卜卦·正吉': 45, '剥金符咒·叁': 36, '返金符咒·贰': 48,
    '经验御守·叁': 36, '折上加折': 74, '轮入之道·叁': 70,
    '鬼神助力·叁': 41, '紫气东来': 18, '多号机·贰': 24,
    '升贺之礼': 22,
    # 银
    '金运·中吉': 26, '洪福·大': 30, '修行·小': 15,
    '赏金·贰': 14, '奉纳符·贰': 4, '吞金鬼咒·贰': 18,
    '剥金符咒·贰': 25, '化厄为吉·贰': 14, '返金符咒': 40,
    '厚积薄发·贰': 8, '经验御守·贰': 28, '招福达摩·贰': 22,
    '捷径·贰': 36, '寻山问卦': 10, '寻山问卦·贰': 14,
    '百鬼夜行·贰': 33, '轮入之道·贰': 30, '齐心协力': 5,
    '鬼神助力·贰': 38, '天降之鬼': 20, '中坚之力': 8,
    '多号机': 17, '惊喜召唤': 10,
    '破势御祝': 12, '网切御祝': 10, '被服御祝': 10,
    '阴摩罗御祝': 10, '青女房御祝': 10, '蚌之御祝': 6,
    '蝠之御祝': 6, '镜之御祝': 6,
    # 铜
    '金运·小吉': 8, '吉运达摩': 10, '洪福·小': 10,
    '赏金': 8, '祸福相依': 0, '奉纳符': 2, '吞金鬼咒': 8,
    '剥金符咒': 14, '纵横急行': 4, '化厄为吉': 9,
    '厚积薄发': 10, '经验御守': 16, '招福达摩': 10,
    '切磋技艺': 14, '捷径': 24, '索签': 18, '百鬼夜行': 14,
    '轮入之道': 15, '不为所动': 8, '鬼神助力': 15,
    '招财吉鬼': 11, '招财吉鬼·贰': 16, '招财吉鬼·叁': 23,
    '蓝调': 2, '蓝调·贰': 12, '优选御魂': 6,
    '首领猎人': 6, '秘魂上宾': 5, '随机纹章': 5,
}

DEFAULT_BENEFIT_BY_QUALITY = {
    'gold': 6.0,
    'silver': 4.0,
    'copper': 3.0,
}
SILVER_SOUL_DEFAULT_BENEFIT = 3.0


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
    """返回实际收益；动态羁绊/纹章按当前阵容计算。"""
    if not name:
        return 0.0
    category = grigri_category(name)
    quality = BADGE_QUALITY_INDEX.get(name)
    if category in ('bond', 'emblem') and name != '随机纹章':
        bond = grigri_bond_name(name)
        if isinstance(lineup, dict):
            context = lineup_bond_context(lineup)
            if bond == context['primary']:
                return 22.0 if quality == 'gold' else 16.0
            if bond == '易形':
                if bond in context['secondary']:
                    return 20.0 if quality == 'gold' else 14.0
                if context['has_yixing']:
                    return 18.0 if quality == 'gold' else 10.0
                return 6.0 if quality == 'gold' else 4.0
            if bond in context['secondary']:
                return 14.0 if quality == 'gold' else 8.0
            return DEFAULT_BENEFIT_BY_QUALITY.get(quality, 3.0)
        lineup_display_name = str(lineup or '')
        if bond == lineup_display_name:
            return 22.0 if quality == 'gold' else 16.0
    if category == 'soul' and quality == 'silver':
        return float(GRIGRI_BENEFIT_BY_NAME.get(
            name,
            SILVER_SOUL_DEFAULT_BENEFIT,
        ))
    return float(GRIGRI_BENEFIT_BY_NAME.get(
        name,
        DEFAULT_BENEFIT_BY_QUALITY.get(quality, 0.0),
    ))


def grigri_keep_names(
    quality: str | None,
    lineup=None,
    keep_ratio: float = 0.4,
) -> frozenset[str]:
    """按当前品质总数排名，严格返回收益前40%的符咒名称。"""
    names = grigri_names_for_quality(quality)
    if not names:
        return frozenset()
    catalog_order = {name: index for index, name in enumerate(names)}
    ranked = sorted(
        names,
        key=lambda name: (
            -grigri_score(name, lineup),
            catalog_order[name],
        ),
    )
    keep_count = max(1, math.ceil(len(ranked) * keep_ratio))
    return frozenset(ranked[:keep_count])


def grigri_selection_key(
    name: str | None,
    lineup=None,
) -> tuple[float]:
    """只按实际收益选择；类别不再提供额外优先级。"""
    return (grigri_score(name, lineup),)


def grigri_file(name: str) -> str:
    return BADGE_FILE_INDEX[name]
