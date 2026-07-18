# This Python file uses the following encoding: utf-8

"""百鬼棋局阵容羁绊注册表。

新增体系时：
1. 以羁绊拼音创建独立策略 Python 文件；
2. 在 ``LINEUP_REGISTRY`` 注册拼音键、中文显示名和策略对象。

OASX 下拉选项和主任务运行时选择均由本注册表生成。
"""

from enum import Enum

from tasks.Chess.lineup_strategy import HAIGUO, QIJIAOSHAN, DAJIANGSHAN, HUYAO, MINGFU


LINEUP_REGISTRY = {
    'qijiaoshan': {
        'display_name': '七角山',
        'strategy': QIJIAOSHAN,
    },
    'haiguo': {
        'display_name': '海国',
        'strategy': HAIGUO,
    },
    'dajiangshan': {
        'display_name': '大江山',
        'strategy': DAJIANGSHAN,
    },
    'huyao': {
        'display_name': '狐妖',
        'strategy': HUYAO,
    },
    'mingfu': {
        'display_name': '冥府',
        'strategy': MINGFU,
    },
}

DEFAULT_LINEUP_KEY = 'qijiaoshan'

# 枚举值使用中文，使 OASX 下拉框直接显示中文；运行时通过下面的解析
# 函数还原成稳定的拼音键。
LineupBond = Enum(
    'LineupBond',
    {
        key.upper(): entry['display_name']
        for key, entry in LINEUP_REGISTRY.items()
    },
    type=str,
)


def resolve_lineup_key(value) -> str:
    """将拼音键、中文显示名或 OASX 枚举值统一解析为拼音键。"""
    raw = getattr(value, 'value', value)
    raw = str(raw or '').strip()
    if raw in LINEUP_REGISTRY:
        return raw
    for key, entry in LINEUP_REGISTRY.items():
        if raw == entry['display_name']:
            return key
    return DEFAULT_LINEUP_KEY
