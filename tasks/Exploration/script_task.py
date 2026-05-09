# This Python file uses the following encoding: utf-8
# @author AzurTian
import time
from datetime import datetime

from module.logger import logger
from module.base.timer import Timer
from tasks.Exploration.base import BaseExploration, Scene
from tasks.Exploration.config import AutoRotate, UserStatus, ExplorationLevel
import tasks.Exploration.page as pages


class ScriptTask(BaseExploration):
    
    def run(self):
        logger.hr('exploration')
        self.pre_process()
        match self._config.exploration_config.user_status:
            case UserStatus.ALONE:
                self.run_alone()
            case UserStatus.LEADER:
                self.run_leader()
            case UserStatus.MEMBER:
                self.run_member()
            case _:
                self.run_alone()
        self.post_process()
        
    def run_alone(self):
        logger.hr('alone')
        self.goto_page(pages.page_exp_main)
        while True:
            self.screenshot()
            current_page = self.get_current_page()
            if self.check_exit(current_page):
                return
            match current_page:
                case None:
                    time.sleep(0.5)
                case pages.page_exp_main:
                    if self.collect_reward():
                        continue
                    self.switch_rotate()
                    fire_button = self.get_fire_button()
                    if fire_button is not None:
                        self.fire(fire_button)
                        continue
                    if self.arrive_end() and self.fire_monster_type != 'boss':  # 探索已经到底且当前不是boss
                        self.goto_page(pages.page_exp_entrance)
                        continue
                    self.swipe(self.S_SWIPE_BACKGROUND_RIGHT, interval=1.5)
                case pages.page_exploration | pages.page_exp_entrance:
                    self.collect_treasure_box()
                    self.fire_monster_type = ''  # 入口处重置怪物类型
                    self.goto_page(pages.page_exp_main)
                case pages.page_battle_prepare | pages.page_battle:
                    self.run_general_battle(self._config.general_battle_config, exit_matcher=pages.page_exp_main)
                case _:
                    if not self.unknown_page_timer.started():
                        self.unknown_page_timer.start()
                    if self.unknown_page_timer.reached():
                        self.goto_page(pages.page_exp_main)
                        self.unknown_page_timer = Timer(self.unknown_page_seconds)

    def run_leader(self):
        logger.hr('leader')
        leave_time_seconds = 3
        friend_leave_timer = Timer(leave_time_seconds)
        while True:
            self.screenshot()
            current_page = self.get_current_page()
            if self.check_exit(current_page):
                return
            if self.check_and_invite(False):
                continue
            match current_page:
                case None:
                    time.sleep(0.5)
                case pages.page_exp_entrance:
                    self.enter_team()
                case pages.page_battle_team:
                    if self.run_invite(self._config.invite_config, self.current_count == 0):
                        continue
                    logger.warning('Invite failed, quit')
                    return
                case pages.page_exp_main:
                    if self.collect_reward():
                        continue
                    if not self.appear(self.I_TEAM_EMOJI):  # 中途有人跑路
                        if friend_leave_timer.started() and friend_leave_timer.reached():
                            logger.warning('Mate disappeared, quit')
                            self.quit_explore()
                            continue
                        if not friend_leave_timer.started():
                            logger.warning('Mate disappear, waiting for mate')
                            friend_leave_timer.start()
                        continue
                    friend_leave_timer = Timer(leave_time_seconds)
                    self.switch_rotate()
                    fire_button = self.get_fire_button()
                    if fire_button is not None:
                        self.fire(fire_button)
                        continue
                    if self.arrive_end() and self.fire_monster_type != 'boss':  # 探索已经到底且当前不是boss
                        self.quit_explore()
                        continue
                    self.swipe(self.S_SWIPE_BACKGROUND_RIGHT, interval=1.5)
                case pages.page_battle_prepare | pages.page_battle:
                    self.run_general_battle(self._config.general_battle_config, exit_matcher=pages.page_exp_main)
                case _:
                    self.collect_treasure_box()
                    self.fire_monster_type = ''  # 重置怪物类型
                    if not self.unknown_page_timer.started():
                        self.unknown_page_timer.start()
                        continue
                    if self.unknown_page_timer.reached() or self.current_count == 0:
                        self.goto_page(pages.page_exp_entrance)
                        self.unknown_page_timer = Timer(self.unknown_page_seconds)

    def run_member(self):
        logger.hr('member')
        leave_time_seconds = 3
        friend_leave_timer = Timer(leave_time_seconds)
        start_wait_time = datetime.now()
        pre_battle_count = -1
        while True:
            self.screenshot()
            current_page = self.get_current_page()
            if pre_battle_count != self.current_count and self.check_exit(current_page):
                return
            pre_battle_count = self.current_count
            if datetime.now() - start_wait_time > self._config.invite_config.wait_time_v:
                logger.warning('Wait timer reached')
                return
            self.device.stuck_record_clear()
            if self.check_then_accept():
                continue
            match current_page:
                case None | pages.page_battle_team:
                    time.sleep(0.5)
                case pages.page_exp_main:
                    if self.collect_reward():
                        continue
                    if not self.appear(self.I_TEAM_EMOJI):  # 中途有人跑路
                        if friend_leave_timer.started() and friend_leave_timer.reached():
                            logger.warning('Mate disappeared, quit')
                            self.quit_explore()
                            continue
                        if not friend_leave_timer.started():
                            logger.warning('Mate disappear, waiting for mate')
                            friend_leave_timer.start()
                        continue
                    friend_leave_timer = Timer(leave_time_seconds)
                    self.switch_rotate()
                case pages.page_exploration | pages.page_exp_entrance:
                    self.collect_treasure_box()
                case pages.page_battle_prepare | pages.page_battle:
                    self.run_general_battle(self._config.general_battle_config, exit_matcher=pages.page_exp_main)
                    start_wait_time = datetime.now()
                case _:
                    if self.current_count == 0:  # 还没有进攻过
                        self.goto_page(pages.page_exploration)
                        continue
                    if not self.unknown_page_timer.started():
                        self.unknown_page_timer.start()
                    if self.unknown_page_timer.reached():
                        self.goto_page(pages.page_exploration)
                        self.unknown_page_timer = Timer(self.unknown_page_seconds)


if __name__ == "__main__":
    from module.config.config import Config
    from module.device.device import Device

    config = Config('丰年2')
    device = Device(config)
    t = ScriptTask(config, device)
    t.run_leader()
