# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import random
from time import sleep
from datetime import time, datetime, timedelta

from tasks.Component.GeneralBattle.general_battle import BattleAction, GeneralBattle
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Component.GeneralBuff.general_buff import GeneralBuff
from tasks.Component.GeneralRoom.general_room import GeneralRoom
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import any_of, page_main, page_reward, page_shikigami_records, page_soul_zones
from tasks.FallenSun.assets import FallenSunAssets
from tasks.FallenSun.config import FallenSun, UserStatus
from module.logger import logger
from module.exception import TaskEnd


class ScriptTask(GeneralBattle, GeneralInvite, GeneralBuff, GeneralRoom, GameUi, SwitchSoul, FallenSunAssets):

    def _fallen_sun_battle_key(self) -> str:
        return f"fallen_sun_{self.config.fallen_sun.fallen_sun_config.layer}"

    def _register_custom_pages(self) -> None:
        reward_page = self.navigator.resolve_page(page_reward)
        if reward_page is None:
            return
        reward_page.recognizer = any_of(self.I_GREED_GHOST, self.I_REWARD, self.I_REWARD_GOLD)

    def run(self) -> bool:
        # 御魂切换方式一
        if self.config.fallen_sun.switch_soul.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(self.config.fallen_sun.switch_soul.switch_group_team)

        # 御魂切换方式二
        if self.config.fallen_sun.switch_soul.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(self.config.fallen_sun.switch_soul.group_name,
                                         self.config.fallen_sun.switch_soul.team_name)

        limit_count = self.config.fallen_sun.fallen_sun_config.limit_count
        limit_time = self.config.fallen_sun.fallen_sun_config.limit_time
        self.current_count = 0
        self.limit_count: int = limit_count
        self.limit_time: timedelta = timedelta(hours=limit_time.hour, minutes=limit_time.minute, seconds=limit_time.second)

        self.goto_page(page_main)
        config: FallenSun = self.config.fallen_sun

        success = True
        match config.fallen_sun_config.user_status:
            case UserStatus.LEADER: success = self.run_leader()
            case UserStatus.MEMBER: success = self.run_member()
            case UserStatus.ALONE: self.run_alone()
            case UserStatus.WILD: self.run_wild()
            case _: logger.error('Unknown user status')

        # 下一次运行时间
        if success:
            self.set_next_run('FallenSun', finish=True, success=True)
        else:
            self.set_next_run('FallenSun', finish=False, success=False)

        raise TaskEnd

    def fallen_sun_enter(self) -> bool:
        logger.info('Enter fallen_sun')
        while True:
            self.screenshot()
            if self.appear(self.I_FORM_TEAM):
                return True
            if self.appear_then_click(self.I_FALLEN_SUN, interval=1):
                continue

    def check_layer(self, layer: str) -> bool:
        """
        检查挑战的层数, 并选中挑战的层
        :return:
        """
        pos = self.list_find(self.L_LAYER_LIST, layer)
        if pos:
            self.device.click(x=pos[0], y=pos[1])
            return True

    def check_lock(self, lock: bool = True) -> bool:
        """
        检查是否锁定阵容, 要求在八岐大蛇界面
        :param lock:
        :return:
        """
        logger.info('Check lock: %s', lock)
        if lock:
            while 1:
                self.screenshot()
                if self.appear(self.I_FALLEN_SUN_LOCK):
                    return True
                if self.appear_then_click(self.I_FALLEN_SUN_UNLOCK, interval=1):
                    continue
        else:
            while 1:
                self.screenshot()
                if self.appear(self.I_FALLEN_SUN_UNLOCK):
                    return True
                if self.appear_then_click(self.I_FALLEN_SUN_LOCK, interval=1):
                    continue

    def run_leader(self):
        logger.info('Start run leader')
        self.goto_page(page_soul_zones)
        self.fallen_sun_enter()
        layer = self.config.fallen_sun.fallen_sun_config.layer
        self.check_layer(layer)
        self.check_lock(self.config.fallen_sun.general_battle_config.lock_team_enable)
        # 创建队伍
        logger.info('Create team')
        while 1:
            self.screenshot()
            if self.appear(self.I_CHECK_TEAM):
                break
            if self.appear_then_click(self.I_FORM_TEAM, interval=1):
                continue
        # 创建房间
        self.create_room()
        self.ensure_private()
        self.create_ensure()

        # 邀请队友
        success = True
        is_first = True
        # 这个时候我已经进入房间了哦
        while 1:
            self.screenshot()
            # 无论胜利与否, 都会出现是否邀请一次队友
            # 区别在于，失败的话不会出现那个勾选默认邀请的框
            if self.check_and_invite(self.config.fallen_sun.invite_config.default_invite):
                continue

            # 检查猫咪奖励
            if self.appear_then_click(self.I_PET_PRESENT, action=self.C_RANDOM_RIGHT, interval=1):
                continue

            if self.current_count >= self.limit_count:
                if self.is_in_room():
                    logger.info('FallenSun count limit out')
                    break

            if datetime.now() - self.start_time >= self.limit_time:
                if self.is_in_room():
                    logger.info('FallenSun time limit out')
                    break

            # 如果没有进入房间那就不需要后面的邀请
            if not self.is_in_room():
                # 如果在探索界面或者是出现在组队界面， 那就是可能房间死了
                # 要结束任务
                sleep(0.5)
                if self.appear(self.I_MATCHING) or self.appear(self.I_CHECK_EXPLORATION):
                    sleep(0.5)
                    if self.appear(self.I_MATCHING) or self.appear(self.I_CHECK_EXPLORATION):
                        logger.warning('FallenSun task failed')
                        success = False
                        break
                continue

            # 点击挑战
            if not is_first:
                if self.run_invite(config=self.config.fallen_sun.invite_config):
                    self.run_general_battle(
                        config=self.config.fallen_sun.general_battle_config,
                        battle_key=self._fallen_sun_battle_key(),
                        exit_matcher=self.I_CHECK_TEAM,
                    )
                else:
                    # 邀请失败，退出任务
                    logger.warning('Invite failed and exit this fallen_sun task')
                    success = False
                    break

            # 第一次会邀请队友
            if is_first:
                if not self.run_invite(config=self.config.fallen_sun.invite_config, is_first=True):
                    logger.warning('Invite failed and exit this fallen_sun task')
                    success = False
                    break
                else:
                    is_first = False
                    self.run_general_battle(
                        config=self.config.fallen_sun.general_battle_config,
                        battle_key=self._fallen_sun_battle_key(),
                        exit_matcher=self.I_CHECK_TEAM,
                    )

        # 当结束或者是失败退出循环的时候只有两个UI的可能，在房间或者是在组队界面
        # 如果在房间就退出
        if self.exit_room():
            pass
        # 如果在组队界面就退出
        if self.exit_team():
            pass

        self.goto_page(page_main)

        if not success:
            return False
        return True

    def run_member(self):
        logger.info('Start run member')
        # self.goto_page(page_soul_zones)
        # self.fallen_sun_enter()
        # self.check_lock(self.config.fallen_sun.general_battle_config.lock_team_enable)

        # 进入战斗流程
        self.device.stuck_record_add('BATTLE_STATUS_S')
        while 1:
            self.screenshot()

            # 检查猫咪奖励
            if self.appear_then_click(self.I_PET_PRESENT, action=self.C_RANDOM_RIGHT, interval=1):
                continue

            if self.current_count >= self.limit_count:
                logger.info('FallenSun count limit out')
                break
            if datetime.now() - self.start_time >= self.limit_time:
                logger.info('FallenSun time limit out')
                break

            if self.check_then_accept():
                continue

            if self.is_in_room():
                self.device.stuck_record_clear()
                if self.wait_battle(wait_time=self.config.fallen_sun.invite_config.wait_time):
                    self.run_general_battle(
                        config=self.config.fallen_sun.general_battle_config,
                        battle_key=self._fallen_sun_battle_key(),
                        exit_matcher=self.I_CHECK_TEAM,
                    )
                else:
                    break
            # 队长秒开的时候，检测是否进入到战斗中
            if self.is_in_battle(False):
                self.run_general_battle(
                    config=self.config.fallen_sun.general_battle_config,
                    battle_key=self._fallen_sun_battle_key(),
                    exit_matcher=self.I_CHECK_TEAM,
                )

        while 1:
            # 有一种情况是本来要退出的，但是队长邀请了进入的战斗的加载界面
            if self.appear(self.I_CHECK_MAIN) or self.appear(self.I_CHECK_EXPLORATION):
                break
            # 如果可能在房间就退出
            if self.exit_room():
                pass
            # 如果还在战斗中，就退出战斗
            if self.exit_battle():
                pass


        self.goto_page(page_main)
        return True

    def run_alone(self):
        logger.info('Start run alone')
        self.goto_page(page_soul_zones)
        self.fallen_sun_enter()
        layer = self.config.fallen_sun.fallen_sun_config.layer
        self.check_layer(layer)
        self.check_lock(self.config.fallen_sun.general_battle_config.lock_team_enable)

        def is_in_fallen_sun(screenshot=False) -> bool:
            if screenshot:
                self.screenshot()
            return self.appear(self.I_FALLEN_SUN_FIRE)

        while 1:
            self.screenshot()

            # 检查猫咪奖励
            if self.appear_then_click(self.I_PET_PRESENT, action=self.C_RANDOM_RIGHT, interval=1):
                continue

            if not is_in_fallen_sun():
                continue

            if self.current_count >= self.limit_count:
                logger.info('FallenSun count limit out')
                break
            if datetime.now() - self.start_time >= self.limit_time:
                logger.info('FallenSun time limit out')
                break

            # 点击挑战
            while 1:
                self.screenshot()
                if self.appear_then_click(self.I_FALLEN_SUN_FIRE, interval=1):
                    pass

                if not self.appear(self.I_FALLEN_SUN_FIRE):
                    self.run_general_battle(
                        config=self.config.fallen_sun.general_battle_config,
                        battle_key=self._fallen_sun_battle_key(),
                        exit_matcher=self.I_FALLEN_SUN_FIRE,
                    )
                    break

        # 回去
        while 1:
            self.screenshot()
            if not self.appear(self.I_FORM_TEAM):
                break
            if self.appear_then_click(self.I_BACK_BL, interval=1):
                continue

        self.goto_page(page_main)

    def run_wild(self):
        logger.error('Wild mode is not implemented')
        pass


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)

    t.run()
    # t.check_layer('日蚀')
