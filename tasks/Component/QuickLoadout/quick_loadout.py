# This Python file uses the following encoding: utf-8
from __future__ import annotations

import ast
import difflib
import re
from dataclasses import dataclass
from time import sleep

import cv2
import numpy as np

from module.atom.click import RuleClick
from module.atom.image import RuleImage
from module.atom.ocr import RuleOcr
from module.atom.swipe import RuleSwipe
from module.base.timer import Timer
from module.logger import logger
from tasks.Component.QuickLoadout.config import (
    NamedQuickLoadoutConfig,
    QuickLoadoutConfig,
    QuickLoadoutMode,
)
from tasks.Component.SwitchSoul.assets import SwitchSoulAssets
from tasks.base_task import BaseTask


class QuickLoadoutOcr(RuleOcr):
    """适配快捷配置面板的棕色/橙色文字。"""

    def pre_process(self, image):
        return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)


@dataclass(frozen=True)
class QuickLoadoutLayout:
    """由“出战”锚点推导出的快捷配置面板运行时布局。"""

    panel: tuple[int, int, int, int]
    group_ocr: RuleOcr
    preset_ocr: RuleOcr
    group_swipe_to_top: RuleSwipe
    group_swipe_down: RuleSwipe
    preset_swipe_to_top: RuleSwipe
    preset_swipe_down: RuleSwipe


