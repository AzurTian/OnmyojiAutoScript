# This Python file uses the following encoding: utf-8

"""百鬼棋局式神统一目录。

数据来源于 ``shikigami/shikigami_menu.txt``，每条文本含义为：
``费用-编号:罗马音:中文名``。

对外提供三种等价索引：

- ``SHIKIGAMI_BY_KEY``：按费用-编号查询；
- ``SHIKIGAMI_BY_ROMAJI``：按罗马音查询；
- ``SHIKIGAMI_BY_CHINESE_NAME``：按中文名查询。
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ShikigamiEntry:
    cost: int
    number: int
    romaji: str
    chinese_name: str

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


SHIKIGAMI_ENTRIES = (
    ShikigamiEntry(1, 1, 'kaku', '觉'),
    ShikigamiEntry(1, 2, 'kappa', '河童'),
    ShikigamiEntry(1, 3, 'hakurou', '白狼'),
    ShikigamiEntry(1, 4, 'kaoru', '薰'),
    ShikigamiEntry(1, 5, 'kanihime', '蟹姬'),
    ShikigamiEntry(1, 6, 'yuki_douji', '雪童子'),
    ShikigamiEntry(1, 7, 'shiro_mujou', '鬼使白'),
    ShikigamiEntry(1, 8, 'yamausagi', '山兔'),
    ShikigamiEntry(1, 9, 'kuda_gitsune', '管狐'),
    ShikigamiEntry(1, 10, 'korouka', '古笼火'),
    ShikigamiEntry(2, 1, 'yamawaro', '山童'),
    ShikigamiEntry(2, 2, 'onikiri', '鬼切'),
    ShikigamiEntry(2, 3, 'zashiki_Warashi', '座敷童子'),
    ShikigamiEntry(2, 4, 'youko', '妖狐'),
    ShikigamiEntry(2, 5, 'ubume', '姑获鸟'),
    ShikigamiEntry(2, 6, 'shiro_douji', '白童子'),
    ShikigamiEntry(2, 7, 'hangan', '判官'),
    ShikigamiEntry(2, 8, 'komatsumaru', '小松丸'),
    ShikigamiEntry(2, 9, 'hotarugusa', '萤草'),
    ShikigamiEntry(2, 10, 'umi_no_Chou', '灵海蝶'),
    ShikigamiEntry(2, 11, 'yuki_onna', '雪女'),
    ShikigamiEntry(2, 12, 'hououka', '凤凰火'),
    ShikigamiEntry(3, 1, 'bakedanuki', '狸猫'),
    ShikigamiEntry(3, 2, 'shouzu', '椒图'),
    ShikigamiEntry(3, 3, 'kingyohime', '金鱼姬'),
    ShikigamiEntry(3, 4, 'kachou_fuugetsu', '花鸟卷'),
    ShikigamiEntry(3, 5, 'yasha', '夜叉'),
    ShikigamiEntry(3, 6, 'kuro_douji', '黑童子'),
    ShikigamiEntry(3, 7, 'yamakaze', '山风'),
    ShikigamiEntry(3, 8, 'ichimoku_ren', '一目连'),
    ShikigamiEntry(3, 9, 'bakekujira', '化鲸'),
    ShikigamiEntry(3, 10, 'kujira', '久次良'),
    ShikigamiEntry(3, 11, 'fuu_youkunn', '封阳君'),
    ShikigamiEntry(3, 12, 'keisei_chihime', '鲸汐千姬'),
    ShikigamiEntry(3, 13, 'hon_shin_sanbi_kitsune', '本真三尾狐'),
    ShikigamiEntry(3, 14, 'miketsu', '御馔津'),
    ShikigamiEntry(3, 15, 'ashura', '阿修罗'),
    ShikigamiEntry(3, 16, 'omoikane', '思金神'),
    ShikigamiEntry(4, 1, 'ibaraki_douji', '茨木童子'),
    ShikigamiEntry(4, 2, 'umibouzu', '海坊主'),
    ShikigamiEntry(4, 3, 'aoandon', '青行灯'),
    ShikigamiEntry(4, 4, 'youtou_hime', '妖刀姬'),
    ShikigamiEntry(4, 5, 'kuro_mujou', '鬼使黑'),
    ShikigamiEntry(4, 6, 'suzuka_gozen', '铃鹿御前'),
    ShikigamiEntry(4, 7, 'zenhyou_setsunajo', '禅冰雪女'),
    ShikigamiEntry(4, 8, 'jinten_tamamonomae', '烬天玉藻前'),
    ShikigamiEntry(4, 9, 'yume_san_byakuzou', '梦山白藏主'),
    ShikigamiEntry(4, 10, 'kumon_fuken_gaku', '云间不见岳'),
    ShikigamiEntry(4, 11, 'tenka_mei_suzu_hime', '天火命铃彦姬'),
    ShikigamiEntry(5, 1, 'shuten_douji', '酒吞童子'),
    ShikigamiEntry(5, 2, 'arakawa_no_nushi', '荒川之主'),
    ShikigamiEntry(5, 3, 'enma', '阎魔'),
    ShikigamiEntry(5, 4, 'hiromori_shikaotoko', '寻森小鹿男'),
    ShikigamiEntry(5, 5, 'ootakemaru', '大岳丸'),
    ShikigamiEntry(5, 6, 'yuki_gozen', '雪御前'),
    ShikigamiEntry(5, 7, 'kuzu_no_ha', '葛叶'),
    ShikigamiEntry(5, 8, 'taira_no_masakado', '平将门'),
)


SHIKIGAMI_BY_KEY = {entry.key: entry for entry in SHIKIGAMI_ENTRIES}
SHIKIGAMI_BY_ROMAJI = {entry.romaji: entry for entry in SHIKIGAMI_ENTRIES}
SHIKIGAMI_BY_CHINESE_NAME = {
    entry.chinese_name: entry
    for entry in SHIKIGAMI_ENTRIES
}


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


def resolve_shikigami(value: str) -> ShikigamiEntry | None:
    """用费用-编号、罗马音或中文名查询同一个式神条目。"""
    value = str(value or '').strip()
    return (
        SHIKIGAMI_BY_KEY.get(value)
        or SHIKIGAMI_BY_ROMAJI.get(value)
        or SHIKIGAMI_BY_CHINESE_NAME.get(value)
    )


def build_lineup_shikigami(position_by_identity: dict[str, int]) -> dict[str, dict]:
    """把阵容的编号或中文名配置转换成以罗马音为唯一键的运行配置。"""
    result = {}
    for identity, position in position_by_identity.items():
        entry = resolve_shikigami(identity)
        if entry is None:
            raise KeyError(f'式神目录不存在: {identity}')
        if entry.romaji in result:
            raise ValueError(f'阵容重复配置式神: {entry.romaji}')
        result[entry.romaji] = {
            'catalog_key': entry.key,
            'display_name': entry.chinese_name,
            'position': int(position),
            'hand_images': (entry.hand_image,),
            'shop_images': (entry.shop_image,),
        }
    return result


_validate_catalog()
