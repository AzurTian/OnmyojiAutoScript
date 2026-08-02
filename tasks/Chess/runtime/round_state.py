"""Chess runtime: round OCR, board occupancy, and state readers."""

# This Python file uses the following encoding: utf-8

import random
import re
import time

from module.logger import logger


class ChessRoundStateMixin:
    """Internal mixin; use through ``ScriptTask`` only."""

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

    def _read_round_resources(self, round_no: int) -> dict:
        """关闭商店后以同一帧记录新回目的资源与存活人数。"""
        if not self._ensure_shop_closed(
            allowed_modes=('备', '战', '鬼', '待'),
        ):
            logger.warning(
                'Chess round snapshot could not confirm shop closed; '
                'capture current screen as fallback'
            )
        # 回目快照同样服从 Buff 高优先级；处理完后再获取正式快照帧。
        if self._refresh_round_state_screenshot():
            self.screenshot()
        snapshot = {
            'round': round_no,
            'gold': self._read_shop_gold(),
            'level': self._read_level(),
            'chess_mode': self._read_chess_mode(),
            'alive_players': self._read_alive_players(),
            'hand_shikigami': self._hand_shikigami_summary(),
        }
        self._round_snapshot = snapshot
        logger.debug(
            'Chess round snapshot: '
            f'round={snapshot["round"]}, mode={snapshot["chess_mode"]}, '
            f'level={snapshot["level"]}, gold={snapshot["gold"]}, '
            f'alive_players={snapshot["alive_players"]}'
        )
        logger.info(
            'Chess round update: '
            f'round={snapshot["round"]}, gold={snapshot["gold"]}, '
            f'level={snapshot["level"]}, '
            f'alive_players={snapshot["alive_players"]}, '
            f'hand_shikigami={snapshot["hand_shikigami"]}'
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
