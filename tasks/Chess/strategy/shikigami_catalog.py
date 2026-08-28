# This Python file uses the following encoding: utf-8

"""百鬼棋局阵容策略共用的式神统一目录。

数据来源于 ``shikigami/shikigami_menu.txt`` 和式神商店卡面，每条记录含义为：
``费用、当前费用下编号、罗马音、中文名、羁绊1、羁绊2、可选羁绊3``。

对外提供三种等价索引：

- ``SHIKIGAMI_BY_KEY``：按费用-编号查询；
- ``SHIKIGAMI_BY_ROMAJI``：按罗马音查询；
- ``SHIKIGAMI_BY_CHINESE_NAME``：按中文名查询。
"""

import re
from dataclasses import dataclass

from tasks.Chess.strategy.soul_catalog import resolve_soul


@dataclass(frozen=True, slots=True)
class ShikigamiEntry:
    cost: int
    number: int
    romaji: str
    chinese_name: str
    bond_1: str
    bond_2: str
    bond_3: str | None = None

    @property
    def key(self) -> str:
        return f'{self.cost}-{self.number}'

    @property
    def hand_image(self) -> str:
        """手牌头像文件名。"""
        return f'card/card_{self.romaji}.png'

    @property
    def shop_image(self) -> str:
        """商店头像文件名。"""
        return f'store/store_{self.romaji}.png'

    @property
    def bonds(self) -> tuple[str, ...]:
        """卡面从上到下显示的二至三个羁绊。"""
        return tuple(
            bond
            for bond in (self.bond_1, self.bond_2, self.bond_3)
            if bond
        )


SHIKIGAMI_ENTRIES = (
    ShikigamiEntry(1, 1, 'kaku', '觉', '大江山', '易形'),
    ShikigamiEntry(1, 2, 'kappa', '河童', '荒川', '分裂'),
    ShikigamiEntry(1, 3, 'hakurou', '白狼', '七角山', '嗜战'),
    ShikigamiEntry(1, 4, 'kaoru', '薰', '七角山', '鬼火'),
    ShikigamiEntry(1, 5, 'kanihime', '蟹姬', '海国', '分裂'),
    ShikigamiEntry(1, 6, 'yuki_douji', '雪童子', '寒霜', '锻刃'),
    ShikigamiEntry(1, 7, 'shiro_mujou', '鬼使白', '冥府', '鬼火'),
    ShikigamiEntry(1, 8, 'yamausagi', '山兔', '平安京', '嗜战'),
    ShikigamiEntry(1, 9, 'kuda_gitsune', '管狐', '狐妖', '护佑'),
    ShikigamiEntry(1, 10, 'korouka', '古笼火', '流火', '甲胄'),
    ShikigamiEntry(2, 1, 'yamawaro', '山童', '大江山', '强体'),
    ShikigamiEntry(2, 2, 'onikiri', '鬼切', '追击', '源氏兵器'),
    ShikigamiEntry(2, 3, 'zashiki_Warashi', '座敷童子', '荒川', '鬼火'),
    ShikigamiEntry(2, 4, 'youko', '妖狐', '狐妖', '嗜战'),
    ShikigamiEntry(2, 5, 'ubume', '姑获鸟', '平安京', '追击'),
    ShikigamiEntry(2, 6, 'shiro_douji', '白童子', '冥府', '甲胄'),
    ShikigamiEntry(2, 7, 'hangan', '判官', '冥府', '锻刃'),
    ShikigamiEntry(2, 8, 'komatsumaru', '小松丸', '七角山', '嗜战'),
    ShikigamiEntry(2, 9, 'hotarugusa', '萤草', '七角山', '护佑'),
    ShikigamiEntry(2, 10, 'umi_no_Chou', '灵海蝶', '海国', '甲胄'),
    ShikigamiEntry(2, 11, 'yuki_onna', '雪女', '寒霜', '强体'),
    ShikigamiEntry(2, 12, 'hououka', '凤凰火', '流火', '易形'),
    ShikigamiEntry(3, 1, 'bakedanuki', '狸猫', '大江山', '强体'),
    ShikigamiEntry(3, 2, 'shouzu', '椒图', '荒川', '护佑'),
    ShikigamiEntry(3, 3, 'kingyohime', '金鱼姬', '荒川', '易形'),
    ShikigamiEntry(3, 4, 'kachou_fuugetsu', '花鸟卷', '平安京', '追击', '强体'),
    ShikigamiEntry(3, 5, 'yasha', '夜叉', '平安京', '强体'),
    ShikigamiEntry(3, 6, 'kuro_douji', '黑童子', '冥府', '甲胄'),
    ShikigamiEntry(3, 7, 'yamakaze', '山风', '七角山', '追击'),
    ShikigamiEntry(3, 8, 'ichimoku_ren', '一目连', '七角山', '护佑'),
    ShikigamiEntry(3, 9, 'bakekujira', '化鲸', '海国', '甲胄'),
    ShikigamiEntry(3, 10, 'kujira', '久次良', '海国', '锻刃', '护佑'),
    ShikigamiEntry(3, 11, 'fuu_youkunn', '封阳君', '寒霜', '追击'),
    ShikigamiEntry(3, 12, 'keisei_chihime', '鲸汐千姬', '寒霜', '强体', '鬼火'),
    ShikigamiEntry(3, 13, 'hon_shin_sanbi_kitsune', '本真三尾狐', '狐妖', '分裂'),
    ShikigamiEntry(3, 14, 'miketsu', '御馔津', '狐妖', '甲胄'),
    ShikigamiEntry(3, 15, 'ashura', '阿修罗', '流火', '锻刃'),
    ShikigamiEntry(3, 16, 'omoikane', '思金神', '流火', '鬼火'),
    ShikigamiEntry(4, 1, 'ibaraki_douji', '茨木童子', '大江山', '嗜战'),
    ShikigamiEntry(4, 2, 'umibouzu', '海坊主', '荒川', '护佑'),
    ShikigamiEntry(4, 3, 'aoandon', '青行灯', '平安京', '鬼火'),
    ShikigamiEntry(4, 4, 'youtou_hime', '妖刀姬', '平安京', '嗜战', '源氏兵器'),
    ShikigamiEntry(4, 5, 'kuro_mujou', '鬼使黑', '冥府', '锻刃'),
    ShikigamiEntry(4, 6, 'suzuka_gozen', '铃鹿御前', '海国', '易形'),
    ShikigamiEntry(4, 7, 'zenhyou_setsunajo', '禅冰雪女', '寒霜', '易形'),
    ShikigamiEntry(4, 8, 'jinten_tamamonomae', '烬天玉藻前', '狐妖', '分裂'),
    ShikigamiEntry(4, 9, 'yume_san_byakuzou', '梦山白藏主', '狐妖', '鬼火', '甲胄'),
    ShikigamiEntry(4, 10, 'kumon_fuken_gaku', '云间不见岳', '流火', '甲胄'),
    ShikigamiEntry(4, 11, 'tenka_mei_suzu_hime', '天火命铃彦姬', '流火', '锻刃'),
    ShikigamiEntry(5, 1, 'shuten_douji', '酒吞童子', '大江山', '追击', '鬼王'),
    ShikigamiEntry(5, 2, 'arakawa_no_nushi', '荒川之主', '荒川', '分裂', '荒川之主'),
    ShikigamiEntry(5, 3, 'enma', '阎魔', '冥府', '分裂', '冥府之主'),
    ShikigamiEntry(5, 4, 'hiromori_shikaotoko', '寻森小鹿男', '七角山', '森林王者'),
    ShikigamiEntry(5, 5, 'ootakemaru', '大岳丸', '海国', '异形', '海国少主'),
    ShikigamiEntry(5, 6, 'yuki_gozen', '雪御前', '寒霜', '锻刃', '雪巫女'),
    ShikigamiEntry(5, 7, 'kuzu_no_ha', '葛叶', '九尾妖狐', '狐妖', '嗜战'),
    ShikigamiEntry(5, 8, 'taira_no_masakado', '平将门', '流火', '异形', '狩日将军'),
)


