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
        '御馔津': 1,
        '薰': 2,
        '一目连': 3,
        '白狼': 4,
        '萤草': 5,
        '小松丸': 6,
        '梦山白藏主': 7,
        '山风': 8,
        '寻森小鹿男': 10,
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


DAJIANGSHAN_CONFIG = {
    'key': 'dajiangshan',
    'display_name': '大江山',
    'shikigami_positions': {
        '雪女': 1,
        '觉': 2,
        '鲸汐千姬': 3,
        '鬼切': 4,
        '狸猫': 5,
        '茨木童子': 6,
        '山童': 7,
        '薰': 8,
        '酒吞童子': 10,
    },
}


DAJIANGSHAN = build_lineup_strategy(DAJIANGSHAN_CONFIG)


HUYAO_CONFIG = {
    'key': 'huyao',
    'display_name': '狐妖',
    'shikigami_positions': {
        '青行灯': 1,
        '烬天玉藻前': 2,
        '梦山白藏主': 3,
        '妖狐': 4,
        '本真三尾狐': 5,
        '葛叶': 6,
        '御馔津': 7,
        '妖刀姬': 8,
    },
    'hakuzosu_protect_position': 1,
}


HUYAO = build_lineup_strategy(HUYAO_CONFIG)


MINGFU_CONFIG = {
    'key': 'mingfu',
    'display_name': '冥府',
    'shikigami_positions': {
        '青行灯': 1,
        '阎魔': 2,
        '夜叉': 3,
        '鬼使黑': 4,
        '黑童子': 5,
        '判官': 6,
        '花鸟卷': 7,
        '鬼使白': 8,
        '白童子': 9,
    },
    'hakuzosu_protect_position': 1,
}


MINGFU = build_lineup_strategy(MINGFU_CONFIG)
