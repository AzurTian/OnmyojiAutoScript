# This Python file uses the following encoding: utf-8

"""百鬼棋局阵容羁绊配置。

阵容配置只描述阵容自身：

- ``shikigami_positions``：式神 ->
  ``(上阵权重, 站位, (限定御魂...))``。权重越低越
  优先上阵；同权重仍按手牌从左到右处理。
- ``hakuzosu_protect_position``：守护之印应装备到的式神站位；不使用
  守护之印时为 ``None``。
- ``arakawa_goldfish_position``：荒川羁绊召唤金鱼后应移动到的位置。
  不使用荒川金鱼时为 ``None``；启用后从棋盘右侧 12、11、10、9
  号位依次寻找生成格。

经济策略属于通用运营流程，写在主任务中，不放入阵容配置。
"""

from tasks.Chess.strategy.shikigami_catalog import build_lineup_shikigami


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
        protect_position = int(protect_position)
        if not 1 <= protect_position <= 12:
            raise ValueError(
                'hakuzosu_protect_position must be between 1 and 12'
            )
    strategy['hakuzosu_protect_position'] = protect_position
    goldfish_position = config.get('arakawa_goldfish_position')
    if goldfish_position is not None:
        goldfish_position = int(goldfish_position)
        if not 1 <= goldfish_position <= 12:
            raise ValueError(
                'arakawa_goldfish_position must be between 1 and 12'
            )
    strategy['arakawa_goldfish_position'] = goldfish_position
    return strategy


QIJIAOSHAN_CONFIG = {
    'key': 'qijiaoshan',
    'display_name': '七角山',
    'hakuzosu_protect_position': 2,
    'shikigami_positions': {
        '古笼火': (2, 1, ()),
        '薰': (1, 2, ('魍魉之匣', '钓瓶火')),
        '一目连': (2, 3, ()),
        '白狼': (1, 4, ()),
        '萤草': (1, 5, ()),
        '小松丸': (1, 6, ()),
        '梦山白藏主': (2, 7, ()),
        '山风': (2, 8, ()),
    },
}


QIJIAOSHAN = build_lineup_strategy(QIJIAOSHAN_CONFIG)


HAIGUO_CONFIG = {
    'key': 'haiguo',
    'display_name': '海国',
    'hakuzosu_protect_position': None,
    'shikigami_positions': {
        '薰': (1, 1, ()),
        '鬼使白': (1, 2, ()),
        '黑童子': (1, 3, ('涅槃之火','蚌精','镜姬')),
        '大岳丸': (1, 4, ()),
        '化鲸': (1, 5, ()),
        '蟹姬': (1, 6, ()),
        '灵海蝶': (1, 7, ()),
        '久次良': (1, 8, ()),
        '铃鹿御前': (1, 10, ()),
    },
}


HAIGUO = build_lineup_strategy(HAIGUO_CONFIG)


DAJIANGSHAN_CONFIG = {
    'key': 'dajiangshan',
    'display_name': '大江山',
    'hakuzosu_protect_position': None,
    'shikigami_positions': {
        '雪女': (1, 1, ()),
        '觉': (1, 2, ()),
        '鲸汐千姬': (1, 3, ()),
        '鬼切': (1, 4, ()),
        '狸猫': (1, 5, ()),
        '茨木童子': (1, 6, ()),
        '山童': (1, 7, ()),
        '薰': (1, 8, ()),
        '酒吞童子': (1, 10, ()),
    },
}


DAJIANGSHAN = build_lineup_strategy(DAJIANGSHAN_CONFIG)


HUYAO_CONFIG = {
    'key': 'huyao',
    'display_name': '狐妖',
    'hakuzosu_protect_position': 1,
    'shikigami_positions': {
        '青行灯': (1, 1, ()),
        '烬天玉藻前': (1, 2, ()),
        '梦山白藏主': (1, 3, ()),
        '妖狐': (1, 4, ()),
        '本真三尾狐': (1, 5, ()),
        '葛叶': (1, 6, ()),
        '御馔津': (1, 7, ()),
        '妖刀姬': (1, 8, ()),
    },
}


HUYAO = build_lineup_strategy(HUYAO_CONFIG)


MINGFU_CONFIG = {
    'key': 'mingfu',
    'display_name': '冥府',
    'hakuzosu_protect_position': 1,
    'shikigami_positions': {
        '青行灯': (1, 1, ()),
        '阎魔': (1, 2, ()),
        '夜叉': (1, 3, ()),
        '鬼使黑': (1, 4, ()),
        '黑童子': (1, 5, ()),
        '判官': (1, 6, ()),
        '花鸟卷': (1, 7, ()),
        '鬼使白': (1, 8, ()),
        '白童子': (1, 9, ()),
    },
}


MINGFU = build_lineup_strategy(MINGFU_CONFIG)


LIUHUO_CONFIG = {
    'key': 'liuhuo',
    'display_name': '流火',
    'hakuzosu_protect_position': 1,
    'shikigami_positions': {
        '思金神': (1, 1, ()),
        '凤凰火': (1, 2, ()),
        '古笼火': (1, 3, ()),
        '阿修罗': (1, 4, ()),
        '云间不见岳': (1, 5, ()),
        '天火命铃彦姬': (1, 7, ()),
        '梦山白藏主': (1, 7, ()),
        '烬天玉藻前': (1, 8, ()),
        '金鱼姬': (1, 9, ()),
    },
}


LIUHUO = build_lineup_strategy(LIUHUO_CONFIG)


ARAKAWA_CONFIG = {
    'key': 'arakawa',
    'display_name': '荒川',
    'hakuzosu_protect_position': None,
    'arakawa_goldfish_position': 12,
    'shikigami_positions': {
        '海坊主': (1, 1, ()),
        '铃鹿御前': (
            2,
            2,
            ('招财猫', '网切', '破势', '狂骨', '贝吹坊'),
        ),
        '椒图': (1, 3, ()),
        '座敷童子': (1, 4, ('钓瓶火','魍魉之匣')),
        '久次良': (2, 5, ()),
        '荒川之主': (1, 6, ()),
        '管狐': (2, 7, ()),
        '金鱼姬': (1, 8, ()),
        '河童': (1, 10, ()),
    },
}


ARAKAWA = build_lineup_strategy(ARAKAWA_CONFIG)
