"""Chess lineup, template loading, and hand-card recognition."""

# This Python file uses the following encoding: utf-8

import time
from functools import cached_property
from pathlib import Path

import cv2

from module.atom.image import RuleImage
from module.logger import logger
from tasks.Chess.strategy.lineup import resolve_lineup_key
from tasks.Chess.strategy.shikigami_catalog import (
    SHIKIGAMI_BONDS_BY_ROMAJI,
    SHIKIGAMI_BY_ROMAJI,
)
from tasks.Chess.strategy.soul_catalog import SOUL_BY_ROMAJI


CHESS_TASK_DIR = Path(__file__).resolve().parents[1]


class ChessRecognitionMixin:
    """Internal mixin; use through ``ScriptTask`` only."""

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

    @cached_property
    def store_gold_rule(self) -> RuleImage:
        """商店卡价格前的金币图标，用于定位其右侧价格数字。"""
        return RuleImage(
            roi_front=(0, 0, 18, 18),
            roi_back=(0, 0, 1280, 720),
            method=RuleImage.METHOD_TEMPLATE_MATCH,
            threshold=self.SHOP_GOLD_ICON_THRESHOLD,
            file=str(CHESS_TASK_DIR / 'c' / 'store_gold.png'),
        )

    def _shop_shikigami_summary(self) -> list[str]:
        """汇总当前商店五格中已识别出的式神。"""
        names = []
        for slot_index, click_rule in self._shop_slots():
            matched = self._recognize_shop_slot(
                slot_index,
                click_rule,
                fallback_rules=self.all_shikigami_shop_rules,
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
        template_dir = CHESS_TASK_DIR / folder
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
        template_dir = CHESS_TASK_DIR / 'c'
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
        template_dir = CHESS_TASK_DIR / 'shikigami'
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
            CHESS_TASK_DIR
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
        template_dir = CHESS_TASK_DIR / 'shikigami/store'
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
        """按拼音文件名加载御魂模板，运行时统一使用拼音键。"""
        rules = self._load_hand_template_folder('soul', prefix='sou_')
        normalized = []
        for romaji, rule in rules:
            entry = SOUL_BY_ROMAJI.get(romaji)
            if entry is None:
                logger.warning(
                    f'Ignore unregistered Chess soul template: {romaji}'
                )
                continue
            normalized.append((entry.romaji, rule))
        return normalized

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
                    if category == 'shikigami':
                        best['bonds'] = SHIKIGAMI_BONDS_BY_ROMAJI.get(name, ())

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
                time.sleep(self.SCREENSHOT_INTERVAL)
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
