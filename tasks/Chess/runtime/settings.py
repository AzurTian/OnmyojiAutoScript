"""Runtime constants for the Chess task."""

from tasks.Chess.strategy.lineup import (
    DEFAULT_LINEUP_KEY as REGISTERED_DEFAULT_LINEUP_KEY,
    LINEUP_REGISTRY as REGISTERED_LINEUP_REGISTRY,
)
from tasks.Chess.strategy.soul_catalog import SOUL_ENTRIES


class ChessRuntimeSettings:
    """Tuning values shared by the Chess runtime mixins."""

    HAND_AREA = (179, 540, 957, 158)
    # 完整手牌模板在实战截图中的真匹配约 0.997，已测非目标最高约
    # 0.438；取 0.75 为光效、轻微位移和压缩失真保留余量。
    HAND_TEMPLATE_THRESHOLD = 0.75
    HAND_DEPLOY_TEMPLATE_THRESHOLD = 0.75
    HAND_DEPLOY_CONFIRM_FRAMES = 1
    SHOP_TEMPLATE_THRESHOLD = 0.75
    SHOP_GLOW_TEMPLATE_THRESHOLD = 0.65
    SHOP_GOLD_ICON_THRESHOLD = 0.75
    # Chess 运行时统一使用四档间隔。较慢的 2/3 秒轮询通过倍数表达，
    # 不再为每个功能分别维护近似数值。
    FAST_OPERATION_INTERVAL = 0.1
    SCREENSHOT_INTERVAL = 0.35
    ACTION_SETTLE_INTERVAL = 0.6
    SLOW_POLL_INTERVAL = 1.0
    ACTION_ICON_WAIT_TIMEOUT = 3.0
    ACTION_ICON_MAX_ATTEMPTS = 3
    # 首领挑战会大幅改变棋盘显示位置，固定站位的勾玉检测框不可用。
    BOSS_CHALLENGE_ROUNDS = frozenset({9, 15, 21, 27, 33})
    HAND_DEPLOY_SAFETY_LIMIT = 20
    HAND_CLEANUP_SAFETY_LIMIT = 30
    HAND_CLEANUP_CLEAN_CONFIRM_FRAMES = 3
    # 系统自动上阵优先占用棋盘右侧 11、12、9、10 号位。百鬼结束后
    # 只需要依次回收这些候选格；若 9 号位由脚本亲自部署，则保留该格。
    BOARD_RECALL_POSITIONS = (11, 12, 9, 10)
    # c_card_1/2/3.png 专用于检测棋盘式神头顶的三种勾玉颜色。
    BOARD_OCCUPANCY_TEMPLATE_THRESHOLD = 0.68
    ROUND_CONFIRM_FRAMES = 2
    GAME_END_CONFIRM_FRAMES = 3
    GAME_OVER_WAIT_TIMEOUT = 60.0
    GAME_ENTER_TIMEOUT = 120.0
    UNKNOWN_STATE_TIMEOUT = 25.0
    SHOP_OPEN_TIMEOUT = 8.0
    SHOP_CLOSE_TIMEOUT = 8.0
    SHOP_REFRESH_CHANGED_SLOT_MINIMUM = 3
    SHOP_REFRESH_SLOT_IMAGE_DIFF_THRESHOLD = 8.0
    ECONOMY_CONFIRM_RETRIES = 2
    SHOP_BUY_TIMEOUT = 30.0
    GRIGRI_SELECT_TIMEOUT = 12.0
    GRIGRI_REFRESH_MAXIMUM = 3
    GRIGRI_ICON_THRESHOLD = 0.72
    EXPERIENCE_COST = 4
    SHOP_REFRESH_COST = 2
    HAKUZOSU_PROTECT_NAME = 'hakuzosu_protect'
    HAKUZOSU_PROTECT_DISPLAY_NAME = '守护之印'
    HAKUZOSU_PROTECT_IMAGE = 'c/c_hakuzosu_protect.png'
    HAKUZOSU_NAME = 'yume_san_byakuzou'
    ARAKAWA_BOND_NAME = '荒川'
    DEFAULT_LINEUP_KEY = REGISTERED_DEFAULT_LINEUP_KEY
    LINEUP_REGISTRY = REGISTERED_LINEUP_REGISTRY
    SOUL_EQUIP_SAFETY_LIMIT = 20
    DISCOVER_SOUL_SAFETY_LIMIT = 10
    DISCOVER_SOUL_UI_TIMEOUT = 8.0
    SOUL_ODD_SET_Y_OFFSET = -5
    SOUL_TEMPLATE_THRESHOLD = 0.60
    SOUL_TEMPLATE_SCALES = (0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20)
    UNKNOWN_SELL_CONFIRM_FRAMES = 3
    UNKNOWN_LINEUP_PROTECT_THRESHOLD = 0.58
    UNKNOWN_LINEUP_PROTECT_SCALES = (0.90, 0.95, 1.00, 1.05, 1.10)
    SOUL_DISPLAY_NAMES = {
        entry.romaji: entry.chinese_name
        for entry in SOUL_ENTRIES
    }
    ATTACK_SOUL_NAMES = {
        entry.romaji
        for entry in SOUL_ENTRIES
        if entry.category == 'attack'
    }
    FUNCTIONAL_SOUL_NAMES = {
        entry.romaji
        for entry in SOUL_ENTRIES
        if entry.category == 'functional'
    }
