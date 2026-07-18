# This Python file uses the following encoding: utf-8

import random
import re
import time
from functools import cached_property
from pathlib import Path

import cv2
import numpy as np

from module.atom.click import RuleClick
from module.atom.image import RuleImage
from module.exception import GameStuckError, TaskEnd
from module.logger import logger
from tasks.Chess.assets import ChessAssets
from tasks.Chess.board_positions import SET_JADE_AREAS, SET_POSITIONS
from tasks.Chess.config import Chess
from tasks.Chess.lineup import (
    DEFAULT_LINEUP_KEY as REGISTERED_DEFAULT_LINEUP_KEY,
    LINEUP_REGISTRY as REGISTERED_LINEUP_REGISTRY,
    resolve_lineup_key,
)
from tasks.Chess.shikigami_catalog import SHIKIGAMI_BY_ROMAJI
from tasks.Chess.press_and_drag import Press_and_Drag
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.GameUi.game_ui import GameUi
from tasks.Chess.page import page_chess, random_click


class ScriptTask(GameUi, GeneralBattle, ChessAssets):
    """百鬼棋局任务入口。"""

    conf: Chess = None
    HAND_AREA = (179, 540, 957, 158)
    HAND_TEMPLATE_THRESHOLD = 0.7
    HAND_DEPLOY_TEMPLATE_THRESHOLD = 0.6
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
    ALIVE_PLAYERS_CONFIRM_FRAMES = 2
    GAME_ENTER_TIMEOUT = 120.0
    RESULT_RETURN_TIMEOUT = 60.0
    UNKNOWN_STATE_TIMEOUT = 25.0
    NORMAL_SCREENSHOT_INTERVAL = 0.35
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

    def get_lineup_strategy(
        self,
        lineup_key: str | None = None,
    ) -> dict:
        """返回当前阵容策略；新增体系只需实现同结构模块并注册。"""
        selected = (
            lineup_key
            or getattr(self, '_active_lineup_key', None)
            or self.DEFAULT_LINEUP_KEY
        )
        key = resolve_lineup_key(selected)
        entry = self.LINEUP_REGISTRY.get(key)
        if entry is None:
            logger.warning(
                f'Unknown Chess lineup strategy [{selected}], fallback to '
                f'[{self.DEFAULT_LINEUP_KEY}]'
            )
            entry = self.LINEUP_REGISTRY[self.DEFAULT_LINEUP_KEY]
        return entry['strategy']

    def select_lineup_strategy(self, lineup_key: str) -> dict:
        """切换当前阵容，并清除依赖阵容的图片规则缓存。"""
        strategy = self.get_lineup_strategy(lineup_key)
        self._active_lineup_key = strategy['key']
        for cache_name in (
            'lineup_shikigami_hand_rules',
            'shikigami_shop_rules',
            'hakuzosu_protect_rule',
        ):
            self.__dict__.pop(cache_name, None)
        logger.info(
            f'Select Chess lineup strategy: '
            f'{strategy["key"]} ({strategy["display_name"]})'
        )
        return strategy

    def _shikigami_display_name(self, name: str | None) -> str:
        """把内部罗马音转换成日志中更易读的中文名。"""
        if not name:
            return '未知'
        strategy_config = self.get_lineup_strategy()['shikigami'].get(name)
        if strategy_config is not None:
            return strategy_config.get('display_name', name)
        entry = SHIKIGAMI_BY_ROMAJI.get(name)
        return entry.chinese_name if entry is not None else str(name)

    def _hand_shikigami_summary(self) -> list[str]:
        """汇总当前手牌中的式神，仅用于每回合摘要日志。"""
        names = []
        for card_roi in self._hand_card_rois():
            result = self.classify_hand_card(card_roi)
            if result['type'] != 'shikigami':
                continue
            names.append(self._shikigami_display_name(result['name']))
        return names

    def _shop_shikigami_summary(self) -> list[str]:
        """汇总当前商店五格中已识别出的式神。"""
        names = []
        for _, click_rule in self._shop_slots():
            matched = self._match_shop_shikigami_avatar(
                click_rule,
                rules=self.all_shikigami_shop_rules,
            )
            names.append(
                self._shikigami_display_name(matched['name'])
                if matched is not None
                else '空/未识别'
            )
        return names

    @staticmethod
    def _soul_category_display(category: str | None) -> str:
        if category == 'attack':
            return '输出'
        if category == 'functional':
            return '功能'
        return str(category or '未知')

    @property
    def shikigami_deploy_positions(self) -> dict[str, int]:
        return {
            name: int(config['position'])
            for name, config in self.get_lineup_strategy()['shikigami'].items()
        }

    def _lineup_final_level(self) -> int:
        """阵容最终不保留经济的阶数，等于当前羁绊式神总人数。"""
        return len(self.get_lineup_strategy()['shikigami'])

    @classmethod
    def _load_hand_template_folder(
        cls,
        folder: str,
        prefix: str,
    ) -> list[tuple[str, RuleImage]]:
        """将指定目录中的 PNG 加载为整个手牌区域的识别模板。"""
        template_dir = Path(__file__).resolve().parent / folder
        rules: list[tuple[str, RuleImage]] = []
        for file in sorted(template_dir.glob('*.png')):
            stem = file.stem
            if not stem.startswith(prefix):
                continue

            name = stem[len(prefix):]
            # `_1` 是从图鉴裁出的头像模板；完整手牌模板没有该后缀。
            # 两类模板归一为同一个式神名，并同时参与匹配。
            if folder == 'shikigami' and name.endswith('_1'):
                name = name[:-2]
            rule = RuleImage(
                roi_front=(cls.HAND_AREA[0], cls.HAND_AREA[1], 1, 1),
                roi_back=cls.HAND_AREA,
                threshold=cls.HAND_TEMPLATE_THRESHOLD,
                method=RuleImage.METHOD_TEMPLATE_MATCH,
                file=file.as_posix(),
            )
            rules.append((name, rule))

        logger.debug(f'Loaded {len(rules)} Chess {folder} hand templates')
        return rules

    @cached_property
    def shikigami_hand_rules(self) -> list[tuple[str, RuleImage]]:
        """式神资源大全；用于通用手牌分类，不代表当前阵容会使用。"""
        return self._load_hand_template_folder('shikigami/card', prefix='card_')

    @cached_property
    def board_occupancy_rules(self) -> tuple[RuleImage, ...]:
        """直接加载三种场上勾玉；不依赖 assets/json 注册项。"""
        template_dir = Path(__file__).resolve().parent / 'c'
        return tuple(
            RuleImage(
                roi_front=(0, 0, 1, 1),
                roi_back=(0, 0, 1, 1),
                threshold=self.BOARD_OCCUPANCY_TEMPLATE_THRESHOLD,
                method=RuleImage.METHOD_TEMPLATE_MATCH,
                file=(template_dir / f'c_card_{index}.png').as_posix(),
            )
            for index in range(1, 4)
        )

    def _load_strategy_shikigami_rules(
        self,
        entries: dict,
        image_field: str,
        threshold: float,
    ) -> list[tuple[str, RuleImage]]:
        """按阵容策略声明的文件名加载式神资源。"""
        template_dir = Path(__file__).resolve().parent / 'shikigami'
        rules = []
        for name, config in entries.items():
            for filename in config.get(image_field, ()):
                file = template_dir / filename
                if not file.exists():
                    logger.warning(
                        f'Chess strategy image is missing: '
                        f'lineup={self.get_lineup_strategy()["key"]}, '
                        f'name={name}, file={filename}'
                    )
                    continue
                rules.append((name, RuleImage(
                    roi_front=(self.HAND_AREA[0], self.HAND_AREA[1], 1, 1),
                    roi_back=self.HAND_AREA,
                    threshold=threshold,
                    method=RuleImage.METHOD_TEMPLATE_MATCH,
                    file=file.as_posix(),
                )))
        return rules

    @cached_property
    def lineup_shikigami_hand_rules(self) -> list[tuple[str, RuleImage]]:
        """当前阵容允许上阵的式神手牌模板。"""
        rules = self._load_strategy_shikigami_rules(
            self.get_lineup_strategy()['shikigami'],
            image_field='hand_images',
            threshold=self.HAND_TEMPLATE_THRESHOLD,
        )
        logger.debug(
            f'Loaded {len(rules)} active Chess lineup hand templates'
        )
        return rules

    @cached_property
    def hakuzosu_protect_rule(self) -> RuleImage:
        """梦山白藏主伴生手牌：守护之印。"""
        file = (
            Path(__file__).resolve().parent
            / self.HAKUZOSU_PROTECT_IMAGE
        )
        return RuleImage(
            roi_front=(self.HAND_AREA[0], self.HAND_AREA[1], 1, 1),
            roi_back=self.HAND_AREA,
            threshold=self.HAND_TEMPLATE_THRESHOLD,
            method=RuleImage.METHOD_TEMPLATE_MATCH,
            file=file.as_posix(),
        )

    @cached_property
    def shikigami_shop_rules(self) -> list[tuple[str, RuleImage]]:
        """仅加载当前阵容声明的商店卡面头像模板。"""
        rules = self._load_strategy_shikigami_rules(
            self.get_lineup_strategy()['shikigami'],
            image_field='shop_images',
            threshold=self.SHOP_TEMPLATE_THRESHOLD,
        )
        logger.debug(f'Loaded {len(rules)} Chess shop avatar templates')
        return rules

    @cached_property
    def all_shikigami_shop_rules(self) -> list[tuple[str, RuleImage]]:
        """全式神商店模板；只用于日志汇总，不参与购买决策。"""
        template_dir = Path(__file__).resolve().parent / 'shikigami/store'
        rules: list[tuple[str, RuleImage]] = []
        for file in sorted(template_dir.glob('store_*.png')):
            name = file.stem[len('store_'):]
            rules.append((
                name,
                RuleImage(
                    roi_front=(self.HAND_AREA[0], self.HAND_AREA[1], 1, 1),
                    roi_back=self.HAND_AREA,
                    threshold=self.SHOP_TEMPLATE_THRESHOLD,
                    method=RuleImage.METHOD_TEMPLATE_MATCH,
                    file=file.as_posix(),
                ),
            ))
        logger.debug(f'Loaded {len(rules)} all Chess shop avatar templates')
        return rules

    @cached_property
    def soul_hand_rules(self) -> list[tuple[str, RuleImage]]:
        """御魂手牌模板，文件名格式为 `sou_<name>.png`。"""
        return self._load_hand_template_folder('soul', prefix='sou_')

    def classify_hand_card(self, card_roi: tuple[int, int, int, int]) -> dict:
        """识别一个已定位的手牌框，未收录时返回 `unknown`。"""
        best = None
        categories = (
            ('shikigami', self.shikigami_hand_rules),
            ('soul', self.soul_hand_rules),
        )
        for category, rules in categories:
            for name, rule in rules:
                matches = rule.match_all_any(
                    self.device.image,
                    roi=list(card_roi),
                    threshold=rule.threshold,
                    nms_threshold=0.3,
                    frame_id=self.device.image_frame_id,
                )
                if not matches:
                    continue
                match = max(matches, key=lambda item: item[0])
                if best is None or match[0] > best['score']:
                    score, x, y, width, height = match
                    best = {
                        'type': category,
                        'name': name,
                        'score': score,
                        'position': (x + width // 2, y + height // 2),
                        'action': None,
                    }

        if best is not None:
            return best
        x, y, width, height = card_roi
        return {
            'type': 'unknown',
            'name': None,
            'score': 0.0,
            'position': (x + width // 2, y + height // 2),
            'action': 'sell',
        }

    def _possible_lineup_shikigami(
        self,
        card_roi: tuple[int, int, int, int],
    ) -> dict | None:
        """以较低阈值复查 unknown，命中任一阵容头像即保护该卡。"""
        x, y, width, height = card_roi
        source = self.device.image[y:y + height, x:x + width]
        best = None
        for name, rule in self.lineup_shikigami_hand_rules:
            template = rule.image
            for scale in self.UNKNOWN_LINEUP_PROTECT_SCALES:
                scaled_width = max(1, int(template.shape[1] * scale))
                scaled_height = max(1, int(template.shape[0] * scale))
                if (
                    scaled_height > source.shape[0]
                    or scaled_width > source.shape[1]
                ):
                    continue
                scaled = cv2.resize(
                    template,
                    (scaled_width, scaled_height),
                    interpolation=(
                        cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
                    ),
                )
                result = cv2.matchTemplate(
                    source,
                    scaled,
                    cv2.TM_CCOEFF_NORMED,
                )
                _, score, _, _ = cv2.minMaxLoc(result)
                if best is None or score > best['score']:
                    best = {
                        'name': name,
                        'score': float(score),
                        'scale': scale,
                    }
        if (
            best is not None
            and best['score'] >= self.UNKNOWN_LINEUP_PROTECT_THRESHOLD
        ):
            return best
        return None

    def _confirm_unknown_hand_card(
        self,
        card_roi: tuple[int, int, int, int],
    ) -> dict | None:
        """连续多帧确认 unknown；疑似阵容卡时返回 None 禁止出售。"""
        original_center_x = card_roi[0] + card_roi[2] // 2
        latest = None
        for confirmation in range(1, self.UNKNOWN_SELL_CONFIRM_FRAMES + 1):
            if confirmation > 1:
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                self.screenshot()
            rois = self._hand_card_rois()
            current_roi = min(
                rois,
                key=lambda roi: abs(
                    roi[0] + roi[2] // 2 - original_center_x
                ),
                default=None,
            )
            if (
                current_roi is None
                or abs(
                    current_roi[0] + current_roi[2] // 2
                    - original_center_x
                ) > 45
            ):
                logger.debug(
                    'Protect unknown Chess hand card: '
                    'card position changed during confirmation'
                )
                return None
            soul = self._soul_match_in_card(current_roi)
            if soul is not None:
                logger.debug(
                    'Protect Chess soul hand card from unknown-card sale: '
                    f'name={soul["text"]}, score={soul["score"]:.3f}, '
                    f'confirmation={confirmation}'
                )
                return None
            protect = self._hakuzosu_protect_match_in_card(current_roi)
            if protect is not None:
                logger.debug(
                    'Protect Chess Hakuzosu protect card from unknown-card '
                    f'sale: score={protect["score"]:.3f}, '
                    f'confirmation={confirmation}'
                )
                return None
            latest = self.classify_hand_card(current_roi)
            if latest['type'] != 'unknown':
                logger.debug(
                    'Protect Chess hand card after repeated classification: '
                    f'type={latest["type"]}, name={latest["name"]}'
                )
                return None
            possible = self._possible_lineup_shikigami(current_roi)
            if possible is not None:
                logger.debug(
                    'Protect possible lineup Chess hand card from sale: '
                    f'name={possible["name"]}, '
                    f'score={possible["score"]:.3f}, '
                    f'confirmation={confirmation}'
                )
                return None
            logger.debug(
                f'Chess unknown hand card confirmation '
                f'{confirmation}/{self.UNKNOWN_SELL_CONFIRM_FRAMES}: '
                f'position={latest["position"]}'
            )
        return latest

    @staticmethod
    def _rule_center(rule: RuleImage | RuleClick) -> tuple[int, int]:
        x, y, width, height = rule.roi_back
        return x + width // 2, y + height // 2

    def _set_position(self, set_index: int) -> tuple[int, int]:
        """读取独立配置中维护的 1-12 号纯站位坐标。"""
        try:
            return tuple(SET_POSITIONS[int(set_index)])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f'Chess board set position is not configured: {set_index}'
            ) from exc

    def _set_jade_area(self, set_index: int) -> tuple[int, int, int, int]:
        """读取独立配置中维护的 1-12 号勾玉占位检测区域。"""
        try:
            return tuple(SET_JADE_AREAS[int(set_index)])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f'Chess board jade area is not configured: {set_index}'
            ) from exc

    def sell_hand_card(self, source: tuple[int, int]) -> None:
        """统一拖到左侧售卖区，避免出售动作改变商店开关状态。"""
        target_rule = self.I_EXPERIENCE
        Press_and_Drag(
            self.device,
            p1=source,
            p2=self._rule_center(target_rule),
            hold_duration=0.5,
            point_random=(-3, -3, 3, 3),
            swipe_duration=0.5,
            name='CHESS_SELL_UNKNOWN_HAND_CARD',
        )
        self.close_shikigami_specifics_if_open()

    def close_shikigami_specifics_if_open(self) -> bool:
        """卖卡/上卡误打开式神详情页时，点击安全区域直到关闭。"""
        if not hasattr(self, 'I_SHIKIGAMI_SPECIFICS'):
            return False
        if not self.appear(self.I_SHIKIGAMI_SPECIFICS):
            return False

        logger.warning(
            'Chess shikigami specifics opened unexpectedly, close it'
        )
        closed = False
        for attempt in range(1, 8):
            self.click(self.C_CLICK_CLOSE_SPECIFICS_AREA, interval=0.1)
            time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
            self.screenshot()
            if not self.appear(self.I_SHIKIGAMI_SPECIFICS):
                logger.debug(
                    f'Chess shikigami specifics closed, attempts={attempt}'
                )
                closed = True
                break
        if not closed:
            logger.warning('Chess shikigami specifics still visible')
        return closed

    def sell_rightmost_hand_card(self) -> dict | None:
        """手牌满时直接出售最右侧卡牌，不再识别或保护星级。"""
        hand_cards = self._hand_card_detections()
        if not hand_cards:
            logger.warning(
                'Chess hand is full but no hand-card anchor was detected'
            )
            return None

        target = max(
            hand_cards,
            key=lambda card: card['roi'][0] + card['roi'][2] // 2,
        )
        x, y, width, height = target['roi']
        position = (x + width // 2, y + height // 2)
        identity = self.classify_hand_card(target['roi'])
        sale_key = (identity['type'], identity['name'])
        count_before = self._hand_card_identity_count(*sale_key)
        logger.info(
            f'Sell Chess card: rightmost hand card, '
            f'name={self._shikigami_display_name(identity["name"])}, '
            f'position={position}'
        )
        self.sell_hand_card(position)
        time.sleep(self.HAND_SELL_WAIT)
        self.screenshot()
        self.close_shikigami_specifics_if_open()
        self.screenshot()
        count_after = self._hand_card_identity_count(*sale_key)
        if count_after >= count_before:
            logger.warning(
                'Rightmost Chess card sale not confirmed; '
                f'count={count_before}->{count_after}'
            )
            return None
        logger.info(
            'Rightmost Chess card sale confirmed: '
            f'count={count_before}->{count_after}'
        )
        return {
            'type': 'rightmost',
            'name': identity['name'],
            'position': position,
        }

    def _hakuzosu_protect_target_position(self) -> int | None:
        """当前阵容中守护之印的目标位置；没有白藏主则禁用。"""
        strategy = self.get_lineup_strategy()
        if self.HAKUZOSU_NAME not in strategy['shikigami']:
            return None
        return int(strategy.get('hakuzosu_protect_position', 1))

    def _find_hakuzosu_protect_hand_card(self) -> dict | None:
        """定位手牌中的守护之印。"""
        if self._hakuzosu_protect_target_position() is None:
            return None
        matches = self.hakuzosu_protect_rule.match_all_any(
            self.device.image,
            roi=list(self.HAND_AREA),
            threshold=self.hakuzosu_protect_rule.threshold,
            nms_threshold=0.3,
            frame_id=self.device.image_frame_id,
        )
        if not matches:
            return None
        score, x, y, width, height = max(matches, key=lambda item: item[0])
        return {
            'name': self.HAKUZOSU_PROTECT_NAME,
            'display_name': self.HAKUZOSU_PROTECT_DISPLAY_NAME,
            'score': score,
            'position': (x + width // 2, y + height // 2),
        }

    def _hakuzosu_protect_match_in_card(
        self,
        card_roi: tuple[int, int, int, int],
    ) -> dict | None:
        """确认指定手牌框是否为守护之印，用于卖卡保护。"""
        if self._hakuzosu_protect_target_position() is None:
            return None
        matches = self.hakuzosu_protect_rule.match_all_any(
            self.device.image,
            roi=list(card_roi),
            threshold=self.hakuzosu_protect_rule.threshold,
            nms_threshold=0.3,
            frame_id=self.device.image_frame_id,
        )
        if not matches:
            return None
        score, x, y, width, height = max(matches, key=lambda item: item[0])
        return {
            'name': self.HAKUZOSU_PROTECT_NAME,
            'text': self.HAKUZOSU_PROTECT_DISPLAY_NAME,
            'score': score,
            'position': (x + width // 2, y + height // 2),
        }

    def equip_hakuzosu_protect_after_deploy(self) -> bool:
        """梦山白藏主上阵后，立刻尝试给目标位装备守护之印。"""
        target_position = self._hakuzosu_protect_target_position()
        if target_position is None:
            return False
        if not self._is_preparation_mode():
            return False
        card = self._find_hakuzosu_protect_hand_card()
        if card is None:
            logger.debug(
                'Chess Hakuzosu protect card is not in hand after '
                'Byakuzou deployment'
            )
            return False
        logger.info(
            f'检测到{card["display_name"]}(功能)，'
            f'移动到{target_position}号位'
        )
        if not self._equip_soul_card(
            source=card['position'],
            set_index=int(target_position),
            operation_name=self.HAKUZOSU_PROTECT_NAME.upper(),
        ):
            return False
        time.sleep(self.SOUL_EQUIP_WAIT)
        self.screenshot()
        return True

    def _equip_soul_card(
        self,
        source: tuple[int, int],
        set_index: int,
        operation_name: str,
    ) -> bool:
        """御魂及阵容特殊手牌共用入口；拖动前必须关闭商店。"""
        if not self._ensure_shop_closed():
            logger.warning(
                f'Abort Chess soul equipment: shop could not be closed, '
                f'operation={operation_name}'
            )
            return False
        target = self._soul_target_position(set_index)
        logger.debug(
            f'Equip Chess soul-type card {operation_name} to set '
            f'{set_index}: source={source}, target={target}'
        )
        Press_and_Drag(
            self.device,
            p1=source,
            p2=target,
            hold_duration=0.5,
            point_random=(-3, -3, 3, 3),
            swipe_duration=0.5,
            name=f'CHESS_EQUIP_SOUL_{operation_name}_SET_{set_index}',
        )
        return True

    def deploy_shikigami_hand_card(
        self,
        name: str,
        source: tuple[int, int],
    ) -> bool:
        """按当前策略站位拖动式神，并以人数变化确认是否上阵。"""
        set_index = self.shikigami_deploy_positions.get(name)
        if set_index is None:
            logger.warning(f'Chess shikigami has no deploy position: {name}')
            return False

        if not self._ensure_shop_closed():
            logger.warning(
                f'Abort Chess shikigami deployment: shop is not closed '
                f'before dragging {name}'
            )
            return False
        count_before = self._read_shikigami_count()
        target_position = self._set_position(set_index)
        logger.debug(
            f'Deploy Chess shikigami {name} to set {set_index}, '
            f'source={source}, target={target_position}'
        )
        Press_and_Drag(
            self.device,
            p1=source,
            p2=target_position,
            hold_duration=0.5,
            point_random=(-3, -3, 3, 3),
            swipe_duration=0.5,
            name=f'CHESS_DEPLOY_{name.upper()}_SET_{set_index}',
        )
        self.close_shikigami_specifics_if_open()
        time.sleep(self.HAND_DEPLOY_WAIT)
        self.screenshot()
        count_after = self._read_shikigami_count()

        if count_before is not None and count_after is not None:
            succeeded = count_after['current'] > count_before['current']
            if succeeded:
                logger.debug(
                    f'Chess shikigami deploy confirmed: {name} -> '
                    f'set {set_index}, '
                    f'{count_before["current"]}/{count_before["total"]} -> '
                    f'{count_after["current"]}/{count_after["total"]}'
                )
                return True
            else:
                logger.warning(
                    f'Chess shikigami count did not confirm deploy: {name} -> '
                    f'set {set_index}, lineup stayed at '
                    f'{count_before["current"]}/{count_before["total"]}; '
                    'verify the hand card before rejecting it'
                )

        # 人数 OCR 偶尔会被动画遮住或读到不变值。此时不再把一次未确认
        # 的拖动直接记为成功；检查原横坐标附近是否仍有同名手牌兜底。
        for rule_name, rule in self.lineup_shikigami_hand_rules:
            if rule_name != name:
                continue
            matches = rule.match_all_any(
                self.device.image,
                roi=list(self.HAND_AREA),
                threshold=rule.threshold,
                nms_threshold=0.3,
                frame_id=self.device.image_frame_id,
            )
            if any(
                abs((x + width // 2) - source[0]) <= 45
                for _, x, _, width, _ in matches
            ):
                logger.warning(
                    f'Chess shikigami deploy not confirmed by hand card: '
                    f'{name} remains near {source}'
                )
                return False

        logger.debug(
            f'Chess shikigami deploy accepted by hand-card disappearance: '
            f'{name} -> set {set_index}'
        )
        return True

    def _find_best_shikigami_hand_card(
        self,
        excluded_names: set[str] | None = None,
    ) -> dict | None:
        """让阵容头像模板直接扫描整个手牌区，返回最左侧命中卡。"""
        excluded_names = excluded_names or set()
        frame_candidates = []
        for frame_index in range(1, self.HAND_DEPLOY_CONFIRM_FRAMES + 1):
            if frame_index > 1:
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                self.screenshot()
            frame_candidates.append(
                self._scan_lineup_hand_card_candidates_once(excluded_names)
            )

        merged = {}
        for candidates in frame_candidates:
            for candidate in candidates:
                key = (
                    candidate['name'],
                    round(candidate['position'][0] / 12),
                )
                item = merged.setdefault(key, {
                    **candidate,
                    'scores': [],
                    'frames': 0,
                })
                item['scores'].append(candidate['score'])
                item['frames'] += 1

        candidates = []
        for item in merged.values():
            if item['frames'] < self.HAND_DEPLOY_CONFIRM_FRAMES:
                logger.debug(
                    'Skip Chess lineup hand card candidate: '
                    f'name={item["name"]}, frames={item["frames"]}/'
                    f'{self.HAND_DEPLOY_CONFIRM_FRAMES}'
                )
                continue
            avg_score = sum(item['scores']) / len(item['scores'])
            item['score'] = avg_score
            if avg_score < self.HAND_DEPLOY_TEMPLATE_THRESHOLD:
                logger.debug(
                    'Skip Chess lineup hand card candidate below threshold: '
                    f'name={item["name"]}, avg_score={avg_score:.3f}, '
                    f'threshold={self.HAND_DEPLOY_TEMPLATE_THRESHOLD}'
                )
                continue
            candidates.append(item)
            logger.debug(
                'Chess lineup hand card candidate confirmed: '
                f'name={item["name"]}, '
                f'avg_score={avg_score:.3f}, '
                f'position={item["position"]}'
            )

        if not candidates:
            logger.debug('No deployable Chess lineup hand card detected')
            return None

        # 同名多张时选最左侧；不同名之间按手牌从左到右处理，避免高分
        # 模板长期压住后续体系卡，导致 2/3 这种未满员场景不上人。
        selected_by_name = {}
        for candidate in sorted(
            candidates,
            key=lambda item: (item['position'][0], -item['score']),
        ):
            selected_by_name.setdefault(candidate['name'], candidate)
        return min(
            selected_by_name.values(),
            key=lambda item: item['position'][0],
        )

    def _scan_lineup_hand_card_candidates_once(
        self,
        excluded_names: set[str],
    ) -> list[dict]:
        """单帧：阵容头像模板直接在完整手牌区域内匹配。"""
        candidates = []
        for name, rule in self.lineup_shikigami_hand_rules:
            if name in excluded_names:
                continue
            matches = rule.match_all_any(
                self.device.image,
                roi=list(self.HAND_AREA),
                threshold=self.HAND_DEPLOY_TEMPLATE_THRESHOLD,
                nms_threshold=0.3,
                frame_id=self.device.image_frame_id,
            )
            for score, x, y, width, height in matches:
                candidate = {
                    'name': name,
                    'score': score,
                    'position': (x + width // 2, y + height // 2),
                }
                logger.info(
                    'Chess deploy hand scan: '
                    f'best={self._shikigami_display_name(name)}, '
                    f'score={score:.3f}, position={candidate["position"]}'
                )
                candidates.append(candidate)

        # 不同角色模板可能在同一张卡上同时得到较低分命中。按人物中心
        # 聚类，每个实际卡位只保留最高分结果，避免同一卡被认成两个人。
        deduplicated = []
        for candidate in sorted(
            candidates,
            key=lambda item: item['score'],
            reverse=True,
        ):
            if any(
                abs(candidate['position'][0] - kept['position'][0]) <= 32
                and abs(candidate['position'][1] - kept['position'][1]) <= 40
                for kept in deduplicated
            ):
                continue
            deduplicated.append(candidate)
        return sorted(
            deduplicated,
            key=lambda item: item['position'][0],
        )

    def _soul_category(self, name: str) -> str | None:
        if name in self.ATTACK_SOUL_NAMES:
            return 'attack'
        if name in self.FUNCTIONAL_SOUL_NAMES:
            return 'functional'
        return None

    def _soul_target_position(self, set_index: int) -> tuple[int, int]:
        """返回御魂类卡牌的投放位置；奇数位统一向北偏移 5 像素。"""
        x, y = self._set_position(set_index)
        if set_index % 2 == 1:
            y += self.SOUL_ODD_SET_Y_OFFSET
        return x, y

    def _soul_targets(
        self,
        category: str,
        verified_names: set[str],
    ) -> list[tuple[int, tuple[int, int]]]:
        """返回本局尚未判满的同类型御魂目标。"""
        full_positions = set(getattr(self, '_soul_full_positions', set()))
        active_positions = sorted(
            self.shikigami_deploy_positions[name]
            for name in verified_names
            if name in self.shikigami_deploy_positions
        )
        wanted_parity = 0 if category == 'attack' else 1
        targets = []
        for set_index in active_positions:
            if (
                set_index % 2 != wanted_parity
                or set_index in full_positions
            ):
                continue
            # 前排奇数位统一使用向北偏移后的御魂投放位置。
            targets.append((set_index, self._soul_target_position(set_index)))
        return targets

    def _template_soul_hand_cards(self) -> list[dict]:
        """在手牌区对 soul 模板执行多尺度匹配。"""
        candidates = []
        roi_x, roi_y, roi_width, roi_height = self.HAND_AREA
        source = self.device.image[
            roi_y:roi_y + roi_height,
            roi_x:roi_x + roi_width,
        ]
        for name, rule in self.soul_hand_rules:
            category = self._soul_category(name)
            if category is None:
                continue
            matches = []
            template = rule.image
            for scale in self.SOUL_TEMPLATE_SCALES:
                width = max(1, int(template.shape[1] * scale))
                height = max(1, int(template.shape[0] * scale))
                if width > source.shape[1] or height > source.shape[0]:
                    continue
                scaled = cv2.resize(
                    template,
                    (width, height),
                    interpolation=(
                        cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
                    ),
                )
                result = cv2.matchTemplate(
                    source,
                    scaled,
                    cv2.TM_CCOEFF_NORMED,
                )
                locations = np.where(
                    result >= self.SOUL_TEMPLATE_THRESHOLD
                )
                for point_x, point_y in zip(*locations[::-1]):
                    matches.append((
                        float(result[point_y, point_x]),
                        roi_x + int(point_x),
                        roi_y + int(point_y),
                        width,
                        height,
                    ))
            if matches:
                boxes = [list(match[1:]) for match in matches]
                scores = [match[0] for match in matches]
                indices = cv2.dnn.NMSBoxes(
                    boxes,
                    scores,
                    score_threshold=self.SOUL_TEMPLATE_THRESHOLD,
                    nms_threshold=0.3,
                )
                matches = [
                    matches[int(index)]
                    for index in np.array(indices).reshape(-1).tolist()
                ] if len(indices) else []
            for score, x, y, width, height in matches:
                candidates.append({
                    'name': name,
                    'text': self.SOUL_DISPLAY_NAMES[name],
                    'position': (x + width // 2, y + height // 2),
                    'score': score,
                    'source': 'template',
                    'category': category,
                })
                logger.debug(
                    f'Chess soul image matched: {self.SOUL_DISPLAY_NAMES[name]}, '
                    f'score={score:.3f}, box={(x, y, width, height)}'
                )
        return candidates

    def _soul_hand_cards(self) -> list[dict]:
        """仅使用 soul 文件夹图片识别御魂，并按手牌横坐标去重。"""
        merged = []
        candidates = self._template_soul_hand_cards()
        for candidate in sorted(
            candidates,
            key=lambda item: (
                item['position'][0],
                -item['score'],
            ),
        ):
            existing = next((
                item
                for item in merged
                if abs(item['position'][0] - candidate['position'][0]) <= 24
            ), None)
            if existing is None:
                merged.append(candidate)
            elif candidate['score'] > existing['score']:
                merged.remove(existing)
                merged.append(candidate)
        return sorted(merged, key=lambda item: item['position'][0])

    def _soul_match_in_card(
        self,
        card_roi: tuple[int, int, int, int],
        soul_cards: list[dict] | None = None,
    ) -> dict | None:
        """返回落在指定手牌框内的最佳御魂图片匹配。"""
        x, _, width, _ = card_roi
        soul_cards = (
            self._soul_hand_cards() if soul_cards is None else soul_cards
        )
        matches = [
            item
            for item in soul_cards
            if x - 8 <= item['position'][0] <= x + width + 8
        ]
        if not matches:
            return None
        return max(matches, key=lambda item: item['score'])

    def _discover_soul_hand_cards(self) -> list[dict]:
        """使用手牌文字区定位“发现御魂”特殊卡。"""
        results = self.O_BADGE_AREA.detect_and_ocr(self.device.image)
        roi_x, roi_y = self.O_BADGE_AREA.roi[:2]
        cards = []
        for result in results:
            text = self._normalize_ocr_text(result.ocr_text).strip(
                '()（）[]【】'
            )
            if not text:
                continue
            if '发现御魂' in text:
                similarity = 1.0
                matched = True
            else:
                matched, similarity, _ = self._fuzzy_text_match(
                    '发现御魂',
                    text,
                )
            if not matched:
                continue

            points = result.box
            left = min(int(point[0]) for point in points)
            right = max(int(point[0]) for point in points)
            top = min(int(point[1]) for point in points)
            bottom = max(int(point[1]) for point in points)
            cards.append({
                'text': text,
                'similarity': similarity,
                'score': float(result.score),
                'position': (
                    roi_x + (left + right) // 2,
                    roi_y + (top + bottom) // 2,
                ),
            })
        return sorted(cards, key=lambda item: item['position'][0])

    def _wait_for_discover_soul_choices(self) -> list[RuleImage]:
        """等待发现御魂三选一界面，并返回本帧实际出现的选项。"""
        deadline = time.monotonic() + self.DISCOVER_SOUL_UI_TIMEOUT
        rules = (
            self.I_SELECT_SOUL_1,
            self.I_SELECT_SOUL_2,
            self.I_SELECT_SOUL_3,
        )
        while time.monotonic() < deadline:
            self.screenshot()
            options = [rule for rule in rules if self.appear(rule)]
            if options:
                return options
            time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
        return []

    def discover_souls_from_hand(self) -> int:
        """优先使用所有“发现御魂”卡，并在出现的选项中随机选择。"""
        used = 0
        for _ in range(self.DISCOVER_SOUL_SAFETY_LIMIT):
            if not self._is_preparation_mode():
                logger.debug(
                    'Stop using Chess discover-soul cards: preparation was '
                    'interrupted or has ended'
                )
                break
            cards = self._discover_soul_hand_cards()
            if not cards:
                break

            card = cards[0]
            logger.debug(
                'Use Chess discover-soul hand card: '
                f'text={card["text"]}, '
                f'similarity={card["similarity"]:.3f}, '
                f'position={card["position"]}'
            )
            self.device.click(
                x=card['position'][0],
                y=card['position'][1],
                control_name='CHESS_DISCOVER_SOUL_CARD',
            )

            use_deadline = time.monotonic() + self.DISCOVER_SOUL_UI_TIMEOUT
            while time.monotonic() < use_deadline:
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                self.screenshot()
                if not self._is_preparation_mode():
                    logger.debug(
                        'Stop using Chess discover-soul card: preparation was '
                        'interrupted or has ended'
                    )
                    return used
                if self.appear_then_click(self.I_USE_SOUL, interval=0.5):
                    break
            else:
                logger.warning(
                    'Chess discover-soul card selected, but use_soul '
                    'did not appear; keep the card and stop this pass'
                )
                break

            options = self._wait_for_discover_soul_choices()
            if not options:
                logger.warning(
                    'Chess discover-soul selection did not appear; '
                    'stop this pass'
                )
                break

            selected = random.choice(options)
            logger.debug(
                'Random Chess discover-soul option: '
                f'{selected.name}, available={[rule.name for rule in options]}'
            )
            self.click(selected)
            used += 1
            time.sleep(self.DISCOVER_SOUL_WAIT)
            close_deadline = time.monotonic() + self.DISCOVER_SOUL_UI_TIMEOUT
            while time.monotonic() < close_deadline:
                self.screenshot()
                if not any(
                    self.appear(rule)
                    for rule in (
                        self.I_SELECT_SOUL_1,
                        self.I_SELECT_SOUL_2,
                        self.I_SELECT_SOUL_3,
                    )
                ):
                    break
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
            else:
                logger.warning(
                    'Chess discover-soul selection remained open; '
                    'stop this pass'
                )
                break
        else:
            logger.warning(
                'Stop using Chess discover-soul cards at safety limit '
                f'{self.DISCOVER_SOUL_SAFETY_LIMIT}'
            )

        logger.debug(f'Chess discover-soul handling complete, used={used}')
        return used

    def equip_souls_from_hand(
        self,
        verified_names: set[str] | None = None,
    ) -> list[str]:
        """给已确认角色装备御魂；同一位置失败两次后轮换下一目标。"""
        if not self._is_preparation_mode():
            logger.debug(
                'Skip equipping Chess souls: preparation was interrupted or '
                'has ended'
            )
            return []
        # “发现御魂”会生成普通御魂，因此必须先全部处理，再扫描并装配
        # soul 文件夹中的御魂卡。
        self.discover_souls_from_hand()
        verified_names = set(verified_names or set())
        if not verified_names:
            logger.debug(
                'Keep Chess souls in hand: no shikigami position was '
                'confirmed on the board'
            )
            return []

        equipped = []
        repeated_attempts = {}
        for _ in range(self.SOUL_EQUIP_SAFETY_LIMIT):
            if not self._is_preparation_mode():
                logger.debug(
                    'Stop equipping Chess souls: '
                    'mode is no longer preparation'
                )
                break

            selected = None
            selected_target = None
            for candidate in self._soul_hand_cards():
                for target in self._soul_targets(
                    candidate['category'],
                    verified_names,
                ):
                    attempt_key = (
                        candidate['name'],
                        candidate['position'][0] // 20,
                        target[0],
                    )
                    if repeated_attempts.get(attempt_key, 0) >= 2:
                        continue
                    selected = candidate
                    selected_target = target
                    repeated_attempts[attempt_key] = (
                        repeated_attempts.get(attempt_key, 0) + 1
                    )
                    break
                if selected is not None:
                    break

            if selected is None or selected_target is None:
                break

            set_index, _ = selected_target
            logger.info(
                f'检测到{selected["text"]}'
                f'({self._soul_category_display(selected["category"])})，'
                f'移动到{set_index}号位'
            )
            if not self._equip_soul_card(
                source=selected['position'],
                set_index=set_index,
                operation_name=selected['name'].upper(),
            ):
                break
            time.sleep(self.SOUL_EQUIP_WAIT)
            self.screenshot()

            # 御魂仍在原横坐标附近表示本次装备没有成功。连续两次失败后，
            # 上面的目标枚举会自动跳过该式神，转向下一个同奇偶站位。
            remains = any(
                candidate['name'] == selected['name']
                and abs(
                    candidate['position'][0]
                    - selected['position'][0]
                ) <= 28
                for candidate in self._soul_hand_cards()
            )
            if remains:
                attempts = repeated_attempts[
                    (
                        selected['name'],
                        selected['position'][0] // 20,
                        set_index,
                    )
                ]
                logger.warning(
                    f'Chess soul equip not confirmed: '
                    f'{selected["text"]} -> set {set_index}, '
                    f'attempt={attempts}/2; '
                    + (
                        'try the same target once more'
                        if attempts < 2
                        else 'switch to next same-category target'
                    )
                )
                if attempts >= 2:
                    full_positions = set(
                        getattr(self, '_soul_full_positions', set())
                    )
                    full_positions.add(set_index)
                    self._soul_full_positions = full_positions
                    logger.debug(
                        f'Chess soul target set {set_index} marked full '
                        f'for current game; full_positions='
                        f'{sorted(full_positions)}'
                    )
                continue

            equipped.append(selected['name'])
            logger.debug(
                f'Chess soul equip confirmed: '
                f'{selected["text"]} -> set {set_index}'
            )
        else:
            logger.warning(
                'Stop equipping Chess souls at safety limit '
                f'{self.SOUL_EQUIP_SAFETY_LIMIT}'
            )

        logger.debug(f'Chess soul equipment complete, equipped={equipped}')
        return equipped

    def deploy_shikigami_from_hand(self) -> list[str]:
        """关闭商店后上阵手牌式神，并以当前阶数限制场上人数。"""
        # 场上人数 OCR 只有在商店完全收起后才可见。把约束放在上卡
        # 方法内部，避免其他调用入口绕过外层准备流程后无效拖卡。
        if not self._is_preparation_mode():
            logger.debug(
                'Skip Chess shikigami deployment: preparation was interrupted '
                'or has ended'
            )
            return []
        if not self._ensure_shop_closed():
            logger.warning(
                'Skip Chess shikigami deployment: shop could not be closed'
            )
            return []
        if self._is_shop_open():
            logger.warning(
                'Skip Chess shikigami deployment: shop is still visible '
                'after close confirmation'
            )
            return []

        deployed = []
        deployed_names = set(getattr(self, '_board_lineup_names', set()))
        failed_attempts = {}
        for _ in range(self.HAND_DEPLOY_SAFETY_LIMIT):
            if not self._is_preparation_mode():
                logger.debug(
                    'Stop deploying Chess hand cards: '
                    'mode is no longer preparation'
                )
                break
            if not self._ensure_shop_closed():
                logger.warning(
                    'Stop deploying Chess hand cards: shop reopened or '
                    'could not be confirmed closed before capacity check'
                )
                break

            capacity = self._read_lineup_capacity_status()
            if capacity is None:
                logger.warning(
                    'Stop deploying Chess hand cards: lineup capacity '
                    'could not be confirmed'
                )
                break
            count = capacity['count']
            lineup_full = capacity['full']
            candidate = self._find_best_shikigami_hand_card(
                excluded_names=(
                    deployed_names
                    | {
                        name
                        for name, attempts in failed_attempts.items()
                        if attempts >= 2
                    }
                ),
            )
            if candidate is None:
                logger.info(
                    'Stop deploying Chess hand cards: no deployable lineup '
                    'hand card candidate'
                )
                break

            logger.info(
                f'Chess deploy candidate: '
                f'{self._shikigami_display_name(candidate["name"])}, '
                f'score={candidate["score"]:.3f}, '
                f'position={candidate["position"]}'
            )
            set_index = self.shikigami_deploy_positions[candidate['name']]
            if lineup_full:
                recalled_set = self._recall_one_system_board_card(
                    preferred_set_index=set_index,
                )
                if recalled_set is None:
                    logger.warning(
                        'Stop deploying Chess hand cards: lineup is full and '
                        'no removable system-deployed card was found at '
                        f'{self.BOARD_RECALL_POSITIONS}'
                    )
                    break
                capacity = self._read_lineup_capacity_status()
                if capacity is None or capacity['full']:
                    logger.warning(
                        'Stop deploying Chess hand cards: system card recall '
                        f'at set {recalled_set} did not free lineup capacity'
                    )
                    break

                # 下阵卡进入手牌后会让整排手牌重新布局。下阵前保存的
                # candidate.position 已失效，必须基于新截图重新定位同名卡。
                self.screenshot()
                candidate_name = candidate['name']
                candidate = self._find_best_shikigami_hand_card(
                    excluded_names=(
                        set(self.shikigami_deploy_positions)
                        - {candidate_name}
                    ),
                )
                if candidate is None or candidate['name'] != candidate_name:
                    logger.warning(
                        'Stop current Chess deployment after system recall: '
                        f'{self._shikigami_display_name(candidate_name)} '
                        'could not be relocated in the reflowed hand'
                    )
                    failed_attempts[candidate_name] = (
                        failed_attempts.get(candidate_name, 0) + 1
                    )
                    continue
                set_index = self.shikigami_deploy_positions[candidate_name]
                logger.info(
                    f'Recall Chess system card at set {recalled_set}, then '
                    f'deploy {self._shikigami_display_name(candidate["name"])} '
                    f'to set {set_index}, refreshed_position='
                    f'{candidate["position"]}'
                )

            if not self.deploy_shikigami_hand_card(
                candidate['name'],
                candidate['position'],
            ):
                failed_attempts[candidate['name']] = (
                    failed_attempts.get(candidate['name'], 0) + 1
                )
                logger.warning(
                    f'Retry Chess shikigami deployment later: '
                    f'{candidate["name"]}, '
                    f'attempt={failed_attempts[candidate["name"]]}/2'
                )
                continue

            deployed.append(candidate['name'])
            deployed_names.add(candidate['name'])
            self._board_lineup_names = deployed_names
            player_positions = set(
                getattr(self, '_player_deployed_positions', set())
            )
            player_positions.add(set_index)
            self._player_deployed_positions = player_positions
            logger.debug(
                'Mark Chess player-deployed position: '
                f'set={set_index}, name={candidate["name"]}'
            )
            if candidate['name'] == self.HAKUZOSU_NAME:
                self.equip_hakuzosu_protect_after_deploy()
        else:
            logger.warning(
                'Stop deploying Chess hand cards at safety limit '
                f'{self.HAND_DEPLOY_SAFETY_LIMIT}'
            )

        logger.debug(f'Chess hand deployment complete, deployed={deployed}')
        return deployed

    def _hand_card_detections(self) -> list[dict]:
        """直接用式神/御魂素材定位已收录手牌，不依赖场上勾玉图。"""
        template_rules = [
            rule
            for _, rule in (
                list(self.shikigami_hand_rules)
                + list(self.soul_hand_rules)
            )
        ]
        template_rules.append(self.hakuzosu_protect_rule)
        candidates = []
        for rule in template_rules:
            matches = rule.match_all_any(
                self.device.image,
                roi=list(self.HAND_AREA),
                threshold=rule.threshold,
                nms_threshold=0.3,
                frame_id=self.device.image_frame_id,
            )
            for score, x, y, width, height in matches:
                candidates.append((score, x, y, width, height))

        # 多个素材可能在同一张卡上产生近邻命中；每个实际卡位只保留
        # 最高分结果。这里保留素材自身矩形，拖动时使用其中心即可。
        card_matches = []
        for candidate in sorted(candidates, key=lambda item: item[0], reverse=True):
            _, x, y, width, height = candidate
            center_x = x + width // 2
            center_y = y + height // 2
            if any(
                abs(center_x - (kept[1] + kept[3] // 2)) <= 28
                and abs(center_y - (kept[2] + kept[4] // 2)) <= 40
                for kept in card_matches
            ):
                continue
            card_matches.append(candidate)

        detections = []
        for score, x, y, width, height in sorted(
            card_matches,
            key=lambda item: item[1],
        ):
            if width <= 0 or height <= 0:
                continue
            detection = {
                'roi': (x, y, width, height),
                'score': score,
            }
            detections.append(detection)
            logger.debug(
                f'Chess hand card template detected: score={score:.3f}, '
                f'roi={detection["roi"]}'
            )
        if not detections:
            logger.debug('Chess hand card templates found no cards')
        return detections

    def _hand_card_rois(self) -> list[tuple[int, int, int, int]]:
        """兼容只需要卡框的分类流程。"""
        return [item['roi'] for item in self._hand_card_detections()]

    def _hand_card_identity_count(
        self,
        card_type: str,
        name: str | None,
    ) -> int:
        """统计手牌中指定素材的命中张数，用于确认出售确实生效。"""
        if card_type == 'shikigami' and name:
            rules = [
                rule
                for rule_name, rule in self.shikigami_hand_rules
                if rule_name == name
            ]
        elif card_type == 'soul' and name:
            rules = [
                rule
                for rule_name, rule in self.soul_hand_rules
                if rule_name == name
            ]
        else:
            return len(self._hand_card_detections())

        matches = []
        for rule in rules:
            matches.extend(rule.match_all_any(
                self.device.image,
                roi=list(self.HAND_AREA),
                threshold=rule.threshold,
                nms_threshold=0.3,
                frame_id=self.device.image_frame_id,
            ))

        centers = []
        for score, x, y, width, height in sorted(
            matches,
            key=lambda item: item[0],
            reverse=True,
        ):
            center = (x + width // 2, y + height // 2)
            if any(
                abs(center[0] - kept[0]) <= 28
                and abs(center[1] - kept[1]) <= 40
                for kept in centers
            ):
                continue
            centers.append(center)
        return len(centers)

    def cleanup_non_lineup_hand_cards(
        self,
        allowed_modes: tuple[str, ...] = ('战',),
        emergency: bool = False,
    ) -> list[tuple[int, int]]:
        """独立卖卡环节：循环出售纹章和非阵容卡，直到连续确认干净。"""
        if not emergency and self._is_early_round_layout():
            logger.debug(
                'Skip Chess hand cleanup: '
                'alternate layout means round 1-3'
            )
            return []

        sold = []
        failed_sale_attempts = {}
        clean_confirm_frames = 0
        strategy = self.get_lineup_strategy()
        logger.debug(
            'Chess hand cleanup lineup protection: '
            f'lineup={strategy["key"]}, '
            f'names={list(strategy["shikigami"].keys())}'
        )
        for cleanup_pass in range(1, self.HAND_CLEANUP_SAFETY_LIMIT + 1):
            self.close_shikigami_specifics_if_open()
            mode = self._read_chess_mode()
            if not self._is_hand_cleanup_allowed(allowed_modes):
                logger.debug(
                    'Stop cleaning Chess hand cards: '
                    f'mode={mode} is outside {allowed_modes}'
                )
                break

            # 纹章没有式神卡左上角的星级标志，无法进入下面的卡框分类。
            # 直接在 badge_area 中定位“纹章”文本，并从文字所在卡片拖出出售。
            badge_target = self._find_badge_hand_card()
            if badge_target is not None:
                logger.info(
                    'Sell Chess card: '
                    f'text={badge_target["text"]}, '
                    f'position={badge_target["position"]}'
                )
                self.sell_hand_card(badge_target['position'])
                sold.append(badge_target['position'])
                clean_confirm_frames = 0
                time.sleep(self.HAND_CLEANUP_REFLOW_WAIT)
                self.screenshot()
                continue

            # 御魂图片可能与星级卡框同时命中。先独立识别御魂，避免
            # classify_hand_card 的固定尺寸模板漏检后将它当作 unknown 出售。
            soul_cards = self._soul_hand_cards()
            discover_soul_cards = self._discover_soul_hand_cards()
            sell_target = None
            for card_roi in self._hand_card_rois():
                card_x, _, card_width, _ = card_roi
                discover_soul = next((
                    item
                    for item in discover_soul_cards
                    if (
                        card_x - 8
                        <= item['position'][0]
                        <= card_x + card_width + 8
                    )
                ), None)
                if discover_soul is not None:
                    logger.debug(
                        'Keep unused Chess discover-soul card during cleanup: '
                        f'text={discover_soul["text"]}, '
                        f'position={discover_soul["position"]}'
                    )
                    continue
                soul = self._soul_match_in_card(card_roi, soul_cards)
                if soul is not None:
                    logger.debug(
                        'Keep Chess soul hand card during cleanup: '
                        f'name={soul["text"]}, score={soul["score"]:.3f}, '
                        f'position={soul["position"]}'
                    )
                    continue
                protect = self._hakuzosu_protect_match_in_card(card_roi)
                if protect is not None:
                    logger.debug(
                        'Keep Chess Hakuzosu protect card during cleanup: '
                        f'score={protect["score"]:.3f}, '
                        f'position={protect["position"]}'
                    )
                    continue
                result = self.classify_hand_card(card_roi)
                keep = (
                    result['type'] == 'soul'
                    or (
                        result['type'] == 'shikigami'
                        and result['name'] in self.shikigami_deploy_positions
                    )
                )
                if keep:
                    continue

                if result['type'] == 'unknown':
                    # 低阈值阵容保护只用于无法分类的卡。已经被完整素材库
                    # 明确识别为非阵容式神的卡不能再被 0.58 的模糊匹配
                    # 覆盖，否则会出现日志列出杂卡但卖卡阶段始终保留。
                    possible = self._possible_lineup_shikigami(card_roi)
                    if possible is not None:
                        logger.debug(
                            'Protect possible lineup Chess hand card from sale: '
                            f'name={possible["name"]}, '
                            f'score={possible["score"]:.3f}'
                        )
                        continue
                    result = self._confirm_unknown_hand_card(card_roi)
                    if result is None:
                        continue
                sale_key = (result['type'], result['name'])
                if failed_sale_attempts.get(sale_key, 0) >= 2:
                    logger.debug(
                        'Skip repeatedly failed Chess sale target in this '
                        f'cleanup pass: type={result["type"]}, '
                        f'name={result["name"]}'
                    )
                    continue
                sell_target = result
                break
            if sell_target is None:
                clean_confirm_frames += 1
                if (
                    clean_confirm_frames
                    >= self.HAND_CLEANUP_CLEAN_CONFIRM_FRAMES
                ):
                    logger.debug(
                        'Chess hand cleanup confirmed clean: '
                        f'frames={clean_confirm_frames}'
                    )
                    break
                logger.debug(
                    'No sellable Chess hand card in current scan, '
                    'wait for layout and verify again: '
                    f'frame={clean_confirm_frames}/'
                    f'{self.HAND_CLEANUP_CLEAN_CONFIRM_FRAMES}'
                )
                time.sleep(self.HAND_CLEANUP_REFLOW_WAIT)
                self.screenshot()
                continue

            logger.info(
                f'Sell Chess card: '
                f'type={sell_target["type"]}, '
                f'name={self._shikigami_display_name(sell_target["name"])}, '
                f'position={sell_target["position"]}'
            )
            sale_key = (sell_target['type'], sell_target['name'])
            count_before = self._hand_card_identity_count(*sale_key)
            self.sell_hand_card(sell_target['position'])
            time.sleep(self.HAND_CLEANUP_REFLOW_WAIT)
            self.screenshot()
            self.close_shikigami_specifics_if_open()
            self.screenshot()
            count_after = self._hand_card_identity_count(*sale_key)
            if count_after < count_before:
                sold.append(sell_target['position'])
                failed_sale_attempts.pop(sale_key, None)
                clean_confirm_frames = 0
                logger.info(
                    'Chess card sale confirmed: '
                    f'type={sell_target["type"]}, '
                    f'name={self._shikigami_display_name(sell_target["name"])}, '
                    f'count={count_before}->{count_after}'
                )
                continue

            failed_sale_attempts[sale_key] = (
                failed_sale_attempts.get(sale_key, 0) + 1
            )
            clean_confirm_frames = 0
            logger.warning(
                'Chess card sale not confirmed; do not register as sold: '
                f'type={sell_target["type"]}, '
                f'name={self._shikigami_display_name(sell_target["name"])}, '
                f'count={count_before}->{count_after}, '
                f'attempt={failed_sale_attempts[sale_key]}/2'
            )
        else:
            logger.warning(
                'Stop cleaning Chess hand cards at safety limit '
                f'{self.HAND_CLEANUP_SAFETY_LIMIT}'
            )

        logger.debug(f'Chess non-lineup hand cleanup complete, sold={sold}')
        return sold

    def _is_hand_cleanup_allowed(
        self,
        allowed_modes: tuple[str, ...] = ('战',),
    ) -> bool:
        """卖卡只在调用方指定阶段执行，阶段变化后立刻停止。"""
        return self._read_chess_mode() in allowed_modes

    def _free_one_hand_slot_for_purchase(self) -> dict | None:
        """手牌满时直接出售最右侧卡牌，为本次购买腾出一格。"""

        mode = self._read_chess_mode()
        if mode not in ('备', '战'):
            logger.warning(
                f'Cannot run emergency Chess hand cleanup in mode={mode}'
            )
            return None

        result = self.sell_rightmost_hand_card()

        if result is None:
            logger.warning('No safe Chess hand card is available to free a slot')
            return None

        # 本方法只会在购买失败的恢复路径调用；清理后必须恢复“商店开”
        # 这一购买前置状态，至于卖卡过程本身不主动切换商店。
        if not self._ensure_shop_open():
            logger.warning(
                'Emergency Chess hand cleanup succeeded, but shop could not '
                'be reopened'
            )
            return None
        self.screenshot()
        return result

    def _find_badge_hand_card(self) -> dict | None:
        """返回 badge_area 内最左侧“纹章”文字的屏幕坐标。"""
        results = self.O_BADGE_AREA.detect_and_ocr(self.device.image)
        matches = []
        roi_x, roi_y = self.O_BADGE_AREA.roi[:2]
        for result in results:
            text = self._normalize_ocr_text(result.ocr_text)
            if '纹章' not in text:
                continue

            # detect_and_ocr 返回的是相对于 OCR 裁剪区的四点框。
            points = result.box
            left = min(int(point[0]) for point in points)
            right = max(int(point[0]) for point in points)
            top = min(int(point[1]) for point in points)
            bottom = max(int(point[1]) for point in points)
            position = (
                roi_x + (left + right) // 2,
                roi_y + (top + bottom) // 2,
            )
            matches.append({
                'text': text,
                'position': position,
                'score': float(result.score),
            })

        if not matches:
            return None
        matches.sort(key=lambda item: item['position'][0])
        return matches[0]

    def _recall_one_system_board_card(
        self,
        preferred_set_index: int | None = None,
    ) -> int | None:
        """满员上卡时只下阵一个系统卡位，成功则返回对应站位。"""
        if not self._is_preparation_mode():
            return None
        if not self._ensure_shop_closed():
            logger.warning(
                'Cannot free Chess lineup slot: shop could not be closed'
            )
            return None

        player_positions = set(
            getattr(self, '_player_deployed_positions', set())
        )
        positions = list(self.BOARD_RECALL_POSITIONS)
        if preferred_set_index in positions:
            positions.remove(preferred_set_index)
            positions.insert(0, preferred_set_index)

        hand_target = self._rule_center(
            RuleClick(
                roi_front=self.HAND_AREA,
                roi_back=self.HAND_AREA,
                name='chess_hand_area',
            )
        )
        time.sleep(self.BOARD_RECALL_SETTLE_WAIT)
        for set_index in positions:
            if set_index in player_positions:
                continue
            if not self._board_set_has_shikigami(set_index):
                continue

            source = self._set_position(set_index)
            for attempt, drag_source in enumerate(
                (source, (source[0], source[1] - 14)),
                start=1,
            ):
                Press_and_Drag(
                    self.device,
                    p1=drag_source,
                    p2=hand_target,
                    hold_duration=0.6 if attempt == 2 else 0.5,
                    point_random=(-2, -2, 2, 2),
                    swipe_duration=0.5,
                    name=(
                        f'CHESS_FREE_SYSTEM_SET_{set_index}'
                        f'_ATTEMPT_{attempt}'
                    ),
                )
                time.sleep(self.BOARD_RECALL_SETTLE_WAIT)
                self.screenshot()
                if not self._board_set_has_shikigami(set_index):
                    tracked_names = set(
                        getattr(self, '_board_lineup_names', set())
                    )
                    self._board_lineup_names = {
                        name
                        for name in tracked_names
                        if self.shikigami_deploy_positions.get(name)
                        != set_index
                    }
                    logger.debug(
                        f'Chess system card recalled for deployment: '
                        f'set={set_index}, attempt={attempt}'
                    )
                    return set_index
        return None

    def recall_all_board_cards(self) -> bool:
        """按系统自动上阵顺序，快速回收棋盘右侧四个候选位置。"""
        if not self._ensure_shop_closed():
            logger.warning(
                'Abort Chess board recall: shop could not be closed'
            )
            return False
        hand_target = self._rule_center(
            RuleClick(
                roi_front=self.HAND_AREA,
                roi_back=self.HAND_AREA,
                name='chess_hand_area',
            )
        )

        count = self._read_shikigami_count()
        if count is not None and count['current'] == 0:
            logger.debug('Chess board is already empty; skip recall')
            self._board_lineup_names = set()
            self._player_deployed_positions = set()
            return True

        tracked_names = set(getattr(self, '_board_lineup_names', set()))
        player_positions = set(
            getattr(self, '_player_deployed_positions', set())
        )
        recall_positions = tuple(
            set_index
            for set_index in self.BOARD_RECALL_POSITIONS
            if set_index not in player_positions
        )
        protected_recall_positions = sorted(
            set(self.BOARD_RECALL_POSITIONS) & player_positions
        )
        if protected_recall_positions:
            logger.debug(
                'Keep Chess system-set positions during recall: '
                f'they were deployed by script, positions='
                f'{protected_recall_positions}'
            )
        logger.debug(
            f'Chess board recall order: {recall_positions}, '
            f'current_count={None if count is None else count["current"]}'
        )
        if not self._is_preparation_mode():
            logger.debug(
                'Stop recalling Chess board cards: '
                'mode is no longer preparation'
            )
            return False

        # 商店图层消失后，棋盘的触控层仍有一小段收起动画。日志显示此前
        # 11 号位在关闭判定后立即拖动，手势已下发但没有成功下阵。
        time.sleep(self.BOARD_RECALL_SETTLE_WAIT)

        # 除 11 号位的针对性确认外，其余候选格连续拖完后再统一截图，
        # 避免每个空位都产生一次截图等待。
        for set_index in recall_positions:
            if not self._board_set_has_shikigami(set_index):
                logger.debug(
                    f'Skip Chess recall set {set_index}: '
                    'jade marker is not detected'
                )
                continue
            source = self._set_position(set_index)
            Press_and_Drag(
                self.device,
                p1=source,
                p2=hand_target,
                hold_duration=0.5,
                point_random=(-3, -3, 3, 3),
                swipe_duration=0.45,
                name=f'CHESS_RECALL_SET_{set_index}',
            )
            time.sleep(self.BOARD_RECALL_INTERVAL)

            # 11 号位是系统自动上阵的第一顺位，也是商店关闭后的第一条
            # 棋盘手势。单独确认它是否生效；失败时稍微上移到模型主体重拖。
            if set_index == 11 and count is not None:
                self.screenshot()
                set_11_count = self._read_shikigami_count()
                if (
                    set_11_count is not None
                    and set_11_count['current'] >= count['current']
                ):
                    retry_source = (source[0], source[1] - 14)
                    logger.warning(
                        'Chess set 11 recall did not reduce lineup count; '
                        f'retry from {retry_source}'
                    )
                    time.sleep(self.BOARD_RECALL_RETRY_WAIT)
                    Press_and_Drag(
                        self.device,
                        p1=retry_source,
                        p2=hand_target,
                        hold_duration=0.6,
                        point_random=(-2, -2, 2, 2),
                        swipe_duration=0.5,
                        name='CHESS_RECALL_SET_11_RETRY',
                    )
                    time.sleep(self.BOARD_RECALL_INTERVAL)
                    self.screenshot()
                    set_11_count = self._read_shikigami_count()
                    logger.debug(
                        'Chess set 11 recall retry result: '
                        f'{None if set_11_count is None else set_11_count["current"]}'
                        f'/{None if set_11_count is None else set_11_count["total"]}'
                    )
                if set_11_count is not None:
                    count = set_11_count

        self.screenshot()
        count = self._read_shikigami_count()
        # 只清除脚本记录中确实位于本次回收区域的式神。若 9 号位是脚本
        # 上阵的卡，或场上仍有 1-8 号位的式神，则保留对应记录。
        self._board_lineup_names = {
            name
            for name in tracked_names
            if self.shikigami_deploy_positions.get(name)
            not in recall_positions
        }
        self._player_deployed_positions = (
            player_positions - set(recall_positions)
        )
        if count is not None and count['current'] == 0:
            self._board_lineup_names = set()
            self._player_deployed_positions = set()
        if count is None:
            logger.debug('Chess board recall completed; count is unavailable')
        else:
            logger.debug(
                'Chess board recall completed at positions '
                f'{self.BOARD_RECALL_POSITIONS}: '
                f'{count["current"]}/{count["total"]}'
            )
        return True

    def select_random_buff(self) -> bool:
        """随机锁定一个 Buff 选项并持续点击，直到选项面板关闭。

        Buff 优先级表完成前使用该挂机保底逻辑；本方法不使用
        三个选项底部的刷新按钮。
        """
        if not self.appear(self.I_SELECT_BUFF):
            return False

        options = (
            self.C_BUFF_OPTION_1,
            self.C_BUFF_OPTION_2,
            self.C_BUFF_OPTION_3,
        )
        selected = random.choice(options)
        deadline = time.monotonic() + self.BUFF_SELECT_TIMEOUT
        attempts = 0
        logger.debug(
            f'Random buff option locked: {selected.name}; '
            'retry until selection panel closes'
        )
        while time.monotonic() < deadline:
            self.screenshot()
            if not self.appear(self.I_SELECT_BUFF):
                logger.debug(
                    'Chess buff selection confirmed: '
                    f'option={selected.name}, attempts={attempts}'
                )
                return True
            attempts += 1
            logger.debug(
                f'Click Chess buff option {selected.name}: '
                f'attempt={attempts}'
            )
            self.click(selected)
            time.sleep(self.BUFF_SELECT_RETRY_INTERVAL)

        self.screenshot()
        if not self.appear(self.I_SELECT_BUFF):
            logger.debug(
                'Chess buff selection confirmed at timeout boundary: '
                f'option={selected.name}, attempts={attempts}'
            )
            return True
        logger.warning(
            'Chess buff selection did not close after repeated clicks: '
            f'option={selected.name}, attempts={attempts}'
        )
        return False

    @staticmethod
    def _normalize_ocr_text(value) -> str:
        if value is None:
            return ''
        return ''.join(str(value).split())

    @classmethod
    def _fuzzy_text_match(
        cls,
        expected,
        current,
    ) -> tuple[bool, float, float]:
        """Chess 内部 OCR 编辑距离兜底，避免修改公共 RuleOcr。"""
        expected = cls._normalize_ocr_text(expected)
        current = cls._normalize_ocr_text(current)
        threshold = 0.75 if len(expected) <= 2 else 0.65
        if not expected or not current:
            return False, 0.0, threshold
        if expected == current:
            return True, 1.0, threshold

        # 仅保留较短字符串长度的一行动态规划状态。
        if len(expected) < len(current):
            expected, current = current, expected
        previous = list(range(len(current) + 1))
        for expected_index, expected_char in enumerate(expected, start=1):
            row = [expected_index]
            for current_index, current_char in enumerate(current, start=1):
                row.append(min(
                    row[current_index - 1] + 1,
                    previous[current_index] + 1,
                    previous[current_index - 1]
                    + (expected_char != current_char),
                ))
            previous = row
        similarity = 1.0 - previous[-1] / max(len(expected), len(current))
        return similarity >= threshold, similarity, threshold

    def _parse_round_number(self, ocr_rule) -> tuple[int | None, str]:
        raw = self._normalize_ocr_text(ocr_rule.ocr(self.device.image))
        matched = re.search(r'(\d+)(?=回)', raw)
        if matched is None:
            matched = re.search(r'\d+', raw)
        if matched is None:
            return None, raw
        value = int(matched.group(0))
        return (value if value > 0 else None), raw

    def _read_primary_round_layout(self) -> tuple[str, bool]:
        """以主 chess_mode 是否读到数字判断是否启用前三回合布局。"""
        frame_id = getattr(self.device, 'image_frame_id', None)
        cache = getattr(self, '_primary_round_layout_cache', None)
        if frame_id is not None and cache is not None and cache[0] == frame_id:
            return cache[1]

        raw = self._normalize_ocr_text(
            self.O_CHESS_MODE.ocr(self.device.image)
        )
        if raw:
            use_alternate_layout = bool(re.search(r'\d', raw))
            self._last_alternate_round_layout = use_alternate_layout
        else:
            # 动画帧偶发空识别时沿用上一帧，避免在两套区域间抖动。
            use_alternate_layout = getattr(
                self,
                '_last_alternate_round_layout',
                False,
            )
        result = raw, use_alternate_layout
        if frame_id is not None:
            self._primary_round_layout_cache = frame_id, result
        return result

    def _is_early_round_layout(self) -> bool:
        """第二套 round/mode 布局即前三回合，此阶段禁止任何卖卡。"""
        _, use_alternate_layout = self._read_primary_round_layout()
        return use_alternate_layout

    def _read_round_number(self) -> int | None:
        """主 chess_mode 读到数字时使用前三回合专用 round_2。"""
        mode_raw, use_alternate_layout = self._read_primary_round_layout()
        ocr_rule = self.O_ROUND_2 if use_alternate_layout else self.O_ROUND
        value, round_raw = self._parse_round_number(ocr_rule)
        if use_alternate_layout:
            logger.debug(
                f'Chess mode primary is numeric [{mode_raw}]; '
                f'use round_2 [{round_raw}] -> {value}'
            )
        return value

    def _read_chess_mode(self) -> str | None:
        """返回模式文字；只有 OCR 真正无文本时才返回 None。"""
        primary_raw, use_alternate_layout = self._read_primary_round_layout()
        raw = (
            self._normalize_ocr_text(
                self.O_CHESS_MODE_2.ocr(self.device.image)
            )
            if use_alternate_layout
            else primary_raw
        )
        for mode in ('备', '战', '鬼'):
            if mode in raw:
                return mode
        # “待”等过渡文字虽然不触发阶段动作，但必须保留为有文本状态，
        # 不能和真正的 OCR 空结果混为一谈，否则会误累计结算空帧。
        return raw or None

    def _board_set_has_shikigami(self, set_index: int) -> bool:
        """在对应站位中匹配三种头顶勾玉，任一命中即视为有人。"""
        x, y, width, height = self._set_jade_area(set_index)
        image_height, image_width = self.device.image.shape[:2]
        if (
            x < 0
            or y < 0
            or x >= image_width
            or y >= image_height
        ):
            logger.warning(
                f'Chess set jade area is outside screenshot: '
                f'set={set_index}, area={(x, y, width, height)}'
            )
            return False
        width = min(width, image_width - x)
        height = min(height, image_height - y)
        if width <= 0 or height <= 0:
            logger.warning(
                f'Chess set jade area is empty after clipping: '
                f'set={set_index}, area={(x, y, width, height)}'
            )
            return False

        roi = [x, y, width, height]
        return any(
            bool(rule.match_all_any(
                self.device.image,
                roi=roi,
                threshold=self.BOARD_OCCUPANCY_TEMPLATE_THRESHOLD,
                nms_threshold=0.3,
                frame_id=self.device.image_frame_id,
            ))
            for rule in self.board_occupancy_rules
        )

    def _read_board_position_count(self) -> dict:
        """统计 12 个站位勾玉区域中检测到图标的位置数量。"""
        occupied_positions = [
            set_index
            for set_index in range(1, 13)
            if self._board_set_has_shikigami(set_index)
        ]
        count = len(occupied_positions)
        raw = ','.join(str(index) for index in occupied_positions)
        logger.debug(
            'Chess board position count by jade: '
            f'{count}/12, occupied={occupied_positions}'
        )
        return {
            'current': count,
            'total': 12,
            'raw': raw,
            'occupied_positions': occupied_positions,
        }

    def _read_shikigami_count(self) -> dict | None:
        """读取场上人数：统计 12 个站位勾玉区域是否有式神。"""
        return self._read_board_position_count()

    def _read_lineup_capacity_status(self) -> dict | None:
        """以场上人数为当前值、当前阶数为最大上阵人数。"""
        count = self._read_shikigami_count()
        level = self._read_level()
        if count is None or level is None:
            logger.warning(
                'Chess lineup capacity unavailable: '
                f'count={count}, level={level}'
            )
            return None

        current = count['current']
        full = current >= level
        logger.debug(
            'Chess lineup capacity by level: '
            f'current={current}, capacity={level}, full={full}, '
            f'count_ocr=[{count["raw"]}]'
        )
        return {
            'current': current,
            'capacity': level,
            'full': full,
            'count': count,
        }

    def _read_round_resources(self, round_no: int, mode: str | None) -> dict:
        """记录一个新回合需要检查的五项信息。"""
        snapshot = {
            'gold': self.O_GOLD.ocr(self.device.image),
            'round': round_no,
            'level': self._read_level(),
            'chess_mode': mode or self._read_chess_mode(),
        }
        logger.debug(
            'Chess round snapshot: '
            f'round={snapshot["round"]}, mode={snapshot["chess_mode"]}, '
            f'level={snapshot["level"]}, gold={snapshot["gold"]}'
        )
        logger.info(
            'Chess round update: '
            f'round={snapshot["round"]}, mode={snapshot["chess_mode"]}, '
            f'gold={snapshot["gold"]}, level={snapshot["level"]}, '
            f'hand_shikigami={self._hand_shikigami_summary()}'
        )
        return snapshot

    def _read_level(self) -> int | None:
        """读取“一阶”至“九阶”，同时兼容阿拉伯数字显示。"""
        raw = self._normalize_ocr_text(self.O_LEVEL.ocr(self.device.image))
        digit = re.search(r'([1-9])', raw)
        if digit is not None:
            level = int(digit.group(1))
            logger.debug(f'Chess level: [{raw}] -> {level}')
            return level

        chinese_digits = {
            '一': 1,
            '二': 2,
            '三': 3,
            '四': 4,
            '五': 5,
            '六': 6,
            '七': 7,
            '八': 8,
            '九': 9,
        }
        for character, level in chinese_digits.items():
            if character in raw:
                logger.debug(f'Chess level: [{raw}] -> {level}')
                return level

        logger.warning(f'Chess level OCR invalid: [{raw}]')
        return None

    def _read_remaining_time(self) -> int | None:
        """读取第一套回合布局的剩余时间；前三回合禁止调用该 OCR。"""
        if self._is_early_round_layout():
            return None
        raw = self._normalize_ocr_text(
            self.O_NOW_TIME.ocr(self.device.image)
        )
        matched = re.search(r'\d+', raw)
        if matched is None:
            logger.warning(f'Chess remaining time OCR invalid: [{raw}]')
            return None
        remaining = int(matched.group(0))
        logger.debug(f'Chess remaining time: [{raw}] -> {remaining}')
        return remaining

    def _read_alive_players(self) -> int | None:
        """以 health_1-8 中仍含数字的最大编号作为当前存活人数。"""
        detected = {}
        for index in range(1, 9):
            rule = getattr(self, f'O_HEALTH_{index}')
            raw = self._normalize_ocr_text(rule.ocr(self.device.image))
            if re.search(r'\d', raw):
                detected[index] = raw

        if not detected:
            logger.warning('Chess alive-player OCR found no health value')
            return None
        alive = max(detected)
        logger.debug(
            'Chess alive players by health OCR: '
            f'alive={alive}, detected={detected}'
        )
        return alive

    def _early_exit_by_alive_players_reached(self) -> bool:
        """连续确认存活人数达到阈值，避免单帧 OCR 漏识别导致误退。"""
        threshold = getattr(self, '_remaining_players_exit', 0)
        if (
            not getattr(self, '_early_exit_enabled', False)
            or threshold <= 0
        ):
            return False

        alive = self._read_alive_players()
        if alive is None:
            self._alive_players_candidate = None
            self._alive_players_confirmed = 0
            return False

        if alive == getattr(self, '_alive_players_candidate', None):
            self._alive_players_confirmed += 1
        else:
            self._alive_players_candidate = alive
            self._alive_players_confirmed = 1

        logger.debug(
            'Chess early-exit player check: '
            f'alive={alive}, threshold={threshold}, '
            f'confirmed={self._alive_players_confirmed}/'
            f'{self.ALIVE_PLAYERS_CONFIRM_FRAMES}'
        )
        return (
            alive <= threshold
            and self._alive_players_confirmed
            >= self.ALIVE_PLAYERS_CONFIRM_FRAMES
        )

    def _try_last_seconds_deploy(self) -> bool:
        """第一套布局备阶段倒计时不超过 10 秒时，空闲补做一次上阵。

        Returns:
            bool: 是否已经进入倒计时补位判定。OCR 未到阈值或不可用时
                返回 False，允许后续截图继续检查；一旦到达阈值，无论
                阵容是否已满都返回 True，确保每回目至多触发一次。
        """
        if self._is_early_round_layout():
            return False
        remaining = self._read_remaining_time()
        if remaining is None or remaining > 10:
            return False

        logger.debug(
            'Chess last-seconds lineup check: '
            f'remaining={remaining}'
        )
        if self._read_chess_mode() != '备':
            logger.debug('Skip last-seconds deploy: mode is no longer 备')
            return True
        if not self._ensure_shop_closed():
            logger.warning(
                'Skip last-seconds deploy: shop could not be closed'
            )
            return True

        self.screenshot()
        if self._is_early_round_layout() or not self._is_preparation_mode():
            logger.debug(
                'Skip last-seconds deploy: preparation/layout changed '
                'while closing shop'
            )
            return True

        capacity = self._read_lineup_capacity_status()
        if capacity is None:
            logger.warning(
                'Skip last-seconds deploy: lineup capacity is unavailable'
            )
            return True
        if capacity['full']:
            logger.debug(
                'Skip last-seconds deploy: lineup is already full '
                f'({capacity["current"]}/{capacity["capacity"]})'
            )
            return True

        logger.debug(
            'Run last-seconds deploy: '
            f'{capacity["current"]}/{capacity["capacity"]}'
        )
        deployed = self.deploy_shikigami_from_hand()
        logger.debug(
            'Chess last-seconds deploy complete: '
            f'deployed={deployed}'
        )
        return True

    def _shop_slots(self) -> list[tuple[int, RuleClick]]:
        """返回商店五个卡面点击区；编号按原资源定义从右向左。"""
        return [
            (
                index,
                getattr(self, f'C_SHIKIGAMI_{index}'),
            )
            for index in range(1, 6)
        ]

    def _is_shop_open(self) -> bool:
        """使用刷新按钮判断商店是否展开；禁止在此读取价格 OCR。

        ``check_market`` 是开店确认的辅助标志，不能用于“商店仍展开”
        的通用判断，否则商店关闭后仍可能命中该图标，导致上卡阶段被
        误判为商店未关闭。
        """
        visible = self._shop_refresh_marker_visible()
        if visible:
            self._shop_assumed_open = True
            return True
        # 战斗技能会遮住右侧刷新按钮。经济续跑期间以脚本自己记录的
        # 商店状态为准，避免因“看不见刷新”而反复开关商店。
        return bool(
            getattr(self, '_economy_battle_mode', False)
            and getattr(self, '_shop_assumed_open', False)
        )

    def _shop_refresh_marker_visible(self) -> bool:
        """刷新/金币不足刷新任一出现，表示商店明确展开。"""
        return self.appear(self.I_REFRESH) or self.appear(self.I_REFRESH_NOT_GOLD)

    def _shop_open_confirm_marker_visible(self) -> bool:
        """开店确认：非战阶段只看 refresh；战阶段追加 check_market。"""
        if self._shop_refresh_marker_visible():
            return True
        return self._read_chess_mode() == '战' and self.appear(
            self.I_CHECK_MARKET
        )

    def _is_preparation_mode(self) -> bool:
        """只有无 Buff 弹窗的“备”可继续操作；弹窗出现立即中断。"""
        if self._read_chess_mode() != '备':
            return False
        if self.appear(self.I_SELECT_BUFF):
            logger.debug(
                'Interrupt Chess preparation immediately: buff selection '
                'panel detected'
            )
            return False
        return True

    def _is_purchase_allowed(self) -> bool:
        """商店动作遇到“鬼”必停；其余阶段由外层状态机调度。"""
        mode = self._read_chess_mode()
        if mode == '鬼':
            return False
        return True

    def _read_shop_gold(self) -> int | None:
        """读取当前金币；OCR 异常时返回 None，避免误停购买流程。"""
        raw = self._normalize_ocr_text(self.O_GOLD.ocr(self.device.image))
        matched = re.search(r'\d+', raw)
        if matched is None:
            logger.warning(f'Chess gold OCR invalid: [{raw}]')
            return None
        return int(matched.group(0))

    @staticmethod
    def _parse_coin_text(raw_text: str) -> dict | None:
        """解析鼬乐币 m/600，并恢复斜杠丢失或误识别为 1/I 的结果。"""
        raw = ''.join(str(raw_text or '').split())
        if not raw:
            return None

        # 标准斜杠以及被识别为 I/l/竖线的分隔符。
        explicit = re.search(r'(\d{1,3})[/／Iil|](600)$', raw)
        recovered = False
        if explicit is not None:
            current = int(explicit.group(1))
            recovered = '/' not in raw and '／' not in raw
        else:
            digits = ''.join(re.findall(r'\d', raw))
            if not digits.endswith('600'):
                return None
            prefix = digits[:-3]
            # 3441600 表示 344/600，其中额外的 1 是斜杠误识别。
            if len(prefix) == 4 and prefix.endswith('1'):
                prefix = prefix[:-1]
                recovered = True
            elif prefix:
                recovered = True
            if not prefix:
                return None
            current = int(prefix)

        if not 0 <= current <= 600:
            return None
        return {
            'current': current,
            'total': 600,
            'raw': raw,
            'recovered': recovered,
        }

    def _read_coin(self) -> dict | None:
        """读取棋局大厅鼬乐币，OCR 无效时返回 None。"""
        raw = self._normalize_ocr_text(self.O_COIN.ocr(self.device.image))
        coin = self._parse_coin_text(raw)
        if coin is None:
            logger.warning(f'Chess coin OCR invalid: [{raw}]')
            return None
        if coin['recovered']:
            logger.debug(
                f'Chess coin OCR recovered: [{raw}] -> '
                f'{coin["current"]}/{coin["total"]}'
            )
        else:
            logger.debug(
                f'Chess coin: {coin["current"]}/{coin["total"]}'
            )
        return coin

    def _coin_is_full(self) -> bool:
        """最多复查三帧，仅 600/600 才视为鼬乐币已满。"""
        for attempt in range(1, 4):
            coin = self._read_coin()
            if coin is not None:
                full = coin['current'] == coin['total'] == 600
                if full:
                    logger.info('Chess coin is full: 600/600')
                return full
            if attempt < 3:
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                self.screenshot()
        return False

    def _can_afford_shop_shikigami(self, slot_index: int) -> bool:
        """判断当前金币是否足以购买指定商店格，OCR 无效时保守跳过。"""
        if slot_index not in range(1, 6):
            logger.warning(f'Invalid Chess shop slot index: {slot_index}')
            return False

        gold = self._read_shop_gold()
        price_rule = getattr(self, f'O_SHIKIGAMI_GOLD_{slot_index}')
        raw_price = self._normalize_ocr_text(
            price_rule.ocr(self.device.image)
        )
        matched = re.search(r'\d+', raw_price)
        if gold is None or matched is None:
            logger.warning(
                'Skip Chess shop purchase because affordability OCR is '
                f'unavailable: slot={slot_index}, gold={gold}, '
                f'price_raw=[{raw_price}]'
            )
            return False

        price = int(matched.group(0))
        affordable = gold >= price
        logger.debug(
            'Chess shop affordability: '
            f'slot={slot_index}, gold={gold}, price={price}, '
            f'affordable={affordable}'
        )
        return affordable

    def _ensure_shop_open(self) -> bool:
        """必要时点击商店图标，并等待刷新按钮确认商店已经展开。"""
        if not self._is_purchase_allowed():
            logger.debug('Stop opening Chess shop: Hyakki mode detected')
            return False
        if getattr(self, '_economy_battle_mode', False):
            return self._ensure_battle_economy_shop_open()
        if self._is_shop_open():
            logger.debug('Chess shop is already open')
            self._shop_assumed_open = True
            return True

        logger.debug('Chess shop is closed, click market to open it')
        # C_MARKET 是跨回合反复使用的合法开关；每次新状态转换单独计数。
        self.device.click_record_remove(self.I_MARKET)
        deadline = time.monotonic() + self.SHOP_OPEN_TIMEOUT
        attempts = 0
        while time.monotonic() < deadline:
            if not self._is_purchase_allowed():
                logger.debug('Stop opening Chess shop: Hyakki mode detected')
                return False
            attempts += 1
            self.click(self.I_MARKET)
            attempt_deadline = min(
                deadline,
                time.monotonic() + self.SHOP_OPEN_ATTEMPT_WAIT,
            )
            while time.monotonic() < attempt_deadline:
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                self.screenshot()
                if not self._is_purchase_allowed():
                    logger.debug('Stop opening Chess shop: Hyakki mode detected')
                    return False
                if self._shop_open_confirm_marker_visible():
                    logger.debug(
                        f'Chess shop opened successfully, attempts={attempts}'
                    )
                    self._shop_assumed_open = True
                    return True

        logger.warning('Chess shop failed to open before timeout')
        return False

    def _ensure_battle_economy_shop_open(self) -> bool:
        """战斗中只开一次商店，不以可能被技能遮挡的刷新图标反复切换。"""
        if self._read_chess_mode() != '战':
            logger.debug('Stop battle economy shop open: mode is no longer 战')
            return False
        if getattr(self, '_shop_assumed_open', False):
            logger.debug('Chess battle economy shop is assumed open')
            return True
        if self._shop_open_confirm_marker_visible():
            self._shop_assumed_open = True
            logger.debug('Chess battle economy shop is visibly open')
            return True

        logger.debug(
            'Open Chess shop once for battle economy; subsequent state is '
            'tracked internally'
        )
        self.device.click_record_remove(self.I_MARKET)
        self.click(self.I_MARKET)
        time.sleep(self.SHOP_OPEN_ATTEMPT_WAIT)
        self.screenshot()
        if self._read_chess_mode() != '战':
            logger.debug('Battle mode ended while opening economy shop')
            return False
        self._shop_assumed_open = True
        return True

    def _ensure_shop_closed(
        self,
        allowed_modes: tuple[str, ...] = ('备',),
    ) -> bool:
        """在指定模式内关闭商店；上卡默认仅允许“备”。"""
        if self._read_chess_mode() not in allowed_modes:
            logger.debug(
                'Stop closing Chess shop: mode is outside '
                f'{allowed_modes}'
            )
            return False
        shop_visible = self._shop_refresh_marker_visible()
        shop_assumed_open = getattr(self, '_shop_assumed_open', False)
        if not shop_visible and not shop_assumed_open:
            logger.debug('Chess shop is already closed')
            return True
        if self._read_chess_mode() != '战' and not shop_visible:
            # 非战斗画面刷新按钮不会被技能遮挡；看不到即以实际画面为准，
            # 清除跨阶段遗留的内部状态，禁止误点后把商店反而打开。
            self._shop_assumed_open = False
            logger.debug('Chess shop is visibly closed; clear stale state')
            return True
        if (
            self._read_chess_mode() in ('鬼', '待')
            and not shop_visible
        ):
            # 进入鬼/待后游戏会自行收起商店；内部状态可能仍停留在上一帧。
            # 此时不能点击不可用的商店位置，只清除脚本侧状态。
            self._shop_assumed_open = False
            logger.debug('Clear stale Chess shop state in passive mode')
            return True

        logger.debug('Chess shop is open, click market to close it')
        self.device.click_record_remove(self.I_MARKET)
        # 战斗中刷新按钮可能完全被技能遮挡。若商店仅由内部状态确认，
        # 固定点击一次即可关闭，禁止进入“看不见 -> 再点一次”的抖动。
        if (
            self._read_chess_mode() == '战'
            and shop_assumed_open
            and not shop_visible
        ):
            self.click(self.I_MARKET)
            time.sleep(self.SHOP_CLOSE_ATTEMPT_WAIT)
            self.screenshot()
            self._shop_assumed_open = False
            logger.debug('Chess battle economy shop closed by one-shot toggle')
            return True

        deadline = time.monotonic() + self.SHOP_CLOSE_TIMEOUT
        while time.monotonic() < deadline:
            if self._read_chess_mode() not in allowed_modes:
                logger.debug(
                    'Stop closing Chess shop: mode changed outside '
                    f'{allowed_modes}'
                )
                return False
            self.click(self.I_MARKET)
            attempt_deadline = min(
                deadline,
                time.monotonic() + self.SHOP_CLOSE_ATTEMPT_WAIT,
            )
            while time.monotonic() < attempt_deadline:
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                self.screenshot()
                if self._read_chess_mode() not in allowed_modes:
                    logger.debug(
                        'Stop closing Chess shop: mode changed outside '
                        f'{allowed_modes}'
                    )
                    return False
                if not self._is_shop_open():
                    logger.debug('Chess shop closed successfully')
                    self._shop_assumed_open = False
                    return True

        logger.warning('Chess shop failed to close before timeout')
        return False

    def _clear_economy_click_history(self) -> None:
        """豁免合法的经验/刷新循环，保留其他按钮的全局防重复点击保护。"""
        removed_experience = self.device.click_record_remove(self.I_EXPERIENCE)
        removed_refresh = self.device.click_record_remove(self.I_REFRESH)
        if removed_experience or removed_refresh:
            logger.debug(
                'Clear Chess economy click history before legal loop: '
                f'experience={removed_experience}, refresh={removed_refresh}'
            )

    def _match_shop_shikigami_avatar(
        self,
        click_rule: RuleClick,
        expected_name: str | None = None,
        rules: list[tuple[str, RuleImage]] | None = None,
    ) -> dict | None:
        """只在一个商店点击框内匹配 ``*_m`` 式神头像。"""
        best = None
        rules = self.shikigami_shop_rules if rules is None else rules
        for name, rule in rules:
            if expected_name is not None and name != expected_name:
                continue
            matches = rule.match_all_any(
                self.device.image,
                roi=list(click_rule.roi_back),
                threshold=rule.threshold,
                nms_threshold=0.3,
                frame_id=self.device.image_frame_id,
            )
            if not matches:
                continue
            score, x, y, width, height = max(matches, key=lambda item: item[0])
            if best is None or score > best['score']:
                best = {
                    'name': name,
                    'score': float(score),
                    'position': (x + width // 2, y + height // 2),
                }
        if best is not None:
            return best

        fallback = self._match_shop_shikigami_avatar_glow_fallback(
            click_rule,
            expected_name=expected_name,
            rules=rules,
        )
        if fallback is not None:
            logger.debug(
                'Chess shop avatar matched by glow fallback: '
                f'name={fallback["name"]}, score={fallback["score"]:.3f}, '
                f'threshold={self.SHOP_GLOW_TEMPLATE_THRESHOLD}'
            )
        return fallback

    @staticmethod
    def _template_gray(image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            return image
        if image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    def _match_shop_shikigami_avatar_glow_fallback(
        self,
        click_rule: RuleClick,
        expected_name: str | None = None,
        rules: list[tuple[str, RuleImage]] | None = None,
    ) -> dict | None:
        """发光商店卡兜底：用灰度归一化匹配降低光效影响。"""
        x, y, width, height = click_rule.roi_back
        source = self.device.image[y:y + height, x:x + width]
        if source.size == 0:
            return None
        source_gray = self._template_gray(source)
        best = None
        rules = self.shikigami_shop_rules if rules is None else rules
        for name, rule in rules:
            if expected_name is not None and name != expected_name:
                continue
            template = rule.image
            if template is None or template.size == 0:
                continue
            if (
                template.shape[0] > source.shape[0]
                or template.shape[1] > source.shape[1]
            ):
                continue
            template_gray = self._template_gray(template)
            result = cv2.matchTemplate(
                source_gray,
                template_gray,
                cv2.TM_CCOEFF_NORMED,
            )
            _, score, _, location = cv2.minMaxLoc(result)
            if best is None or score > best['score']:
                best = {
                    'name': name,
                    'score': float(score),
                    'position': (
                        x + location[0] + template.shape[1] // 2,
                        y + location[1] + template.shape[0] // 2,
                    ),
                }
        if best is None:
            return None
        if best['score'] < self.SHOP_GLOW_TEMPLATE_THRESHOLD:
            logger.debug(
                'Chess shop glow fallback best candidate below threshold: '
                f'name={best["name"]}, score={best["score"]:.3f}, '
                f'threshold={self.SHOP_GLOW_TEMPLATE_THRESHOLD}'
            )
            return None
        return best

    def _buy_shop_slot(
        self,
        slot_index: int,
        click_rule: RuleClick,
        matched_name: str,
    ) -> bool:
        """持续点击目标商店格，直到原头像不再出现在该格。"""
        deadline = time.monotonic() + self.SHOP_BUY_TIMEOUT
        current_match = self._match_shop_shikigami_avatar(
            click_rule,
            expected_name=matched_name,
        )
        attempts = 0

        while current_match is not None and time.monotonic() < deadline:
            if not self._is_purchase_allowed():
                logger.debug(
                    f'Stop buying {matched_name}: Hyakki mode detected'
                )
                return False
            if not self._can_afford_shop_shikigami(slot_index):
                logger.debug(
                    f'Skip buying {matched_name}: insufficient gold for '
                    f'shop slot {slot_index}'
                )
                return False
            attempts += 1
            logger.info(
                f'Buy Chess card: '
                f'{self._shikigami_display_name(matched_name)} '
                f'(slot={slot_index}, '
                f'attempt={attempts}, avatar_score={current_match["score"]:.3f})'
            )
            self.click(click_rule)
            time.sleep(self.SHOP_BUY_RETRY_INTERVAL)
            self.screenshot()
            current_match = self._match_shop_shikigami_avatar(
                click_rule,
                expected_name=matched_name,
            )
            if current_match is not None:
                if not self._is_purchase_allowed():
                    logger.debug(
                        f'Stop buying {matched_name}: Hyakki mode detected'
                    )
                    return False
                if not self._can_afford_shop_shikigami(slot_index):
                    logger.debug(
                        f'Stop retrying {matched_name}: insufficient gold '
                        f'for shop slot {slot_index}'
                    )
                    return False
                logger.debug(
                    f'Chess shop slot {slot_index} still matches '
                    f'{matched_name} after click, free hand space and retry'
                )
                if self._free_one_hand_slot_for_purchase() is None:
                    logger.warning(
                        f'Chess buy {matched_name} is still unconfirmed and '
                        'no safe hand card can be cleared; block shop refresh'
                    )
                    return False

        if current_match is None:
            logger.debug(
                'Chess shop purchase succeeded by avatar disappearance: '
                f'slot={slot_index}, name={matched_name}, attempts={attempts}'
            )
            return True

        logger.warning(
            f'Chess shop purchase timed out: slot={slot_index}, '
            f'name={matched_name}, avatar remains in slot'
        )
        return False

    def buy_lineup_shikigami_from_shop(self) -> list[str] | None:
        """先以卡面头像记录商店目标，再按记录购买所有阵容式神。"""
        if not self._is_purchase_allowed():
            logger.debug('Stop Chess shop purchase: Hyakki mode detected')
            return None
        if not self._ensure_shop_open():
            return None

        logger.debug('Scan all Chess shop slots before purchasing')
        targets = []

        for slot_index, click_rule in self._shop_slots():
            if not self._is_purchase_allowed():
                logger.debug('Stop Chess shop purchase: Hyakki mode detected')
                return None
            matched = self._match_shop_shikigami_avatar(click_rule)
            if matched is None:
                logger.debug(
                    f'Chess shop slot {slot_index}: no lineup avatar matched'
                )
                continue

            logger.debug(
                f'Chess shop slot {slot_index}: avatar -> '
                f'{matched["name"]}, score={matched["score"]:.3f}'
            )
            targets.append({
                'slot_index': slot_index,
                'click_rule': click_rule,
                'matched_name': matched['name'],
            })

        logger.debug(
            'Chess shop target scan complete: '
            f'{[(item["slot_index"], item["matched_name"]) for item in targets]}'
        )
        purchased = []
        for target in targets:
            if not self._is_purchase_allowed():
                logger.debug('Stop Chess shop purchase: Hyakki mode detected')
                return None
            if not self._can_afford_shop_shikigami(target['slot_index']):
                logger.debug(
                    'Skip unaffordable Chess shop target: '
                    f'slot={target["slot_index"]}, '
                    f'name={target["matched_name"]}'
                )
                continue
            if self._buy_shop_slot(
                slot_index=target['slot_index'],
                click_rule=target['click_rule'],
                matched_name=target['matched_name'],
            ):
                purchased.append(target['matched_name'])
            elif not self._is_purchase_allowed():
                return None
            elif not self._can_afford_shop_shikigami(
                target['slot_index']
            ):
                logger.debug(
                    'Chess target became unaffordable; skip it and continue: '
                    f'slot={target["slot_index"]}, '
                    f'name={target["matched_name"]}'
                )
                continue
            else:
                logger.warning(
                    'Chess target purchase was not confirmed by avatar '
                    'disappearance; '
                    f'slot={target["slot_index"]}, '
                    f'name={target["matched_name"]}; '
                    'stop this shop cycle before any refresh'
                )
                return None

        logger.debug(f'Chess shop check complete, purchased={purchased}')
        return purchased

    def purchase_lineup_cards_once(self) -> list[str] | None:
        """确保商店打开后扫描并购买，不负责关闭商店。"""
        return self.buy_lineup_shikigami_from_shop()

    def _reset_economy_state(self) -> None:
        """重置单局可暂停的回目结束任务和商店状态。"""
        self._economy_pending = False
        self._economy_step_state = 'idle'
        self._economy_sequence_level = None
        self._economy_sequence_index = 0
        self._formation_pending = False
        self._economy_battle_mode = False
        self._shop_assumed_open = False

    def _schedule_economy_cycle(self) -> None:
        """登记一次经济任务；已有未完成原子动作时保持其精确进度。"""
        if getattr(self, '_economy_pending', False):
            logger.debug(
                'Chess economy is already pending: '
                f'state={self._economy_step_state}'
            )
            return
        self._economy_pending = True
        self._economy_step_state = 'ready'
        logger.debug('Schedule Chess economy upgrade/refresh cycle')

    def _schedule_round_end_actions(self, round_no: int) -> None:
        """登记回目结束任务；第四回目起额外登记系统站位整理。"""
        if round_no > 3:
            if not getattr(self, '_formation_pending', False):
                logger.debug(
                    f'Schedule Chess formation recovery after round {round_no}'
                )
            self._formation_pending = True
        else:
            logger.debug(
                f'Chess round {round_no} uses alternate early layout; '
                'skip formation recovery scheduling'
            )
        self._schedule_economy_cycle()

    def _finish_economy_cycle(self, reason: str) -> None:
        self._economy_pending = False
        self._economy_step_state = 'idle'
        logger.debug(f'Chess economy cycle complete: {reason}')

    def _click_economy_button_and_confirm_gold(
        self,
        button: RuleImage,
        expected_cost: int,
        label: str,
        allow_hidden: bool,
    ) -> str:
        """点击经济按钮，以金币下降确认；返回 success/no_progress/unknown。"""
        gold_before = self._read_shop_gold()
        if gold_before is None:
            logger.warning(f'Cannot confirm Chess {label}: gold OCR unavailable')
            return 'no_progress'
        if not allow_hidden and not self.appear(button):
            logger.warning(f'Cannot execute Chess {label}: button is missing')
            return 'no_progress'

        for attempt in range(1, self.ECONOMY_CONFIRM_RETRIES + 1):
            logger.debug(
                f'Chess {label}: fixed click attempt={attempt}, '
                f'gold_before={gold_before}'
            )
            self._clear_economy_click_history()
            self.click(button)
            time.sleep(self.SHOP_REFRESH_WAIT)
            self.screenshot()
            gold_after = self._read_shop_gold()
            if gold_after is None:
                logger.warning(
                    f'Chess {label} was clicked but confirmation OCR is '
                    'unavailable; preserve forward progress'
                )
                return 'unknown'
            if gold_after <= gold_before - expected_cost:
                logger.debug(
                    f'Chess {label} confirmed by gold: '
                    f'{gold_before} -> {gold_after}'
                )
                return 'success'
            logger.warning(
                f'Chess {label} click made no confirmed progress: '
                f'{gold_before} -> {gold_after}'
            )

        return 'no_progress'

    def _economy_sequence_for_level(self, level: int) -> tuple[str, ...]:
        """返回当前阶数的原子操作序列。"""
        if level >= self._lineup_final_level():
            return ('refresh',)
        if level <= 7:
            return ('experience', 'refresh')
        return ('experience', 'refresh', 'refresh')

    def _economy_reserve_for_level(self, level: int) -> int:
        if level >= self._lineup_final_level():
            return 0
        if level <= 5:
            return 42
        if level <= 7:
            return 30
        return 10

    def _reset_economy_sequence_if_level_changed(self, level: int) -> None:
        if self._economy_sequence_level == level:
            return
        logger.debug(
            'Reset Chess economy operation counter: '
            f'{self._economy_sequence_level} -> {level}'
        )
        self._economy_sequence_level = level
        self._economy_sequence_index = 0

    def _next_economy_operation(self, level: int) -> str:
        self._reset_economy_sequence_if_level_changed(level)
        sequence = self._economy_sequence_for_level(level)
        index = self._economy_sequence_index % len(sequence)
        operation = sequence[index]
        logger.debug(
            'Chess economy next operation: '
            f'level={level}, sequence={sequence}, index={index}, '
            f'operation={operation}'
        )
        return operation

    def _advance_economy_operation_counter(self, level: int) -> None:
        self._reset_economy_sequence_if_level_changed(level)
        sequence = self._economy_sequence_for_level(level)
        self._economy_sequence_index = (
            self._economy_sequence_index + 1
        ) % len(sequence)
        logger.debug(
            'Advance Chess economy operation counter: '
            f'level={level}, next_index={self._economy_sequence_index}'
        )

    def _can_execute_economy_operation(
        self,
        level: int,
        gold: int,
        operation: str,
    ) -> bool:
        reserve = self._economy_reserve_for_level(level)
        cost = (
            self.EXPERIENCE_COST
            if operation == 'experience'
            else self.SHOP_REFRESH_COST
        )
        if level < self._lineup_final_level() and gold <= reserve:
            return False
        return gold >= reserve + cost

    def _run_economy_atomic_batch(self, battle_mode: bool = False) -> str:
        """执行一个由计数器决定的升级/刷新原子动作。"""
        if not getattr(self, '_economy_pending', False):
            return 'complete'
        if not self._is_purchase_allowed():
            logger.debug('Pause Chess economy: Hyakki mode detected')
            return 'blocked'

        previous_battle_mode = getattr(self, '_economy_battle_mode', False)
        self._economy_battle_mode = battle_mode
        try:
            level = self._read_level()
            gold = self._read_shop_gold()
            if level is None or gold is None:
                logger.warning(
                    'Pause Chess economy: level or gold OCR unavailable'
                )
                return 'blocked'

            operation = self._next_economy_operation(level)
            if not self._can_execute_economy_operation(level, gold, operation):
                self._finish_economy_cycle(
                    f'budget limit reached, level={level}, gold={gold}, '
                    f'operation={operation}, '
                    f'reserve={self._economy_reserve_for_level(level)}, '
                    f'final_level={self._lineup_final_level()}'
                )
                return 'complete'

            if operation == 'experience':
                result = self._click_economy_button_and_confirm_gold(
                    self.I_EXPERIENCE,
                    self.EXPERIENCE_COST,
                    'buy experience',
                    allow_hidden=battle_mode,
                )
                if result == 'no_progress':
                    return 'blocked'
                self._advance_economy_operation_counter(level)
            else:
                # 只有刷新动作要求商店打开；购买经验不改变商店状态。
                if not self._ensure_shop_open():
                    return 'blocked'
                result = self._click_economy_button_and_confirm_gold(
                    self.I_REFRESH,
                    self.SHOP_REFRESH_COST,
                    'refresh shop',
                    allow_hidden=battle_mode,
                )
                if result == 'no_progress':
                    return 'blocked'
                logger.info(
                    f'Refresh Chess shop: cards={self._shop_shikigami_summary()}'
                )
                self._advance_economy_operation_counter(level)
                purchased = self.purchase_lineup_cards_once()
                if purchased is None:
                    logger.warning(
                        'Pause Chess economy after refresh: purchase not '
                        'confirmed'
                    )
                    return 'blocked'
            self._economy_step_state = 'ready'

            logger.debug(
                'Chess economy atomic batch finished: '
                f'operation={operation}, battle_mode={battle_mode}'
            )

            # 只判断是否还有下一批；真正执行留到外层重新截图、检查回目
            # 后，确保新回目的备阶段能够抢占长时间经济循环。
            level = self._read_level()
            gold = self._read_shop_gold()
            if level is None or gold is None:
                return 'pending'
            next_operation = self._next_economy_operation(level)
            if self._can_execute_economy_operation(
                level,
                gold,
                next_operation,
            ):
                return 'pending'
            self._finish_economy_cycle(
                f'budget limit reached after batch, level={level}, '
                f'gold={gold}, next_operation={next_operation}, '
                f'reserve={self._economy_reserve_for_level(level)}, '
                f'final_level={self._lineup_final_level()}'
            )
            return 'complete'
        finally:
            self._economy_battle_mode = previous_battle_mode

    def _is_in_chess_game(self) -> bool:
        """阵容入口或商店任一出现，即认为仍处于棋局内。"""
        return self.appear(self.I_OPEN_LINEUP) or self.appear(self.I_MARKET)

    def _wait_until_in_chess_game(
        self,
        timeout: float,
        retry_start: bool = False,
    ) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.screenshot()
            if self._is_in_chess_game():
                return
            if retry_start and self.appear(self.I_CHESS_START):
                self.appear_then_click(self.I_CHESS_START, interval=2.0)
            time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
        raise GameStuckError('Chess: timeout waiting for in-game markers')

    def _start_chess_game(self) -> None:
        """从棋局大厅开战，确认进入局内后直接开始回合流程。"""
        logger.debug('Chess game start')
        # 御魂容量只在单局内记忆。新对局重新允许所有已上阵式神接受
        # 御魂，避免上一局的“已满”状态污染下一局。
        self._soul_full_positions = set()
        self._board_lineup_names = set()
        self._player_deployed_positions = set()
        self._alive_players_candidate = None
        self._alive_players_confirmed = 0
        self._reset_economy_state()
        strategy = self.get_lineup_strategy()
        logger.debug(
            'Reset Chess per-game state: '
            f'lineup={strategy["key"]} ({strategy["display_name"]})'
        )
        self._wait_until_in_chess_game(
            timeout=self.GAME_ENTER_TIMEOUT,
            retry_start=True,
        )
        logger.debug(
            'Chess entered game; skip lineup preset and start round loop'
        )

    def _handle_preparation(self) -> bool:
        """统一备阶段：Buff 弹窗优先处理，随后上式神、上御魂。"""
        if self.appear(self.I_SELECT_BUFF):
            self.select_random_buff()
            return False
        if not self._is_preparation_mode():
            return False
        # deploy_shikigami_from_hand 内部负责确认商店关闭、人数上限和
        # 每次拖动后的重新定位，准备阶段不重复实现这些约束。
        self.deploy_shikigami_from_hand()
        if self._is_shop_open() or not self._is_preparation_mode():
            logger.warning(
                'Stop Chess preparation before soul phase: '
                'shop is open or mode left preparation'
            )
            return False
        # 上式神与上御魂保持为两个独立操作，由准备阶段明确编排顺序。
        verified_board_names = {
            name
            for name in getattr(self, '_board_lineup_names', set())
            if name in self.shikigami_deploy_positions
        }
        self.equip_souls_from_hand(verified_board_names)
        return self._is_preparation_mode()

    def _run_preparation_economy_until_time_limit(self) -> None:
        """备阶段升级/刷新循环：仅这部分受剩余时间限制。"""
        if not self._is_preparation_mode():
            return

        self._schedule_economy_cycle()
        while getattr(self, '_economy_pending', False):
            if not self._is_preparation_mode():
                return
            if self.appear(self.I_SELECT_BUFF):
                return
            # 只有升级/刷新循环受剩余时间限制；第二套布局没有 now_time
            # OCR，_read_remaining_time 会返回 None，因此不会误打断购买。
            remaining = self._read_remaining_time()
            if remaining is not None and remaining <= 15:
                logger.info(
                    'Stop Chess preparation upgrade/refresh loop: '
                    f'remaining_time={remaining} <= 15'
                )
                return
            result = self._run_economy_atomic_batch(battle_mode=False)
            if result in ('complete', 'blocked'):
                return
            self.screenshot()

    def _run_battle_economy_until_budget_limit(self) -> None:
        """战阶段续跑升级/刷新循环；同样受剩余时间 <= 15 保护。"""
        if self._read_chess_mode() != '战':
            return
        self._schedule_economy_cycle()
        while (
            self._read_chess_mode() == '战'
            and getattr(self, '_economy_pending', False)
        ):
            remaining = self._read_remaining_time()
            if remaining is not None and remaining <= 15:
                logger.info(
                    'Stop Chess battle upgrade/refresh loop: '
                    f'remaining_time={remaining} <= 15'
                )
                return
            result = self._run_economy_atomic_batch(battle_mode=True)
            if result in ('complete', 'blocked'):
                return
            self.screenshot()

    def _return_to_chess_lobby(self) -> None:
        """点击返回与分享页，并持续安全点击直到进入可识别页面。"""
        logger.debug('Chess game finished')
        deadline = time.monotonic() + self.RESULT_RETURN_TIMEOUT
        share_seen = False
        exit_clicked = False
        safe_clicks = 0
        rank_recovery_started = False
        fallback_exit_at = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            self.screenshot()

            if (
                rank_recovery_started
                and self.appear(self.I_CHECK_CHESS)
            ):
                logger.debug('Returned to Chess lobby from recovered rank page')
                return

            # 任务重启时可能已经停在排名界面，此时没有机会重新经历分享
            # 页面，保留恢复入口；正常结算只有在分享流程完成后才处理排名。
            rank_page = self.appear(self.I_CHECK_RANK)
            rank_button = self.appear(self.I_RANK_GOTO_CHESS)
            if (rank_page or rank_button) and not exit_clicked:
                logger.debug('Chess rank page detected, return to Chess lobby')
                rank_recovery_started = True
                if rank_button:
                    self.appear_then_click(self.I_RANK_GOTO_CHESS, interval=1.5)
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                continue

            if not exit_clicked:
                if self.appear(self.I_EXIT_TO_CHESS):
                    logger.debug(
                        'Chess return-to-lobby button detected, click it; '
                        'share page is now mandatory'
                    )
                    self.appear_then_click(self.I_EXIT_TO_CHESS, interval=1.5)
                    exit_clicked = True
                    time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                    continue
                if self.appear(self.I_EXIT_TO_CHESS_2):
                    logger.debug(
                        'Chess active-exit result detected; click it and '
                        'require share page next'
                    )
                    self.appear_then_click(
                        self.I_EXIT_TO_CHESS_2,
                        interval=1.5,
                    )
                    exit_clicked = True
                    time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                    continue
                if self.appear(self.I_SHARE):
                    # 脚本重启时可能已经点击过返回并停在分享页。
                    logger.debug(
                        'Chess return flow resumed from existing share page'
                    )
                    exit_clicked = True
                    share_seen = True
                    continue
                if time.monotonic() >= fallback_exit_at:
                    # 模板偶发未命中时，正常结算按钮位置是固定的。
                    logger.warning(
                        'Chess return button image was not detected; '
                        'click its fixed safe position and require share page'
                    )
                    self.click(self.I_EXIT_TO_CHESS)
                    exit_clicked = True
                    time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                    continue
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                continue

            if not share_seen and self.appear(self.I_SHARE):
                share_seen = True
                logger.debug(
                    'Chess share page detected after return-to-lobby click'
                )

            if not share_seen:
                # 即便大厅标志发生误命中，也必须先等到分享页，禁止提前
                # 返回上层循环并开始下一局。
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                continue

            if rank_page or rank_button:
                logger.debug(
                    'Chess rank page detected after share safe clicks'
                )
                rank_recovery_started = True
                if rank_button:
                    self.appear_then_click(
                        self.I_RANK_GOTO_CHESS,
                        interval=1.5,
                    )
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                continue

            if self.appear(self.I_CHECK_CHESS):
                logger.debug(
                    'Returned to Chess lobby after share flow: '
                    f'safe_clicks={safe_clicks}'
                )
                return

            # 分享页出现后不再限制点击次数。只要尚未进入棋局大厅或
            # 排名页，就继续点击左侧安全区域推动结算动画和弹窗。
            safe_click = random_click(
                ltrb=(True, False, False, False)
            )
            safe_clicks += 1
            logger.debug(
                'Chess share safe click: '
                f'{safe_clicks}, target={safe_click.name}'
            )
            self.click(safe_click)
            time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
        raise GameStuckError('Chess: failed to return to lobby after result')

    def _chess_result_flow_visible(self) -> bool:
        """检测任一已知结算/返回大厅标志。"""
        return (
            self.appear(self.I_CHECK_CHESS)
            or self.appear(self.I_EXIT_TO_CHESS)
            or self.appear(self.I_EXIT_TO_CHESS_2)
            or self.appear(self.I_SHARE)
            or self.appear(self.I_CHECK_RANK)
            or self.appear(self.I_RANK_GOTO_CHESS)
        )

    def active_exit_chess_game(self) -> bool:
        """Chess 专属主动退出；不扩展通用 GeneralBattle 接口。"""
        logger.debug('Chess active exit requested')
        deadline = time.monotonic() + self.RESULT_RETURN_TIMEOUT
        next_exit_click_at = 0.0
        next_confirm_click_at = 0.0
        dialog_seen = False
        confirm_clicked = False

        while time.monotonic() < deadline:
            self.device.stuck_record_clear()
            self.screenshot()

            confirm_visible = self.appear(self.I_CHESS_EXIT_CONFIRM)
            cancel_visible = self.appear(self.I_CHESS_EXIT_CANCEL)
            if confirm_visible or cancel_visible:
                dialog_seen = True

            # 只有确实点击过确认按钮后，它的消失才代表主动退出成功。
            if dialog_seen and confirm_clicked and not confirm_visible:
                logger.debug('Chess active exit success')
                self._return_to_chess_lobby()
                return True

            now = time.monotonic()
            if dialog_seen:
                if confirm_visible and now >= next_confirm_click_at:
                    self.click(self.I_CHESS_EXIT_CONFIRM)
                    confirm_clicked = True
                    next_confirm_click_at = now + 2.0
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                continue

            if now >= next_exit_click_at:
                if self.appear(self.I_CHESS_EXIT):
                    self.click(self.I_CHESS_EXIT)
                next_exit_click_at = now + 2.0
            time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)

        logger.warning(
            'Chess active exit timed out: '
            f'dialog_seen={dialog_seen}, confirm_clicked={confirm_clicked}'
        )
        return False

    def _recover_interrupted_chess_game(self) -> bool:
        """仅在任务启动时清理上次脚本中断后遗留的棋局。"""
        self.screenshot()

        # 已在大厅时无需恢复。
        if self.appear(self.I_CHECK_CHESS):
            return False

        # 上次可能已经进入结算、分享或排名阶段，直接继续既有返回流程。
        if (
            self.appear(self.I_EXIT_TO_CHESS)
            or self.appear(self.I_EXIT_TO_CHESS_2)
            or self.appear(self.I_SHARE)
            or self.appear(self.I_CHECK_RANK)
            or self.appear(self.I_RANK_GOTO_CHESS)
        ):
            logger.debug('Chess startup recovery: unfinished result flow detected')
            self._return_to_chess_lobby()
            return True

        mode = self._read_chess_mode()
        if mode is None and not self._is_in_chess_game():
            return False

        logger.warning(
            f'Chess startup recovery: interrupted in-game state detected, mode={mode}'
        )
        if not self.active_exit_chess_game():
            raise GameStuckError(
                'Chess: interrupted game detected but active exit was unavailable'
            )
        return True

    def _run_round_loop(self) -> None:
        """运行单局回目循环；Chess 自行持续刷新通用卡死计时。"""
        self.device.stuck_record_clear()
        try:
            self._run_game_by_rounds_without_device_stuck_timeout()
        finally:
            self.device.stuck_record_clear()

    def _finish_chess_game_if_visible(self) -> bool:
        """发现任一结算入口时完成返回大厅流程。"""
        if not self._chess_result_flow_visible():
            return False
        self._return_to_chess_lobby()
        return True

    def _wait_for_round_start(self) -> int | None:
        """等待稳定回目数字；返回 None 表示本局已经结算。"""
        candidate = None
        confirmed = 0
        empty_frames = 0
        while True:
            self.device.stuck_record_clear()
            self.screenshot()
            if self._finish_chess_game_if_visible():
                return None

            round_no = self._read_round_number()
            mode = self._read_chess_mode()
            if round_no is not None:
                empty_frames = 0
                if round_no == candidate:
                    confirmed += 1
                else:
                    candidate = round_no
                    confirmed = 1
                if confirmed >= self.ROUND_CONFIRM_FRAMES:
                    return round_no
            else:
                candidate = None
                confirmed = 0
                if mode is None:
                    empty_frames += 1
                    if empty_frames >= self.RESULT_EMPTY_CONFIRM_FRAMES:
                        logger.debug(
                            'Chess round and mode stayed empty before a round; '
                            'enter result flow'
                        )
                        self._return_to_chess_lobby()
                        return None
                else:
                    empty_frames = 0
            time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)

    def _handle_round_end(self) -> bool:
        """在下一次可用的备阶段补做系统卡回收、上阵和御魂。"""
        if not getattr(self, '_formation_pending', False):
            return True
        if not self._is_preparation_mode():
            return False

        logger.debug('Chess pending system-card recall')
        if not self._ensure_shop_closed():
            return False
        if not self.recall_all_board_cards():
            return False
        time.sleep(self.BOARD_REDEPLOY_SETTLE_WAIT)
        self.screenshot()
        if not self._is_preparation_mode():
            return False
        # 回收之后先恢复阵容，再允许经济操作。
        logger.debug('Chess immediate redeploy after pending recall')
        if not self._handle_preparation():
            return False

        self._formation_pending = False
        logger.debug('Chess pending formation recovery completed')
        return True

    def _handle_preparation_stage(self, stage_index: int) -> bool:
        """执行一次完整备阶段；卖卡已移至独立的战阶段环节。"""
        logger.debug(f'Chess preparation stage {stage_index}/2')
        return self._handle_preparation() and self._is_preparation_mode()

    def _handle_battle_sell_stage(self) -> bool:
        """战阶段独立卖卡：持续清理杂卡和纹章，直到确认手牌干净。"""
        if self._read_chess_mode() != '战':
            return False
        logger.debug('Chess battle hand-card cleanup')
        sold = self.cleanup_non_lineup_hand_cards(allowed_modes=('战',))
        logger.debug(f'Chess battle hand-card cleanup complete: sold={sold}')
        return self._read_chess_mode() == '战'

    def _handle_passive_stage(self, mode: str) -> bool:
        """战、鬼、待阶段只等待，不主动改变商店状态。"""
        return mode in ('战', '鬼', '待')

    def _handle_battle_economy(self) -> str:
        """卖卡完成后，在战阶段续跑一个尚未完成的经济原子动作。"""
        if self._read_chess_mode() != '战':
            return 'blocked'
        if not getattr(self, '_economy_pending', False):
            return 'complete'
        logger.debug(
            'Chess battle economy continuation: '
            f'state={self._economy_step_state}'
        )
        return self._run_economy_atomic_batch(battle_mode=True)

    def run_one_round(self, round_no: int) -> int | None:
        """执行一个回目：回合开始 -> 备 -> 战/鬼/待 -> 等待新回合。"""
        logger.debug(f'Chess round {round_no}')
        self._read_round_resources(round_no, self._read_chess_mode())
        phase = 'await_preparation'
        preparation_done = False
        next_round_candidate = None
        next_round_confirmed = 0
        empty_frames = 0
        unknown_since = None
        battle_hand_cleanup_done = False

        while True:
            self.device.stuck_record_clear()
            self.screenshot()
            if self._finish_chess_game_if_visible():
                return None
            if self._early_exit_by_alive_players_reached():
                logger.warning(
                    'Chess remaining-player early exit reached: '
                    f'alive={self._alive_players_candidate}, '
                    f'threshold={self._remaining_players_exit}'
                )
                if self.active_exit_chess_game():
                    return None
                logger.warning(
                    'Chess early-exit condition reached, but active exit '
                    'button is currently unavailable; retry next frame'
                )

            observed_round = self._read_round_number()
            mode = self._read_chess_mode()

            if observed_round is None and mode is None:
                empty_frames += 1
                if empty_frames >= self.RESULT_EMPTY_CONFIRM_FRAMES:
                    logger.debug(
                        f'Chess round {round_no} state stayed empty; '
                        'enter result flow'
                    )
                    self._return_to_chess_lobby()
                    return None
            else:
                empty_frames = 0

            round_transition_pending = False
            if observed_round is not None and observed_round != round_no:
                if observed_round == next_round_candidate:
                    next_round_confirmed += 1
                else:
                    next_round_candidate = observed_round
                    next_round_confirmed = 1
                round_transition_pending = True
                if next_round_confirmed >= self.ROUND_CONFIRM_FRAMES:
                    logger.debug(
                        f'Chess round boundary confirmed: {round_no} -> '
                        f'{observed_round}, phase={phase}, '
                        f'preparation_done={preparation_done}'
                    )
                    return observed_round
            else:
                next_round_candidate = None
                next_round_confirmed = 0

            # 回目数字第一次变化时暂停所有旧回目动作，等待第二帧确认。
            if round_transition_pending:
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                continue

            in_game = mode is not None or self._is_in_chess_game()
            if in_game:
                unknown_since = None
            elif unknown_since is None:
                unknown_since = time.monotonic()
            elif time.monotonic() - unknown_since >= self.UNKNOWN_STATE_TIMEOUT:
                raise GameStuckError(
                    f'Chess: lost all markers during round {round_no}'
                )

            if mode in ('战', '鬼', '待'):
                if mode == '战':
                    self._run_battle_economy_until_budget_limit()
                    if not battle_hand_cleanup_done:
                        battle_hand_cleanup_done = (
                            self._handle_battle_sell_stage()
                        )
                    self._handle_passive_stage('战')
                else:
                    self._handle_passive_stage(mode)
                if phase == 'await_preparation':
                    preparation_done = True
                    phase = 'await_battle_end'
                    logger.warning(
                        f'Chess round {round_no}: resumed in passive mode '
                        f'{mode}; treat preparation as already passed'
                    )

            elif mode == '备':
                # Buff 面板是当前备阶段的高优先级中断事件。选完后不推进
                # phase/preparation_count；下一轮循环会把它当作新的同阶段备，
                # 从上式神、上御魂的起点重新执行。
                if self.appear(self.I_SELECT_BUFF):
                    logger.debug('Chess preparation interrupted by buff selection')
                    self.select_random_buff()
                    continue

                if phase == 'await_preparation':
                    # 回合开始先独立购买一次：开商店、扫商店、买目标。
                    # 15 秒保护只约束后面的升级/刷新循环，不影响这次买卡。
                    self.purchase_lineup_cards_once()
                    self._run_preparation_economy_until_time_limit()
                    if not self._is_preparation_mode():
                        time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                        continue
                    if self._handle_preparation_stage(1):
                        preparation_done = True
                        phase = 'await_battle'
                        logger.debug(
                            f'Chess round {round_no}: preparation '
                            'complete; wait for 战/鬼/待'
                        )

            interval = (
                self.HYAKKI_SCREENSHOT_INTERVAL
                if mode == '鬼'
                else self.NORMAL_SCREENSHOT_INTERVAL
            )
            time.sleep(interval)

    def _run_game_by_rounds_without_device_stuck_timeout(self) -> None:
        """单局协调器：逐个调用单回目函数，直至完成结算返回。"""
        round_no = self._wait_for_round_start()
        while round_no is not None:
            round_no = self.run_one_round(round_no)

    def run_one_game(self) -> None:
        """从棋局大厅开始一局，并运行全部回目直到返回棋局大厅。"""
        self._start_chess_game()
        self._run_round_loop()

    def run(self):
        """按执行次数循环百鬼棋局，并可在鼬乐币刷满时提前结束。"""
        chess_task_config = getattr(self.config, 'chess', None)
        chess_config = getattr(chess_task_config, 'chess_config', None)
        selected_lineup = getattr(
            chess_config,
            'lineup_bond',
            self.DEFAULT_LINEUP_KEY,
        )
        strategy = self.select_lineup_strategy(selected_lineup)

        # 启动恢复可能主动退出遗留对局；正常对局还可由人数约束退出。
        self._recover_interrupted_chess_game()
        self.goto_page(page_chess)

        # Config 持有完整 ConfigModel，Chess 专属配置位于
        # self.config.chess.chess_config。旧配置未包含新字段时使用默认值，
        # 避免升级后任务在进入棋局大厅时直接崩溃。
        target_count = int(getattr(chess_config, 'run_count', 1))
        coin_full_exit = bool(
            getattr(chess_config, 'coin_full_exit', False)
        )
        self._early_exit_enabled = bool(
            getattr(chess_config, 'early_exit', False)
        )
        self._remaining_players_exit = max(
            0,
            min(
                8,
                int(getattr(chess_config, 'remaining_players', 0)),
            ),
        )
        completed = 0
        logger.info(
            'Chess task constraints: '
            f'lineup={strategy["key"]} ({strategy["display_name"]}), '
            f'run_count={target_count}, coin_full_exit={coin_full_exit}, '
            f'early_exit={self._early_exit_enabled}, '
            f'remaining_players={self._remaining_players_exit}'
        )

        while target_count == -1 or completed < target_count:
            self.screenshot()
            if coin_full_exit and self._coin_is_full():
                logger.info(
                    'Stop Chess task before next game: coin reached 600/600'
                )
                break

            logger.debug(
                'Chess game loop '
                f'{completed + 1}/'
                f'{"infinite" if target_count == -1 else target_count}'
            )
            self.run_one_game()
            completed += 1
            logger.info(
                f'Chess completed games: {completed}/'
                f'{"infinite" if target_count == -1 else target_count}'
            )

            # _run_round_loop 正常返回时已经回到棋局大厅，此处刷新后检查
            # 本局获得的鼬乐币；勾选时次数和满币任一条件先满足即结束。
            if coin_full_exit:
                self.screenshot()
                if self._coin_is_full():
                    logger.info(
                        'Stop Chess task after game: coin reached 600/600'
                    )
                    break

        logger.info(
            f'Chess task loop finished: completed={completed}, '
            f'target={target_count}, coin_full_exit={coin_full_exit}'
        )
        self.set_next_run(task='Chess', success=True, finish=True)
        raise TaskEnd('Chess')