SHIKIGAMI_BY_KEY = {entry.key: entry for entry in SHIKIGAMI_ENTRIES}
SHIKIGAMI_BY_ROMAJI = {entry.romaji: entry for entry in SHIKIGAMI_ENTRIES}
SHIKIGAMI_BY_CHINESE_NAME = {
    entry.chinese_name: entry
    for entry in SHIKIGAMI_ENTRIES
}

# 寻森小鹿男通过其他玩法进入手牌和场上，不参与商店卡面签名。
NON_SHOP_SHIKIGAMI = frozenset({'hiromori_shikaotoko'})

# OCR 容易把旧字形或相近字识别成下列文本。统一在羁绊文本进入
# 商店/手牌识别流程前修正，目录本身只保存游戏中的正式名称。
BOND_OCR_ALIASES = {
    '暗战': '嗜战',
    '锻刀': '锻刃',
}


def normalize_bond_ocr_text(value) -> str:
    """清理羁绊 OCR 文本，并将常见形近字替换为正式羁绊名。"""
    text = ''.join(str(value or '').split())
    text = ''.join(re.findall(r'[\u4e00-\u9fffA-Za-z]+', text))
    for mistaken, canonical in BOND_OCR_ALIASES.items():
        text = text.replace(mistaken, canonical)
    return text


def bond_key(bonds: tuple[str, ...]) -> frozenset[str]:
    """把卡面上下顺序转换成用于识别的无序羁绊键。"""
    return frozenset(str(bond).strip() for bond in bonds if str(bond).strip())


# 以下识别索引全部由统一目录生成，不再维护第二份羁绊数据。
SHIKIGAMI_BONDS_BY_ROMAJI = {
    entry.romaji: entry.bonds
    for entry in SHIKIGAMI_ENTRIES
}

