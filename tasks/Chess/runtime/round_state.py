"""Chess runtime: round OCR, board occupancy, and state readers."""

# This Python file uses the following encoding: utf-8

import random
import re
import time
from functools import cached_property
from pathlib import Path

import cv2
from module.logger import logger
from tasks.Chess.strategy.grigri import (
    grigri_category,
    grigri_file,
    grigri_names_for_quality,
    grigri_score,
    grigri_selection_key,
    resolve_grigri_name,
)


class ChessRoundStateMixin:
    """Internal mixin; use through ``ScriptTask`` only."""

    @cached_property
    def grigri_icon_templates(self) -> dict[str, object]:
        """按中文名缓存全部符咒图标，供 OCR 失败时进行图像兜底。"""
        badge_dir = Path(__file__).resolve().parents[1] / 'badge'
        templates = {}
        for name in grigri_names_for_quality(None):
            file = badge_dir / grigri_file(name)
            image = cv2.imread(str(file), cv2.IMREAD_COLOR)
            if image is None:
                logger.warning(f'Chess grigri icon is missing: {file}')
                continue
            templates[name] = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        logger.debug(f'Loaded {len(templates)} Chess grigri icon templates')
        return templates

    def _detect_grigri_quality(self) -> str | None:
        for quality, rule in (
            ('gold', self.I_GRIGRI_GOLD),
            ('silver', self.I_GRIGRI_SILVER),
            ('copper', self.I_GRIGRI_COPPER),
        ):
            if self.appear(rule):
                return quality
        logger.warning('Chess grigri quality was not recognized')
        return None

    def _match_grigri_icon(
        self,
        option_rule,
        quality: str | None,
    ) -> tuple[str | None, float]:
        x, y, width, height = option_rule.roi_front
        image_height, image_width = self.device.image.shape[:2]
        # 点击框略窄于 94px 图标，匹配区向左右各扩 24px。
        left = max(0, x - 24)
        top = max(0, y - 8)
        right = min(image_width, x + width + 24)
        bottom = min(image_height, y + height)
        source = self.device.image[top:bottom, left:right]
        best_name, best_score = None, 0.0
        for name in grigri_names_for_quality(quality):
            template = self.grigri_icon_templates.get(name)
            if (
                template is None
                or template.shape[0] > source.shape[0]
                or template.shape[1] > source.shape[1]
            ):
                continue
            result = cv2.matchTemplate(
                source,
                template,
                cv2.TM_CCOEFF_NORMED,
            )
            _, score, _, _ = cv2.minMaxLoc(result)
            if score > best_score:
                best_name, best_score = name, float(score)
        if best_score < self.GRIGRI_ICON_THRESHOLD:
            return None, best_score
        return best_name, best_score

    def _recognize_grigri_options(self) -> list[dict]:
        quality = self._detect_grigri_quality()
        lineup_strategy = self.get_lineup_strategy()
        option_rules = (
            self.C_GRIGRI_OPTION_1,
            self.C_GRIGRI_OPTION_2,
            self.C_GRIGRI_OPTION_3,
        )
        ocr_rules = (
            self.O_GRIGRI_OPTION_NAME_1,
            self.O_GRIGRI_OPTION_NAME_2,
            self.O_GRIGRI_OPTION_NAME_3,
        )
        result = []
        for index, (option_rule, ocr_rule) in enumerate(
            zip(option_rules, ocr_rules),
            start=1,
        ):
            raw = self._normalize_ocr_text(ocr_rule.ocr(self.device.image))
            ocr_name, text_score = resolve_grigri_name(raw, quality)
            icon_name, icon_score = self._match_grigri_icon(
                option_rule,
                quality,
            )
            # OCR 已达到图鉴映射阈值时优先采用文字；图像负责校验和兜底。
            name = ocr_name or icon_name
            if ocr_name and icon_name and ocr_name != icon_name:
                logger.warning(
                    'Chess grigri OCR/icon conflict: '
                    f'option={index}, ocr={ocr_name}({text_score:.3f}), '
                    f'icon={icon_name}({icon_score:.3f})'
                )
            category = grigri_category(name)
            score = grigri_score(name, lineup_strategy)
            selection_key = grigri_selection_key(name, lineup_strategy)
            item = {
                'index': index,
                'quality': quality,
                'raw': raw,
                'name': name,
                'category': category,
                'score': score,
                'selection_key': selection_key,
                'text_score': text_score,
                'icon_name': icon_name,
                'icon_score': icon_score,
                'rule': option_rule,
            }
            result.append(item)
            logger.info(
                'Chess grigri option: '
                f'option={index}, quality={quality or "unknown"}, '
                f'ocr=[{raw}], name={name or "未知"}, '
                f'category={category}, score={score:g}, '
                f'icon={icon_name or "未命中"}({icon_score:.3f})'
            )
        return result

    @staticmethod
    def _best_grigri_option(options: list[dict]) -> dict:
        best_key = max(item['selection_key'] for item in options)
        return random.choice([
            item for item in options if item['selection_key'] == best_key
        ])

    def _refresh_grigri_option(self, option: dict) -> bool:
        index = option['index']
        done_rule = getattr(self, f'I_GRIGRI_FRESH_DONE_{index}')
        none_rule = getattr(self, f'I_GRIGRI_FRESH_NONE_{index}')
        if self.appear(none_rule):
            logger.debug(f'Chess grigri option {index} was already refreshed')
            return False
        if not self.appear(done_rule):
            logger.warning(
                f'Chess grigri refresh state is unknown: option={index}'
            )
            return False
        logger.info(
            f'Refresh low-score Chess grigri: '
            f'option={index}, score={option["score"]:g}'
        )
        self.click(done_rule)
        deadline = time.monotonic() + self.GRIGRI_REFRESH_CONFIRM_TIMEOUT
        while time.monotonic() < deadline:
            time.sleep(self.GRIGRI_REFRESH_WAIT)
            self.screenshot()
            if self.appear(none_rule):
                logger.info(
                    'Chess grigri refresh confirmed: '
                    f'option={index}, state=none'
                )
                return True
        logger.warning(
            'Chess grigri refresh was not confirmed: '
            f'option={index}, none marker did not appear'
        )
        return False

    def _best_refreshable_grigri_option(
        self,
        options: list[dict],
    ) -> tuple[dict, bool]:
        """同分低分选项优先挑仍有刷新次数的位置。"""
        best_key = max(item['selection_key'] for item in options)
        tied = [
            item for item in options if item['selection_key'] == best_key
        ]
        refreshable = [
            item
            for item in tied
            if (
                item['score'] < self.GRIGRI_REFRESH_SCORE_THRESHOLD
                and self.appear(getattr(
                    self,
                    f'I_GRIGRI_FRESH_DONE_{item["index"]}',
                ))
            )
        ]
        if refreshable:
            return random.choice(refreshable), True
        return random.choice(tied), False

    def select_grigri(self) -> bool:
        """识别、评分并选择符咒；低分时对目标选项刷新一次。"""
        if not self.appear(self.I_SELECT_GRIGRI):
            return False

        options = self._recognize_grigri_options()
        selected = None
        for _ in range(self.GRIGRI_REFRESH_MAXIMUM):
            selected, refreshable = (
                self._best_refreshable_grigri_option(options)
            )
            if not refreshable:
                break
            if not self._refresh_grigri_option(selected):
                break
            options = self._recognize_grigri_options()
        else:
            selected, _ = self._best_refreshable_grigri_option(options)

        if selected is None:
            selected = self._best_grigri_option(options)

        selected_rule = selected['rule']
        deadline = time.monotonic() + self.GRIGRI_SELECT_TIMEOUT
        attempts = 0
        logger.debug(
            f'Chess grigri option locked: option={selected["index"]}, '
            f'name={selected["name"] or "未知"}, '
            f'category={selected["category"]}, score={selected["score"]:g}; '
            'retry until selection panel closes'
        )
        while time.monotonic() < deadline:
            self.screenshot()
            if not self.appear(self.I_SELECT_GRIGRI):
                logger.debug(
                    'Chess grigri selection confirmed: '
                    f'option={selected["index"]}, attempts={attempts}'
                )
                return True
            attempts += 1
            self.click(selected_rule)
            time.sleep(self.GRIGRI_SELECT_RETRY_INTERVAL)

        self.screenshot()
        if not self.appear(self.I_SELECT_GRIGRI):
            return True
        logger.warning(
            'Chess grigri selection did not close after repeated clicks: '
            f'option={selected["index"]}, attempts={attempts}'
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
        """以阶数为式神容量；荒川金鱼出现后额外增加一个单位位。"""
        count = self._read_shikigami_count()
        level = self._read_level()
        if count is None or level is None:
            logger.warning(
                'Chess lineup capacity unavailable: '
                f'count={count}, level={level}'
            )
            return None

        current = count['current']
        goldfish_present = (
            getattr(self, '_arakawa_goldfish_current_position', None)
            is not None
        )
        capacity = level + int(goldfish_present)
        full = current >= capacity
        logger.debug(
            'Chess lineup capacity by level: '
            f'current={current}, capacity={capacity}, level={level}, '
            f'arakawa_goldfish={goldfish_present}, full={full}, '
            f'count_ocr=[{count["raw"]}]'
        )
        return {
            'current': current,
            'capacity': capacity,
            'level': level,
            'arakawa_goldfish': goldfish_present,
            'full': full,
            'count': count,
        }

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
        """读取剩余时间；第二套布局复用第一套阶段框中的数字。"""
        primary_raw, use_alternate_layout = (
            self._read_primary_round_layout()
        )
        raw = (
            primary_raw
            if use_alternate_layout
            else self._normalize_ocr_text(
                self.O_NOW_TIME.ocr(self.device.image)
            )
        )
        matched = re.search(r'\d+', raw)
        if matched is None:
            logger.warning(f'Chess remaining time OCR invalid: [{raw}]')
            return None
        remaining = int(matched.group(0))
        logger.debug(
            f'Chess remaining time: [{raw}] -> {remaining}, '
            f'alternate_layout={use_alternate_layout}'
        )
        return remaining

    def _read_game_rank(self) -> tuple[int | None, str]:
        """读取结算页“第几名”，兼容阿拉伯数字和中文数字。"""
        raw = self._normalize_ocr_text(self.O_RANK.ocr(self.device.image))
        matched = re.search(r'第?([1-8])名?', raw)
        if matched is not None:
            return int(matched.group(1)), raw

        chinese_digits = {
            '一': 1,
            '二': 2,
            '三': 3,
            '四': 4,
            '五': 5,
            '六': 6,
            '七': 7,
            '八': 8,
        }
        for character, rank in chinese_digits.items():
            if character in raw:
                return rank, raw
        return None, raw

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