class QuickLoadout(BaseTask, SwitchSoulAssets):
    """战斗界面内的一键配置组件。

    接入任务提供入口图片、面板内“出战”锚点和面板外安全关闭区域；
    面板内部点击点、OCR 和滑动范围由锚点动态生成。
    """

    PANEL_FROM_FIGHT = (-263, -331, 551, 386)
    GROUP_OCR_ROI = (17, 7, 101, 356)
    PRESET_OCR_ROI = (145, 7, 278, 320)
    GROUP_CLICK_X = 61
    GROUP_FIRST_Y = 31
    GROUP_ROW_HEIGHT = 51
    PRESET_SELECT_X = 300
    PRESET_EQUIP_X = 482
    PRESET_NUMBER_X = 157
    PRESET_NUMBER_Y = 7
    PRESET_NUMBER_SIZE = (24, 32)
    PRESET_FIRST_Y = 26
    PRESET_ROW_HEIGHT = 96
    PRESET_FULL_VISIBLE_ROWS = 3
    PRESET_VISIBLE_SLOTS = 4

    PANEL_OPEN_TIMEOUT = 8
    PANEL_CLOSE_TIMEOUT = 5
    CONFIRM_TIMEOUT = 1.5
    MAX_GROUP_SWIPES = 10
    MAX_PRESET_SWIPES = 15
    STAGE_NAME_MATCH_THRESHOLD = 0.75

    @staticmethod
    def _parse_custom_presets(
        value: str,
    ) -> dict[str, tuple[int, int] | tuple[str, str]]:
        presets = {}
        for raw_item in re.split(r'[;；]+', value):
            item = raw_item.strip()
            if not item:
                continue
            parts = re.split(r'[:：]', item, maxsplit=1)
            if len(parts) != 2 or not parts[0].strip():
                raise ValueError(f'Invalid custom quick loadout item: {item}')
            stage_name, target_text = parts[0].strip(), parts[1].strip()
            try:
                target = ast.literal_eval(target_text)
            except (SyntaxError, ValueError) as exc:
                raise ValueError(f'Invalid custom quick loadout target: {item}') from exc
            if not isinstance(target, (tuple, list)) or len(target) != 2:
                raise ValueError(f'Custom quick loadout target must contain two values: {item}')
            group, preset = target
            is_number_target = (
                isinstance(group, int) and not isinstance(group, bool)
                and isinstance(preset, int) and not isinstance(preset, bool)
            )
            is_ocr_target = isinstance(group, str) and isinstance(preset, str)
            if not is_number_target and not is_ocr_target:
                raise ValueError(
                    f'Custom quick loadout target must be two integers or two strings: {item}'
                )
            if is_number_target and (group < 1 or preset < 1):
                raise ValueError(f'Custom quick loadout numbers must be positive: {item}')
            if is_ocr_target:
                group, preset = group.strip(), preset.strip()
                if not group or not preset:
                    raise ValueError(f'Custom quick loadout target cannot be empty: {item}')
            presets[stage_name] = (group, preset)
        return presets

    def _read_quick_loadout_stage_name(self, name_ocr: RuleOcr) -> str:
        best = ''
        for attempt in range(1, 4):
            self.screenshot()
            value = str(name_ocr.ocr(self.device.image)).strip()
            if len(self._normalize_name(value)) > len(self._normalize_name(best)):
                best = value
            logger.info(f'Quick loadout stage OCR {attempt}/3: {value}')
            if best:
                break
            sleep(0.3)
        return best

    @classmethod
    def _match_custom_preset(cls, stage_name, presets):
        """显式关卡名优先；没有显式匹配时使用 ALL。"""
        best_name = None
        best_target = None
        best_score = 0.0
        all_target = None
        for candidate, target in presets.items():
            if candidate.upper() == 'ALL':
                all_target = target
                continue
            score = cls._name_similarity(stage_name, candidate)
            if score > best_score:
                best_name, best_target, best_score = candidate, target, score
        if best_target is not None and best_score >= cls.STAGE_NAME_MATCH_THRESHOLD:
            return best_name, best_target, best_score
        if all_target is not None:
            return 'ALL', all_target, 1.0
        return None, None, 0.0

    def _resolve_named_quick_loadout(
        self,
        config: NamedQuickLoadoutConfig,
        name_ocr: RuleOcr,
    ) -> QuickLoadoutConfig:
        stage_name = self._read_quick_loadout_stage_name(name_ocr)
        if not self._normalize_name(stage_name):
            logger.warning('Quick loadout stage name OCR is empty, use default preset')
            return config

        try:
            presets = self._parse_custom_presets(config.custom_preset)
        except ValueError as exc:
            logger.warning(str(exc))
            return config

        best_name, best_target, best_score = self._match_custom_preset(stage_name, presets)
        if best_target is None:
            logger.info(f'No custom quick loadout for stage {stage_name}, use default preset')
            return config

        group, preset = best_target
        if isinstance(group, int) and isinstance(preset, int):
            updates = {
                'mode': QuickLoadoutMode.NUMBER,
                'group_number': group,
                'preset_number': preset,
            }
        else:
            updates = {
                'mode': QuickLoadoutMode.OCR,
                'group_name': group,
                'preset_name': preset,
            }
        logger.info(
            f'Custom quick loadout matched stage {stage_name} -> '
            f'({group}, {preset}) [{best_score:.2f}]'
        )
        return config.model_copy(update=updates)

    @staticmethod
    def _offset_roi(panel, relative):
        return panel[0] + relative[0], panel[1] + relative[1], relative[2], relative[3]

    @staticmethod
    def _result_center_y(result, roi_top: int) -> int:
        return int(round(float(np.mean(result.box[:, 1])))) + roi_top

    @staticmethod
    def _normalize_name(value: str) -> str:
        return re.sub(r'[\s·•,，.。:：_\-—]+', '', str(value)).strip()

    @classmethod
    def _name_similarity(cls, actual: str, expected: str) -> float:
        actual = cls._normalize_name(actual)
        expected = cls._normalize_name(expected)
        if not actual or not expected:
            return 0.0
        if expected in actual or actual in expected:
            return 1.0
        return difflib.SequenceMatcher(None, actual, expected).ratio()

    def _build_quick_loadout_layout(self, fight_anchor: RuleImage) -> QuickLoadoutLayout:
        anchor_x, anchor_y = fight_anchor.roi_front[:2]
        dx, dy, panel_width, panel_height = self.PANEL_FROM_FIGHT
        panel = anchor_x + dx, anchor_y + dy, panel_width, panel_height
        x, y, width, height = panel
        if x < 0 or y < 0 or x + width > 1280 or y + height > 720:
            raise ValueError(f'Quick loadout panel is outside screen: {panel}')

        group_roi = self._offset_roi(panel, self.GROUP_OCR_ROI)
        preset_roi = self._offset_roi(panel, self.PRESET_OCR_ROI)
        group_ocr = QuickLoadoutOcr(roi=group_roi, area=group_roi, mode='Full', method='Default', keyword='', name='quick_loadout_group_name')
        preset_ocr = QuickLoadoutOcr(roi=preset_roi, area=preset_roi, mode='Full', method='Default', keyword='', name='quick_loadout_preset_name')
        group_swipe_to_top = RuleSwipe(roi_front=(x + 55, y + 105, 25, 20), roi_back=(x + 55, y + 285, 25, 20), mode='default', name='quick_loadout_group_to_top')
        group_swipe_down = RuleSwipe(roi_front=(x + 55, y + 285, 25, 20), roi_back=(x + 55, y + 105, 25, 20), mode='default', name='quick_loadout_group_down')
        preset_swipe_to_top = RuleSwipe(roi_front=(x + 355, y + 105, 30, 20), roi_back=(x + 355, y + 280, 30, 20), mode='default', name='quick_loadout_preset_to_top')
        preset_swipe_down = RuleSwipe(roi_front=(x + 355, y + 280, 30, 20), roi_back=(x + 355, y + 105, 30, 20), mode='default', name='quick_loadout_preset_down')
        return QuickLoadoutLayout(panel, group_ocr, preset_ocr, group_swipe_to_top, group_swipe_down, preset_swipe_to_top, preset_swipe_down)

    def _open_quick_loadout(self, entry: RuleImage, fight_anchor: RuleImage) -> bool:
        logger.info('Open quick loadout panel')
        timer = Timer(self.PANEL_OPEN_TIMEOUT).start()
        while not timer.reached():
            self.screenshot()
            if self.appear(fight_anchor):
                return True
            self.appear_then_click(entry, interval=1)
        logger.warning('Cannot open quick loadout panel')
        return False

    def _dismiss_quick_loadout(self, fight_anchor: RuleImage, dismiss: RuleClick) -> bool:
        timer = Timer(self.PANEL_CLOSE_TIMEOUT).start()
        while not timer.reached():
            self.screenshot()
            if not self.appear(fight_anchor):
                return True
            self.click(dismiss, interval=1)
        logger.warning('Cannot close quick loadout panel safely')
        return False

    def _rewind_list(self, ocr: RuleOcr, swipe: RuleSwipe, max_swipes: int) -> None:
        previous_text = None
        previous_visual = None
        stable_count = 0
        for attempt in range(max_swipes):
            self.screenshot()
            results = ocr.detect_and_ocr(self.device.image, logDisplay=False)
            normalized_results = []
            for result in results:
                normalized = self._normalize_name(result.ocr_text)
                if normalized:
                    normalized_results.append(normalized)
            current_text = tuple(sorted(normalized_results))

            x, y, width, height = ocr.roi
            current_visual = cv2.cvtColor(
                self.device.image[y:y + height, x:x + width],
                cv2.COLOR_RGB2GRAY,
            )
            current_visual = cv2.resize(current_visual, (64, 64))

            text_stable = bool(
                current_text
                and previous_text is not None
                and current_text == previous_text
            )
            visual_stable = bool(
                previous_visual is not None
                and cv2.absdiff(current_visual, previous_visual).mean() < 2.5
            )
            if text_stable or visual_stable:
                stable_count += 1
                if stable_count >= 2:
                    logger.info(f'Quick loadout list reached top after {attempt} swipes')
                    return
            else:
                stable_count = 0

            previous_text = current_text
            previous_visual = current_visual
            self.swipe(swipe)
            # Rewinding is an intentional bounded repeated action. Keep other
            # click history intact while preventing the global loop guard from
            # treating these swipes as an uncontrolled click loop.
            self.device.click_record_remove(swipe.name)
            sleep(0.45)

        logger.warning(f'Quick loadout rewind reached safety limit: {max_swipes}')

    def _find_name_y(self, ocr: RuleOcr, target: str, results=None):
        best_y = None
        best_score = 0.0
        if results is None:
            results = ocr.detect_and_ocr(self.device.image)
        for result in results:
            score = self._name_similarity(result.ocr_text, target)
            if score > best_score:
                best_score = score
                best_y = self._result_center_y(result, ocr.roi[1])
        return best_y, best_score

    def _find_visible_preset_number_y(self, layout: QuickLoadoutLayout, target: int):
        panel_x, panel_y, _, _ = layout.panel
        number_width, number_height = self.PRESET_NUMBER_SIZE
        for slot in range(self.PRESET_VISIBLE_SLOTS):
            roi = (
                panel_x + self.PRESET_NUMBER_X,
                panel_y + self.PRESET_NUMBER_Y + slot * self.PRESET_ROW_HEIGHT,
                number_width,
                number_height,
            )
            number_ocr = RuleOcr(roi=roi, area=roi, mode='Digit', method='Default', keyword='', name=f'quick_loadout_preset_number_{slot + 1}')
            if number_ocr.ocr(self.device.image) == target:
                return panel_y + self.PRESET_FIRST_Y + slot * self.PRESET_ROW_HEIGHT
        return None

    def _select_group(self, layout: QuickLoadoutLayout, config: QuickLoadoutConfig) -> bool:
        self._rewind_list(layout.group_ocr, layout.group_swipe_to_top, self.MAX_GROUP_SWIPES)
        panel_x, panel_y, _, _ = layout.panel
        if config.mode == QuickLoadoutMode.NUMBER:
            y = panel_y + self.GROUP_FIRST_Y + (config.group_number - 1) * self.GROUP_ROW_HEIGHT
            self.device.click(panel_x + self.GROUP_CLICK_X, y, control_name='QUICK_LOADOUT_GROUP')
            sleep(0.6)
            return True

        previous = None
        stable_count = 0
        for _ in range(self.MAX_GROUP_SWIPES + 1):
            self.screenshot()
            results = layout.group_ocr.detect_and_ocr(self.device.image, logDisplay=False)
            current = tuple(result.ocr_text for result in results)
            y, score = self._find_name_y(layout.group_ocr, config.group_name, results)
            if y is not None and score >= 0.55:
                self.device.click(panel_x + self.GROUP_CLICK_X, y, control_name='QUICK_LOADOUT_GROUP_OCR')
                sleep(0.6)
                return True
            stable_count = stable_count + 1 if current and current == previous else 0
            if stable_count >= 2:
                break
            previous = current
            self.swipe(layout.group_swipe_down)
            sleep(0.6)
        logger.warning(f'Quick loadout group not found: {config.group_name}')
        return False

    def _select_preset_row(self, layout: QuickLoadoutLayout, config: QuickLoadoutConfig):
        self._rewind_list(layout.preset_ocr, layout.preset_swipe_to_top, self.MAX_PRESET_SWIPES)
        panel_y = layout.panel[1]
        if config.mode == QuickLoadoutMode.NUMBER and config.preset_number <= self.PRESET_FULL_VISIBLE_ROWS:
            return panel_y + self.PRESET_FIRST_Y + (config.preset_number - 1) * self.PRESET_ROW_HEIGHT

        previous = None
        stable_count = 0
        target_label = str(config.preset_number) if config.mode == QuickLoadoutMode.NUMBER else config.preset_name
        for _ in range(self.MAX_PRESET_SWIPES + 1):
            self.screenshot()
            results = layout.preset_ocr.detect_and_ocr(self.device.image, logDisplay=False)
            current = tuple(result.ocr_text for result in results)
            if config.mode == QuickLoadoutMode.NUMBER:
                y = self._find_visible_preset_number_y(layout, config.preset_number)
                score = 1.0 if y is not None else 0.0
            else:
                y, score = self._find_name_y(layout.preset_ocr, config.preset_name, results)
            if y is not None and score >= 0.55:
                return y
            stable_count = stable_count + 1 if current and current == previous else 0
            if stable_count >= 2:
                break
            previous = current
            self.swipe(layout.preset_swipe_down)
            sleep(0.6)
        logger.warning(f'Quick loadout preset not found: {target_label}')
        return None

    def _equip_quick_loadout_souls(self, layout: QuickLoadoutLayout, row_y: int) -> None:
        panel_x = layout.panel[0]
        self.device.click(panel_x + self.PRESET_EQUIP_X, row_y, control_name='QUICK_LOADOUT_EQUIP_SOUL')
        timer = Timer(self.CONFIRM_TIMEOUT).start()
        while not timer.reached():
            self.screenshot()
            if not self.appear(self.I_SOU_SWITCH_SURE):
                sleep(0.15)
                continue
            self.ui_click_until_disappear(self.I_SOU_SWITCH_SURE, interval=0.6)
            return
        logger.info('Quick loadout soul confirmation did not appear; preset may already be equipped')

    def _deploy_quick_loadout(self, layout, fight_anchor, dismiss, row_y) -> bool:
        panel_x = layout.panel[0]
        self.device.click(panel_x + self.PRESET_SELECT_X, row_y, control_name='QUICK_LOADOUT_PRESET')
        sleep(0.4)
        self.click(fight_anchor)
        timer = Timer(self.PANEL_CLOSE_TIMEOUT).start()
        while not timer.reached():
            self.screenshot()
            if not self.appear(fight_anchor):
                logger.info('Quick loadout deployed')
                return True
            sleep(0.2)
        logger.warning('Quick loadout deploy did not close panel')
        self._dismiss_quick_loadout(fight_anchor, dismiss)
        return False

    def run_quick_loadout(
        self,
        config: QuickLoadoutConfig,
        *,
        entry: RuleImage,
        fight_anchor: RuleImage,
        dismiss: RuleClick,
        name_ocr: RuleOcr | None = None,
    ) -> bool:
        """装配目标预设御魂并将该预设上阵。"""
        if not config.enable:
            return True
        if isinstance(config, NamedQuickLoadoutConfig) and config.custom_preset_enable:
            if name_ocr is None:
                logger.warning('Named quick loadout enabled without a stage-name OCR rule')
            else:
                config = self._resolve_named_quick_loadout(config, name_ocr)
        config.validate_target()
        logger.hr('Quick loadout', 2)
        if not self._open_quick_loadout(entry, fight_anchor):
            return False
        try:
            layout = self._build_quick_loadout_layout(fight_anchor)
            if not self._select_group(layout, config):
                self._dismiss_quick_loadout(fight_anchor, dismiss)
                return False
            row_y = self._select_preset_row(layout, config)
            if row_y is None:
                self._dismiss_quick_loadout(fight_anchor, dismiss)
                return False
            self._equip_quick_loadout_souls(layout, row_y)
            return self._deploy_quick_loadout(layout, fight_anchor, dismiss, row_y)
        except Exception:
            self._dismiss_quick_loadout(fight_anchor, dismiss)
            raise
