import re
from module.logger import logger

from datetime import datetime, timedelta

from tasks.SixRealms.moon_sea.map import MoonSeaMap
from tasks.SixRealms.moon_sea.l101 import MoonSeaL101
from tasks.SixRealms.moon_sea.l102 import MoonSeaL102
from tasks.SixRealms.moon_sea.l103 import MoonSeaL103
from tasks.SixRealms.moon_sea.l104 import MoonSeaL104
from tasks.SixRealms.moon_sea.l105 import MoonSeaL105
from tasks.SixRealms.moon_sea.common import MoonSeaType


class MoonSea(MoonSeaMap, MoonSeaL101, MoonSeaL102, MoonSeaL103, MoonSeaL104, MoonSeaL105):

    @property
    def _conf(self):
        return self.config.model.six_realms.six_realms_gate

    def run_moon_sea(self):
        self.cnt_skill101 = 1
        self._start()
        while True:
            self.screenshot()
            if not self.in_main():
                continue
            if self.appear(self.I_BOSS_FIRE):  # 最后boss
                self.boss_team_lock()
                if self.boss_battle():
                    break
                continue
            remain_turns = self.O_REMAIN_TURNS.ocr_single(self.device.image)
            match = re.search(r'\d{1,2}', remain_turns)
            isl_num = 0
            if self.contains_any_char(remain_turns, chars='回合') and match:
                isl_num = int(match.group())
            # 如果还剩1回合, 且当前不是商店, 并且技能没满和金币足够就开启商店
            if isl_num == 1 and not self.appear(self.I_MS_LAND_SHOP) and self.cnt_skill101 < 5 and self.coin_num >= 300:
                self.activate_store()
            # 优先级：商店 > 神秘 > 混沌 > 星之屿 > 战斗
            elif self.appear(self.I_MS_LAND_SHOP):
                if not self.enter_island(self.I_MS_LAND_SHOP):
                    continue
                self.run_l101()
            elif self.appear(self.I_MS_LAND_MYSTERY):
                if not self.enter_island(self.I_MS_LAND_MYSTERY):
                    continue
                self.run_l102()
            elif self.appear(self.I_MS_LAND_CHAOS):
                if not self.enter_island(self.I_MS_LAND_CHAOS):
                    continue
                self.run_l103()
            elif self.appear(self.I_MS_LAND_STAR):
                if not self.enter_island(self.I_MS_LAND_STAR):
                    continue
                self.run_l105()
            elif self.appear(self.I_MS_LAND_FIRE):
                if not self.enter_island(self.I_MS_LAND_FIRE):
                    continue
                self.run_l104()
            self.wait_animate_stable(self.C_MAIN_ANIMATE_KEEP, timeout=1.5)

    def _continue(self):
        logger.warning('Moon Sea Continue')
        while 1:
            self.screenshot()
            if self.in_main():
                break
            if self.appear_then_click(self.I_MCONINUE, interval=1):
                continue

    def _start(self):
        logger.hr('Moon Sea', 1)
        while 1:
            self.screenshot()
            if self.appear(self.I_MSTART):
                break
            if self.appear_then_click(self.I_MENTER, interval=1):
                continue
            if self.appear(self.I_MCONINUE):
                self._continue()
                return
        logger.info("Ensure select ShouZu")
        while 1:
            self.screenshot()
            if self.appear(self.I_MSHOUZU):
                break
            if self.appear_then_click(self.I_MSHUTEN, interval=3):
                continue
            if self.appear_then_click(self.I_MSHOUZU_SELECT, interval=1):
                continue
        logger.info("Ensure selected ShouZu")
        while 1:
            self.screenshot()
            if self.appear(self.I_PREPARE_BATTLE):
                break
            if self.appear_then_click(self.I_MSTART_UNCHECK, interval=0.6):
                continue
            if self.appear_then_click(self.I_UI_CONFIRM, interval=1):
                continue
            if self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1):
                continue
            if self.appear_then_click(self.I_MSKIP, interval=1.5):
                continue
            if self.appear_then_click(self.I_MSTART, interval=3):
                continue
            if self.appear_then_click(self.I_MSTART_CONFIRM, interval=3):
                continue
            if self.appear_then_click(self.I_MSTART_CONFIRM2, interval=3):
                continue
            if self.appear_then_click(self.I_MCONINUE, interval=3):
                continue
        logger.info("Start Roguelike")
        while 1:
            self.screenshot()
            if self.appear(self.I_M_STORE):
                break
            if self.appear_then_click(self.I_MFIRST_SKILL, interval=1):
                continue
        # 选中第一个柔风
        logger.info("Select first skill")

    def boss_team_lock(self):
        while 1:
            self.screenshot()
            if self.appear(self.I_BOSS_TEAM_LOCK):
                break
            if self.appear_then_click(self.I_BOSS_TEAM_UNLOCK, interval=2):
                logger.info('Click lock Boss Team')
                continue

    def boss_battle(self) -> bool:
        logger.hr('Boss Battle')
        self.ui_click_until_disappear(self.I_BOSS_FIRE, interval=1)
        self.device.stuck_record_clear()
        self.device.stuck_record_add('BATTLE_STATUS_S')
        while 1:
            self.screenshot()
            if self.appear(self.I_BOSS_SHARE):
                break
            if self.appear(self.I_BOSS_BATTLE_GIVEUP):
                # 打boss失败了
                logger.warning('Boss battle give up')
                self.ui_click_until_disappear(self.I_BOSS_BATTLE_GIVEUP, interval=1)
                continue
            if self.appear(self.I_BOSS_USE_DOUBLE, interval=1):
                # 双倍奖励
                logger.info('Double reward')
                self.ui_get_reward(self.I_BOSS_USE_DOUBLE)
            if self.ui_reward_appear_click():
                continue
            if self.appear_then_click(self.I_BOSS_GET_EXP, interval=1):
                logger.info('Get EXP')
                continue
            if self.appear_then_click(self.I_UI_CANCEL, interval=1):
                # 取消购买 万相赐福
                continue
            if self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1):
                continue
            if self.appear_then_click(self.I_BOSS_SKIP, interval=1):
                # 第二个boss
                self.device.stuck_record_clear()
                self.device.stuck_record_add('BATTLE_STATUS_S')
                continue
        logger.info('Boss battle end')
        if self.wait_until_appear(self.I_BOSS_SHUTU, wait_time=20):
            self.ui_click(self.I_BOSS_SHUTU, stop=self.I_MSTART)
        return True


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('日常1')
    d = Device(c)
    t = MoonSea(c, d)
    t.screenshot()

    t.run_moon_sea()
