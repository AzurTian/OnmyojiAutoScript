"""Runtime constants for the Chess task."""

from tasks.Chess.strategy.lineup import (
    DEFAULT_LINEUP_KEY as REGISTERED_DEFAULT_LINEUP_KEY,
    LINEUP_REGISTRY as REGISTERED_LINEUP_REGISTRY,
)


class ChessRuntimeSettings:
    """Tuning values shared by the Chess runtime mixins."""

    HAND_AREA = (179, 540, 957, 158)
    HAND_TEMPLATE_THRESHOLD = 0.7
    HAND_DEPLOY_TEMPLATE_THRESHOLD = 0.66
    HAND_DEPLOY_CONFIRM_FRAMES = 1
    SHOP_TEMPLATE_THRESHOLD = 0.7
    SHOP_GLOW_TEMPLATE_THRESHOLD = 0.58
    HAND_DEPLOY_WAIT = 0.6
    HAND_DEPLOY_SAFETY_LIMIT = 20
    HAND_CLEANUP_SAFETY_LIMIT = 30
    HAND_CLEANUP_CLEAN_CONFIRM_FRAMES = 3
    HAND_CLEANUP_REFLOW_WAIT = 1.0
    HAND_SELL_WAIT = 0.6
    BOARD_RECALL_INTERVAL = 0.03
    BOARD_RECALL_SETTLE_WAIT = 0.6
    BOARD_RECALL_RETRY_WAIT = 0.2
    BOARD_REDEPLOY_SETTLE_WAIT = 0.6
    # 系统自动上阵优先占用棋盘右侧 11、12、9、10 号位。百鬼结束后
    # 只需要依次回收这些候选格；若 9 号位由脚本亲自部署，则保留该格。
    BOARD_RECALL_POSITIONS = (11, 12, 9, 10)
    # c_card_1/2/3.png 专用于检测棋盘式神头顶的三种勾玉颜色。
    BOARD_OCCUPANCY_TEMPLATE_THRESHOLD = 0.70
    ROUND_CONFIRM_FRAMES = 2
    RESULT_EMPTY_CONFIRM_FRAMES = 3
    GAME_ENTER_TIMEOUT = 120.0
    RESULT_RETURN_TIMEOUT = 60.0
    UNKNOWN_STATE_TIMEOUT = 25.0
    NORMAL_SCREENSHOT_INTERVAL = 0.35
    ROUND_STATE_SCREENSHOT_INTERVAL = 1.0
    HYAKKI_SCREENSHOT_INTERVAL = 3.0
    SHOP_OPEN_TIMEOUT = 8.0
    SHOP_OPEN_ATTEMPT_WAIT = 2.0
    SHOP_CLOSE_TIMEOUT = 8.0
    SHOP_CLOSE_ATTEMPT_WAIT = 2.0
    SHOP_REFRESH_WAIT = 0.8
    ECONOMY_CONFIRM_RETRIES = 2
    SHOP_BUY_RETRY_INTERVAL = 0.4
    SHOP_BUY_TIMEOUT = 30.0
    BUFF_SELECT_TIMEOUT = 12.0
    BUFF_SELECT_RETRY_INTERVAL = 0.5
    EXPERIENCE_COST = 4
    SHOP_REFRESH_COST = 2
    HAKUZOSU_PROTECT_NAME = 'hakuzosu_protect'
    HAKUZOSU_PROTECT_DISPLAY_NAME = '守护之印'
    HAKUZOSU_PROTECT_IMAGE = 'c/c_hakuzosu_protect.png'
    HAKUZOSU_NAME = 'yume_san_byakuzou'
    DEFAULT_LINEUP_KEY = REGISTERED_DEFAULT_LINEUP_KEY
    LINEUP_REGISTRY = REGISTERED_LINEUP_REGISTRY
    SOUL_EQUIP_WAIT = 0.6
    SOUL_EQUIP_SAFETY_LIMIT = 20
    DISCOVER_SOUL_SAFETY_LIMIT = 10
    DISCOVER_SOUL_UI_TIMEOUT = 8.0
    DISCOVER_SOUL_WAIT = 0.6
    SOUL_ODD_SET_Y_OFFSET = -5
    SOUL_TEMPLATE_THRESHOLD = 0.60
    SOUL_TEMPLATE_SCALES = (0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20)
    UNKNOWN_SELL_CONFIRM_FRAMES = 3
    UNKNOWN_LINEUP_PROTECT_THRESHOLD = 0.58
    UNKNOWN_LINEUP_PROTECT_SCALES = (0.90, 0.95, 1.00, 1.05, 1.10)
    SOUL_DISPLAY_NAMES = {
        'poshang': '破势',
        'shanghunniao': '伤魂鸟',
        'fuyi': '蝠翼',
        'wangqie': '网切',
        'yinmoluo': '阴摩罗',
        'yingshengchong': '应声虫',
        'kuanggu': '狂骨',
        'beichuifang': '贝吹坊',
        'beifu': '被服',
        'bangjing': '蚌精',
        'niepanzhihuo': '涅槃之火',
        'qingnvfang': '青女房',
        'zheng': '狰',
        'huoling': '火灵',
        'dizangxiang': '地藏像',
        'wangliangzhixia': '魍魉之匣',
        'diaopinghuo': '钓瓶火',
        # 图鉴中已裁好的另外三种均按功能性处理。
        'zhaocaimao': '招财猫',
        'jingji': '镜姬',
        'mumei': '木魅',
    }
    ATTACK_SOUL_NAMES = {
        'poshang',
        'shanghunniao',
        'fuyi',
        'wangqie',
        'yinmoluo',
        'yingshengchong',
        'kuanggu',
        'beichuifang',
    }
    FUNCTIONAL_SOUL_NAMES = set(SOUL_DISPLAY_NAMES) - ATTACK_SOUL_NAMES