STORE_SHIKIGAMI_BY_SIGNATURE: dict[
    tuple[int, frozenset[str]],
    str,
] = {}

for entry in SHIKIGAMI_ENTRIES:
    unordered_bonds = bond_key(entry.bonds)
    if entry.romaji in NON_SHOP_SHIKIGAMI:
        continue
    signature = (entry.cost, unordered_bonds)
    previous = STORE_SHIKIGAMI_BY_SIGNATURE.get(signature)
    if previous is not None:
        raise ValueError(
            '商店费用+羁绊签名重复: '
            f'{signature} -> {previous}, {entry.romaji}'
        )
    STORE_SHIKIGAMI_BY_SIGNATURE[signature] = entry.romaji

KNOWN_BONDS = frozenset(
    bond
    for entry in SHIKIGAMI_ENTRIES
    for bond in entry.bonds
)


def _validate_catalog() -> None:
    total = len(SHIKIGAMI_ENTRIES)
    indexes = (
        ('费用-编号', SHIKIGAMI_BY_KEY),
        ('罗马音', SHIKIGAMI_BY_ROMAJI),
        ('中文名', SHIKIGAMI_BY_CHINESE_NAME),
    )
    for label, index in indexes:
        if len(index) != total:
            raise ValueError(f'式神目录存在重复{label}')
    if any(
        len(bond_key(entry.bonds)) not in (2, 3)
        for entry in SHIKIGAMI_ENTRIES
    ):
        raise ValueError('式神目录必须包含二至三个互不相同的羁绊')


def resolve_shikigami(value: str) -> ShikigamiEntry | None:
    """用费用-编号、罗马音或中文名查询同一个式神条目。"""
    value = str(value or '').strip()
    return (
        SHIKIGAMI_BY_KEY.get(value)
        or SHIKIGAMI_BY_ROMAJI.get(value)
        or SHIKIGAMI_BY_CHINESE_NAME.get(value)
    )


def build_lineup_shikigami(position_by_identity: dict) -> dict[str, dict]:
    """转换阵容配置，并兼容旧版纯站位及旧御魂元组。"""
    result = {}
    for identity, raw_config in position_by_identity.items():
        entry = resolve_shikigami(identity)
        if entry is None:
            raise KeyError(f'式神目录不存在: {identity}')
        if entry.romaji in result:
            raise ValueError(f'阵容重复配置式神: {entry.romaji}')

        deploy_weight = 1
        equip_protect = False
        if isinstance(raw_config, dict):
            position = raw_config['position']
            deploy_weight = raw_config.get('weight', 1)
            soul_values = raw_config.get('souls', ())
            equip_protect = raw_config.get('protect', False)
        elif isinstance(raw_config, (tuple, list)):
            if not raw_config:
                raise ValueError(f'阵容式神配置不能为空: {identity}')
            # 新格式：(上阵权重, 站位, (限定御魂...))
            if (
                len(raw_config) in (3, 4)
                and isinstance(raw_config[2], (tuple, list, set))
            ):
                deploy_weight, position, soul_values = raw_config[:3]
                # 兼容旧四元组；新阵容改用阵容级守护之印目标位置。
                if len(raw_config) == 4:
                    equip_protect = raw_config[3]
            else:
                # 兼容旧格式：(站位, 御魂1, 御魂2, ...)
                position, *soul_values = raw_config
        else:
            position = raw_config
            soul_values = ()

        if isinstance(soul_values, str):
            soul_values = (soul_values,)
        deploy_weight = int(deploy_weight)
        position = int(position)
        if deploy_weight < 0:
            raise ValueError(f'上阵权重不能小于 0: {identity}')
        if not 1 <= position <= 12:
            raise ValueError(f'上阵位置必须为 1-12: {identity}')

        preferred_souls = []
        for soul_value in soul_values:
            if str(soul_value).strip() == '守护之印':
                # 兼容旧元组；守护之印不是御魂，单独登记开关。
                equip_protect = True
                continue
            soul = resolve_soul(soul_value)
            if soul is None:
                raise KeyError(
                    f'御魂目录不存在: {soul_value} '
                    f'(式神={entry.chinese_name})'
                )
            soul_key = soul.romaji
            if soul_key not in preferred_souls:
                preferred_souls.append(soul_key)

        if equip_protect:
            if (
                equip_protect is not True
                and str(equip_protect).strip() != '守护之印'
            ):
                raise ValueError(
                    f'守护之印配置必须为 True/False 或“守护之印”: {identity}'
                )

        result[entry.romaji] = {
            'catalog_key': entry.key,
            'display_name': entry.chinese_name,
            'deploy_weight': deploy_weight,
            'position': position,
            'preferred_souls': tuple(preferred_souls),
            'equip_hakuzosu_protect': bool(equip_protect),
            'hand_images': (entry.hand_image,),
            'shop_images': (entry.shop_image,),
        }
    return result


_validate_catalog()
