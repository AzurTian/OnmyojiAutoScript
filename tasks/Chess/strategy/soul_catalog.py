# This Python file uses the following encoding: utf-8

"""百鬼棋局御魂中文名与拼音的唯一对照目录。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SoulEntry:
    romaji: str
    chinese_name: str
    category: str

    @property
    def image_name(self) -> str:
        return f'sou_{self.romaji}.png'


SOUL_ENTRIES = (
    SoulEntry('poshi', '破势', 'attack'),
    SoulEntry('shanghunniao', '伤魂鸟', 'attack'),
    SoulEntry('fuyi', '蝠翼', 'attack'),
    SoulEntry('wangqie', '网切', 'attack'),
    SoulEntry('yinmoluo', '阴摩罗', 'attack'),
    SoulEntry('yingshengchong', '应声虫', 'attack'),
    SoulEntry('kuanggu', '狂骨', 'attack'),
    SoulEntry('beichuifang', '贝吹坊', 'attack'),
    SoulEntry('beifu', '被服', 'functional'),
    SoulEntry('bangjing', '蚌精', 'functional'),
    SoulEntry('niepanzhihuo', '涅槃之火', 'functional'),
    SoulEntry('qingnvfang', '青女房', 'functional'),
    SoulEntry('zheng', '狰', 'functional'),
    SoulEntry('huoling', '火灵', 'functional'),
    SoulEntry('dizangxiang', '地藏像', 'functional'),
    SoulEntry('wangliangzhixia', '魍魉之匣', 'functional'),
    SoulEntry('diaopinghuo', '钓瓶火', 'functional'),
    SoulEntry('zhaocaimao', '招财猫', 'functional'),
    SoulEntry('jingji', '镜姬', 'functional'),
    SoulEntry('mumei', '木魅', 'functional'),
)

SOUL_BY_ROMAJI = {entry.romaji: entry for entry in SOUL_ENTRIES}
SOUL_BY_CHINESE_NAME = {
    entry.chinese_name: entry
    for entry in SOUL_ENTRIES
}
def resolve_soul(value) -> SoulEntry | None:
    """仅按拼音或完整中文名解析御魂。"""
    if isinstance(value, SoulEntry):
        return value
    text = str(value or '').strip()
    if not text:
        return None
    return SOUL_BY_ROMAJI.get(text) or SOUL_BY_CHINESE_NAME.get(text)


def _validate_catalog() -> None:
    total = len(SOUL_ENTRIES)
    if total != 20:
        raise ValueError(f'御魂目录数量异常: {total}, expected=20')
    for label, index in (
        ('拼音', SOUL_BY_ROMAJI),
        ('中文名', SOUL_BY_CHINESE_NAME),
    ):
        if len(index) != total:
            raise ValueError(f'御魂目录存在重复{label}')
    if any(
        entry.category not in {'attack', 'functional'}
        for entry in SOUL_ENTRIES
    ):
        raise ValueError('御魂类型必须为 attack 或 functional')


_validate_catalog()
