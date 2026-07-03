# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from time import sleep
from datetime import datetime, timedelta
from random import randint

from module.logger import logger
from module.exception import TaskEnd

from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.GameUi.default_pages import page_battle_prepare, page_battle
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_shikigami_records, page_goryou_realm, page_exploration
from tasks.GoryouRealm.config import GoryouClass
from tasks.GoryouRealm.assets import GoryouRealmAssets


class ScriptTask(GeneralBattle, GameUi, SwitchSoul, GoryouRealmAssets):

    def run(self):
        con = self.config.goryou_realm
        limit_time = con.goryou_config.limit_time
        self.limit_time: timedelta = timedelta(hours=limit_time.hour, minutes=limit_time.minute,
                                               seconds=limit_time.second)
        if con.switch_soul_config.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(con.switch_soul_config.switch_group_team)
        if con.switch_soul_config.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(con.switch_soul_config.group_name, con.switch_soul_config.team_name)
        self.goto_page(page_goryou_realm)
        match_click = {
            GoryouClass.Dark_Divine_Dragon: self.C_GR_C_1,
            GoryouClass.Dark_Hakuzousu: self.C_GR_C_2,
            GoryouClass.Dark_Black_Panther: self.C_GR_C_3,
            GoryouClass.Dark_Peacock: self.C_GR_C_4,
        }
        goryou_class = con.goryou_config.goryou_class
        if goryou_class == GoryouClass.RANDOM:
            goryou_class = {
                1: GoryouClass.Dark_Divine_Dragon,
                2: GoryouClass.Dark_Hakuzousu,
                3: GoryouClass.Dark_Black_Panther,
                4: GoryouClass.Dark_Peacock,
            }[randint(1, 4)]
        while 1:
            self.screenshot()
            if self.appear(self.I_GR_FIRE):
                logger.info('Enter GoryouRealm')
                break
            if self.click(match_click[goryou_class], interval=1):
                continue
        self.check_lock(con.general_battle_config.lock_team_enable, self.I_GR_LOCK, self.I_GR_UNLOCK)
        # 开始循环
        while True:
            self.screenshot()
            if self.current_count >= con.goryou_config.limit_count:
                logger.info('GoryouRealm count limit out')
                break
            if datetime.now() - self.start_time >= self.limit_time:
                logger.info('GoryouRealm time limit out')
                break
            if not self.enter_battle():
                break
            self.run_general_battle(config=con.general_battle_config, exit_matcher=self.I_GR_FIRE)

        self.goto_page(page_exploration)
        self.set_next_run(task='GoryouRealm', success=True, finish=True)
        raise TaskEnd

    def enter_battle(self) -> bool:
        """成功进入True, 否则False"""
        # 点击挑战
        click_max_cnt = randint(2, 4)
        while True:
            self.screenshot()
            if self.get_current_page() in (page_battle_prepare, page_battle):
                return True
            if click_max_cnt <= 0:
                logger.info('Maybe tickets not enough, exit')
                break
            if self.appear_then_click(self.I_GR_FIRE, interval=2):
                click_max_cnt -= 1
                continue
        return False

if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)
    t.screenshot()

    t.run()
