# This Python file uses the following encoding: utf-8

"""百鬼棋局阵容羁绊配置。

阵容配置只描述阵容自身：

- ``shikigami_positions``：式神 -> 上阵位置。式神可填写费用-编号、
  罗马音或中文名，运行时统一解析为罗马音。
- ``hakuzosu_protect_position``：当阵容包含梦山白藏主时，守护之印
  应装备到的位置；不填写时默认装备到 1 号位。

经济策略属于通用运营流程，写在主任务中，不放入阵容配置。
"""

from tasks.Chess.shikigami_catalog import build_lineup_shikigami


def build_lineup_strategy(config: dict) -> dict:
    """把轻量阵容配置转换成主程序使用的标准结构。"""
    strategy = {
        'key': config['key'],
        'display_name': config['display_name'],
        'shikigami': build_lineup_shikigami(
            config.get('shikigami_positions', {})
        ),
    }
    protect_position = config.get('hakuzosu_protect_position')
    if protect_position is not None:
        strategy['hakuzosu_protect_position'] = int(protect_position)
    return strategy


QIJIAOSHAN_CONFIG = {
    'key': 'qijiaoshan',
    'display_name': '七角山',
    'shikigami_positions': {
        '1-4': 1,   # 薰
        '1-3': 2,   # 白狼
        '3-14': 3,  # 御馔津
        '2-8': 4,   # 小松丸
        '3-8': 5,   # 一目连
        '5-4': 6,   # 寻森小鹿男
        '2-9': 7,   # 萤草
        '3-7': 8,   # 山风
        '4-9': 9,   # 梦山白藏主
    },
    'hakuzosu_protect_position': 1,
}


QIJIAOSHAN = build_lineup_strategy(QIJIAOSHAN_CONFIG)


HAIGUO_CONFIG = {
    'key': 'haiguo',
    'display_name': '海国',
    'shikigami_positions': {
        '黑童子': 1,
        '蟹姬': 2,
        '化鲸': 3,
        '铃鹿御前': 4,
        '灵海蝶': 5,
        '久次良': 6,
        '白童子': 7,
        '大岳丸': 8,
    },
}


HAIGUO = build_lineup_strategy(HAIGUO_CONFIG)
