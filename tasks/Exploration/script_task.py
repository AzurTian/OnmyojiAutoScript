# This Python file uses the following encoding: utf-8
# @author AzurTian
import time
from datetime import datetime, timedelta

from module.logger import logger
from tasks.Exploration.base import BaseExploration
from tasks.Exploration.config import AutoRotate, UserStatus, ExplorationLevel
import tasks.Exploration.page as pages
from tasks.GameUi.page_definition import Page
from typing import Callable


class InviteFailedException(Exception):
    pass

class ScriptTask(BaseExploration):
    """探索"""

    def confirm_page(self, page: Page, skip_first_screenshot: bool = True) -> bool:
        """探索页面跳转更改为单帧确认"""
        self.maybe_screenshot(skip_first_screenshot)
        return self.match_page_once(page)

    def arrive_end(self) -> bool:
        # 28章直接匹配
        if self._config.exploration_config.exploration_level == ExplorationLevel.EXPLORATION_28:
            return self.appear(self.I_SWIPE_END)
        return super().arrive_end()

    @property
    def exp_page_handle_dict(self) -> dict[Page, Callable]:
        return {
            pages.page_exp_main: self.run_on_exp_main,
            pages.page_exp_settings: self.run_on_exp_settings,
            pages.page_exp_exit: self.run_on_exp_exit,
            pages.page_exp_entrance: self.run_on_exp_entrance,
            pages.page_exploration: self.run_on_exp,
            pages.page_battle_prepare: self.run_on_battle,
            pages.page_battle: self.run_on_battle,
            pages.page_battle_result: self.run_on_battle,
            pages.page_reward: lambda : self.click(pages.random_click(), interval=0.8),
            pages.page_battle_team: self.run_on_battle_team
        }

    def run(self):
        logger.hr('exploration')
        self.pre_process()
        self.exec_exp_page()
        self.post_process()

    def exec_exp_page(self):
        pages.page_battle_team_exit = self.navigator.resolve_page(pages.page_battle_team_exit)
        pages.page_battle_team_exit.connect(pages.page_exp_entrance, self.I_UI_CONFIRM, key="page_battle_team_exit->page_exp_entrance")
        while True:
            self.screenshot()
            current_page = self.get_current_page()
            if current_page is None:
                time.sleep(0.5)
                continue
            if self.check_exit(current_page):
                self.appear_then_click(self.I_UI_CANCEL, interval=0.8)  # 处理队长结束的邀请弹窗
                break
            handle = self.exp_page_handle_dict.get(current_page, None)
            if handle is None:
                self.goto_page(pages.page_exploration)
                continue
            try:
                handle()
            except InviteFailedException as e:
                logger.warning(e)
                break

    def run_on_exp_main(self):
        if self.collect_reward():
            return
        if self.user_status != UserStatus.ALONE:
            if self.fire_monster_type == 'boss':
                return
            if not self.appear(self.I_TEAM_EMOJI):
                logger.info('Friend disappeared, quit')
                self.quit_exp_main()
                return
        if self.switch_rotate() or self.user_status == UserStatus.MEMBER:
            return
        fire_button = self.get_fire_button()
        if fire_button is not None and self.fire(fire_button):
            return
        if self.fire_monster_type != 'boss' and self.swipe(self.S_SWIPE_BACKGROUND_RIGHT, interval=1.5) and self.arrive_end():
            self.quit_exp_main()

    def run_on_exp_entrance(self):
        self.collect_treasure_box()
        self.fire_monster_type = ''  # 入口处重置怪物类型
        self.need_exit = False
        match self.user_status:
            case UserStatus.LEADER:
                if self.check_and_invite(self._config.invite_config.default_invite):
                    return
                if datetime.now() - self.wait_start_time >= timedelta(seconds=10) or self.current_count == 0:
                    self.enter_team()
            case UserStatus.ALONE:
                self.goto_page(pages.page_exp_main)
            case UserStatus.MEMBER:
                self.check_then_accept()
                self.device.stuck_record_clear()

    def run_on_exp(self):
        self.fire_monster_type = ''  # 入口处重置怪物类型
        self.need_exit = False
        match self.user_status:
            case UserStatus.LEADER:
                # TODO: 队长宝箱收集(游戏问题导致邀请和宝箱出现时间不一致, 一旦先点中宝箱就会出现卡死), 当前先取消队长在探索界面的宝箱收集
                if self.check_and_invite(self._config.invite_config.default_invite):
                    return
                if datetime.now() - self.wait_start_time >= timedelta(seconds=10) or self.current_count == 0:
                    self.goto_page(pages.page_exp_entrance)
            case UserStatus.ALONE:
                self.collect_treasure_box()
                self.goto_page(pages.page_exp_main)
            case UserStatus.MEMBER:
                self.collect_treasure_box()
                self.check_then_accept()
                self.device.stuck_record_clear()

    def run_on_battle(self):
        self.run_general_battle(self._config.general_battle_config, exit_matcher=pages.page_exp_main)
        self._match_end.refresh()  # 防止同一张图多次打怪导致误以为探索结束
        self.wait_start_time = datetime.now()  # 队友等待时间重置

    def run_on_battle_team(self):
        self.need_exit = False
        match self.user_status:
            case UserStatus.LEADER:
                if self.run_invite(self._config.invite_config, self.current_count == 0):
                    return
                raise InviteFailedException('Invite failed, quit')
            case UserStatus.ALONE:
                self.goto_page(pages.page_exp_main)

    def run_on_exp_settings(self):
        if self._config.exploration_config.auto_rotate == AutoRotate.no:
            self.goto_page(pages.page_exp_main)
            return
        self.fill_shikigami()
        self.appear_then_click(self.I_E_AUTO_ROTATE_OFF, interval=0.8)

    def run_on_exp_exit(self):
        if not self.need_exit: # 不需要退出则点取消, 通常是直接在探索界面启动脚本(或退出期间在主界面再次识别到需要攻击的怪物)
            self.appear_then_click(self.I_E_EXIT_CANCEL, interval=0.8)
            return
        self.appear_then_click(self.I_E_EXIT_CONFIRM, interval=0.8)
        self.wait_start_time = datetime.now()  # 队友等待时间重置


if __name__ == "__main__":
    from module.config.config import Config
    from module.device.device import Device

    config = Config('丰年2')
    device = Device(config)
    t = ScriptTask(config, device)
    t.run()
