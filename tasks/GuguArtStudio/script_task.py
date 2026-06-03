# This Python file uses the following encoding: utf-8
# @author AzurTian
import time

import random
from module.base.timer import Timer
from module.exception import TaskEnd
from module.logger import logger
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.GameUi.game_ui import GameUi
from tasks.GuguArtStudio.assets import GuguArtStudioAssets
from tasks.GuguArtStudio.config import GuguArtStudio
import tasks.GuguArtStudio.page as pages


class ScriptTask(GeneralBattle, GameUi, SwitchSoul, GuguArtStudioAssets):
    """ 呱呱画室 """

    conf: GuguArtStudio = None
    page_act_list_gugu_act = None

    def run(self):
        self.conf = self.config.gugu_art_studio
        self.switch_soul()
        self.goto_page(pages.page_gugu_fire)
        unknown_page_seconds = 8
        unknown_page_timer = Timer(unknown_page_seconds)
        max_submit = random.randint(2, 3)
        while True:
            self.screenshot()
            if max_submit <= 0:
                logger.info('Submit paint success, exit')
                break
            current_page = self.get_current_page()
            match current_page:
                case None:
                    time.sleep(0.5)
                case pages.page_gugu:
                    unknown_page_timer = Timer(unknown_page_seconds)
                    if self.appear_then_click(self.I_SUBMIT_PAINT, interval=0.8):
                        max_submit -= 1
                        self.get_reward()
                case pages.page_gugu_fire:
                    unknown_page_timer = Timer(unknown_page_seconds)
                    if self.appear_then_click(self.I_GOTO_SUBMIT):
                        logger.info('Get paint finish, go to submit paint')
                        continue
                    if self.appear(self.I_GAS_CANNOT_FIRE):  # 无法挑战则退出到提交颜料页面
                        logger.info('Cannot fire, go to submit paint')
                        self.goto_page(pages.page_gugu)
                        continue
                    self.switch_lock()
                    if self.appear_then_click(self.I_GAS_CAN_FIRE, interval=1.2):  # 点击挑战
                        self.run_general_battle(config=self.conf.general_battle_config, exit_matcher=pages.page_gugu_fire)
                case _:
                    if not unknown_page_timer.started():
                        unknown_page_timer.start()
                    if unknown_page_timer.reached():
                        self.goto_page(pages.page_gugu_fire)
                        unknown_page_timer = Timer(unknown_page_seconds)
        self.goto_page(pages.page_main)
        self.set_next_run(task='GuguArtStudio', success=True, finish=True)
        raise TaskEnd

    def switch_lock(self):
        if self.conf.general_battle_config.lock_team_enable:
            self.ui_click(self.I_GAS_UNLOCK, self.I_GAS_LOCK)
            return
        self.ui_click(self.I_GAS_LOCK, self.I_GAS_UNLOCK)

    def switch_soul(self):
        """切换御魂"""
        if self.conf.switch_soul_config.enable:
            self.goto_page(pages.page_shikigami_records)
            self.run_switch_soul(self.conf.switch_soul_config.switch_group_team)
        if self.conf.switch_soul_config.enable_switch_by_name:
            self.goto_page(pages.page_shikigami_records)
            self.run_switch_soul_by_name(self.conf.switch_soul_config.group_name,
                                         self.conf.switch_soul_config.team_name)

    def get_reward(self):
        logger.hr('Get gugu reward', 3)
        reward_click = [self.C_GAS_REWARD_1, self.C_GAS_REWARD_2, self.C_GAS_REWARD_3, self.C_GAS_REWARD_4, self.C_GAS_REWARD_5]
        for click in reward_click:
            self.I_GAS_REWARD_LOCK.roi_back = click.roi_back
            self.I_GAS_ALREADY_GET_REWARD.roi_back = click.roi_back
            self.screenshot()
            if self.appear(self.I_GAS_REWARD_LOCK):
                logger.info(f'Skip {click.name} on lock')
                break
            if self.appear(self.I_GAS_ALREADY_GET_REWARD):
                logger.info(f'Skip {click.name} on already get')
                continue
            logger.info(f'Get {click.name}')
            self.ui_get_reward(click, click_interval=2.5)
            break
        logger.info('Get gugu reward done')


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas3')
    d = Device(c)
    t = ScriptTask(c, d)
    t.screenshot()

    t.run()
