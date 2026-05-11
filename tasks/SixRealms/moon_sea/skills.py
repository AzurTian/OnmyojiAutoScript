import time
import re

from cached_property import cached_property

from module.logger import logger
from module.base.timer import Timer
from tasks.base_task import BaseTask
from tasks.SixRealms.assets import SixRealmsAssets


class MoonSeaSkills(BaseTask, SixRealmsAssets):
    coin_num = 0
    cnt_skill101 = 0

    def in_main(self, screenshot: bool = False):
        if screenshot:
            self.screenshot()
        if self.appear(self.I_M_STORE):
            return True
        if self.appear(self.I_M_STORE_ACTIVITY):
            return True
        if self.appear(self.I_BOSS_FIRE):
            return True
        return False

    def battle_lock_team(self):
        self.ui_click(self.I_BATTLE_TEAM_UNLOCK, self.I_BATTLE_TEAM_LOCK)
        return

    def island_battle(self):
        # 小怪战斗
        self.screenshot()
        while 1:
            self.screenshot()
            if self.appear(self.I_SKILL_REFRESH):
                break
            if self.appear(self.I_COIN):
                break
            if self.appear_then_click(self.I_NPC_FIRE, interval=1):
                self.device.stuck_record_clear()
                self.device.stuck_record_add('BATTLE_STATUS_S')
                continue
        self.device.stuck_record_clear()

    @cached_property
    def selects_button(self):
        return [
            self.I_SELECT_0,
            self.I_SELECT_1,
            self.I_SELECT_2,
            self.I_SELECT_3,
        ]

    def _select_skill(self) -> int:
        self.screenshot()
        self.wait_until_stable(self.I_SELECT_3)
        select = 3  # 从0开始计数
        button = None
        # 只选柔风
        if button is None and self.appear(self.I_SKILL101):
            self.cnt_skill101 += 1
            logger.info(f'Skill 101 level: {self.cnt_skill101}')
            button = self.I_SKILL101
        elif button is None and self.appear(self.I_SKILL105):
            logger.info(f'Skill 105 level: {self.cnt_skill101}')
            button = self.I_SKILL105
        if button is not None:
            x, y = button.front_center()
            if x < 360:
                select = 0
            elif 360 <= x < 640:
                select = 1
            elif 640 <= x < 960:
                select = 2
            else:
                select = 3
        logger.info(f'Select {select}')
        return select

    def select_skill(self):
        """战斗结束后选技能"""
        logger.info('Start select skill')
        while True:
            self.screenshot()
            if self.in_main():
                break
            if self.appear(self.I_UI_CONFIRM):
                self.ui_click_until_disappear(self.I_UI_CONFIRM)
            if self.appear(self.I_SKILL_REFRESH) and self.appear(self.I_SELECT_3) and not self.appear(self.I_COIN):
                self.coin_num = self.O_COIN_NUM.ocr(self.device.image)
                logger.info(f'Current coin: {self.coin_num}')
                select = self._select_skill()
                if self.appear_then_click(self.selects_button[select]):
                    self.wait_animate_stable(self.C_MAIN_ANIMATE_KEEP, timeout=1.5)
                    continue
            if self.appear(self.I_COIN, interval=2):
                x, y, width, height = self.I_COIN.roi_front
                self.O_EXTRA_COIN_NUM.roi = [x + 25, y + 47, width - 5, height - 23]
                extra_coin = self.O_EXTRA_COIN_NUM.ocr_digit(self.device.image)
                extra_coin = int(extra_coin) if extra_coin != "" else 0
                self.coin_num += extra_coin
                logger.info(f'Current coin: {self.coin_num}')
                self.click(self.C_UI_REWARD)
