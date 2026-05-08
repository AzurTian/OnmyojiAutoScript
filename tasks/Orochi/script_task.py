# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import random
from time import sleep
from datetime import time, datetime, timedelta

from tasks.Component.GeneralBattle.general_battle import BattleAction, GeneralBattle, ExitMatcher
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Component.GeneralBuff.general_buff import GeneralBuff
from tasks.Component.GeneralRoom.general_room import GeneralRoom
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import any_of, page_main, page_reward, page_shikigami_records, page_soul_zones
from tasks.Orochi.assets import OrochiAssets
from tasks.Orochi.config import Orochi, UserStatus, Layer
from module.logger import logger
from module.exception import TaskEnd


class ScriptTask(GeneralBattle, GeneralInvite, GeneralBuff, GeneralRoom, GameUi, SwitchSoul, OrochiAssets):

    def _orochi_battle_key(self) -> str:
        return f"orochi_{self.config.orochi.orochi_config.layer}"

    def _register_custom_pages(self) -> None:
        reward_page = self.navigator.resolve_page(page_reward)
        if reward_page is None:
            return
        reward_page.recognizer = any_of(self.I_GREED_GHOST, reward_page.recognizer)

    def _exit_matcher(self) -> ExitMatcher | None:
        return any_of(self.I_GI_EMOJI_1, self.I_GI_EMOJI_2, self.I_CHECK_EXPLORATION)

    def run(self) -> bool:
        # 御魂切换方式一
        if self.config.orochi.switch_soul.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(self.config.orochi.switch_soul.switch_group_team)

        # 御魂切换方式二
        if self.config.orochi.switch_soul.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(self.config.orochi.switch_soul.group_name,
                                         self.config.orochi.switch_soul.team_name)
        # 根据选层切换御魂
        self.orochi_switch_soul()

        limit_count = self.config.orochi.orochi_config.limit_count
        limit_time = self.config.orochi.orochi_config.limit_time
        self.current_count = 0
        self.limit_count: int = limit_count
        self.limit_time: timedelta = timedelta(hours=limit_time.hour, minutes=limit_time.minute, seconds=limit_time.second)

        config: Orochi = self.config.orochi
        if not self.is_in_battle(True):
            self.goto_page(page_main)
            if config.orochi_config.soul_buff_enable:
                self.open_buff()
                self.soul(is_open=True)
                self.close_buff()

        success = True
        match config.orochi_config.user_status:
            case UserStatus.LEADER: success = self.run_leader()
            case UserStatus.MEMBER: success = self.run_member()
            case UserStatus.ALONE: self.run_alone()
            case UserStatus.WILD: success = self.run_wild()
            case _: logger.error('Unknown user status')

        # 记得关掉
        if config.orochi_config.soul_buff_enable:
            self.open_buff()
            self.soul(is_open=False)
            self.close_buff()
        # 下一次运行时间
        if success:
            self.set_next_run('Orochi', finish=True, success=True)
        else:
            self.set_next_run('Orochi', finish=False, success=False)

        raise TaskEnd

    def orochi_enter(self) -> bool:
        logger.info('Enter orochi')
        while True:
            self.screenshot()
            if self.appear(self.I_FORM_TEAM) or self.appear(self.I_SHI_RECORDS):
                return True
            if self.appear_then_click(self.I_OROCHI, interval=1):
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
                if self.appear(self.I_OROCHI_LOCK):
                    return True
                if self.appear_then_click(self.I_OROCHI_UNLOCK, interval=1):
                    continue
        else:
            while 1:
                self.screenshot()
                if self.appear(self.I_OROCHI_UNLOCK):
                    return True
                if self.appear_then_click(self.I_OROCHI_LOCK, interval=1):
                    continue

    def run_leader(self):
        logger.info('Start run leader')
        self.goto_page(page_soul_zones)
        self.orochi_enter()
        layer = self.config.orochi.orochi_config.layer
        self.check_layer(layer)
        # https://github.com/runhey/OnmyojiAutoScript/issues/592
        self.config.orochi.general_battle_config.lock_team_enable = True
        self.check_lock(self.config.orochi.general_battle_config.lock_team_enable)
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
            if self.check_and_invite(self.config.orochi.invite_config.default_invite):
                continue

            # 检查猫咪奖励
            if self.appear_then_click(self.I_PET_PRESENT, action=self.C_RANDOM_RIGHT, interval=1):
                continue

            if self.current_count >= self.limit_count:
                if self.is_in_room():
                    logger.info('Orochi count limit out')
                    break

            if datetime.now() - self.start_time >= self.limit_time:
                if self.is_in_room():
                    logger.info('Orochi time limit out')
                    break



            # 如果没有进入房间那就不需要后面的邀请
            if not self.is_in_room():
                if self.is_room_dead():
                    logger.warning('Orochi task failed')
                    success = False
                    break
                continue

            # 点击挑战
            if not is_first:
                if self.run_invite(config=self.config.orochi.invite_config):
                    self.run_general_battle(
                        config=self.config.orochi.general_battle_config,
                        battle_key=self._orochi_battle_key()
                    )
                else:
                    # 邀请失败，退出任务
                    logger.warning('Invite failed and exit this orochi task')
                    success = False
                    break

            # 第一次会邀请队友
            if is_first:
                if not self.run_invite(config=self.config.orochi.invite_config, is_first=True):
                    logger.warning('Invite failed and exit this orochi task')
                    success = False
                    break
                else:
                    is_first = False
                    self.run_general_battle(
                        config=self.config.orochi.general_battle_config,
                        battle_key=self._orochi_battle_key()
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
        # self.orochi_enter()
        # self.check_lock(self.config.orochi.general_battle_config.lock_team_enable)

        # 进入战斗流程
        self.device.stuck_record_add('BATTLE_STATUS_S')
        while 1:
            self.screenshot()

            # 检查猫咪奖励
            if self.appear_then_click(self.I_PET_PRESENT, action=self.C_RANDOM_RIGHT, interval=1):
                continue
            if self.current_count >= self.limit_count:
                logger.info('Orochi count limit out')
                break
            if datetime.now() - self.start_time >= self.limit_time:
                logger.info('Orochi time limit out')
                break

            if self.check_then_accept():
                continue

            if self.is_in_room(False):
                self.device.stuck_record_clear()
                if self.wait_battle(wait_time=self.config.orochi.invite_config.wait_time):
                    self.run_general_battle(
                        config=self.config.orochi.general_battle_config,
                        battle_key=self._orochi_battle_key()
                    )
                else:
                    break
            # 队长秒开的时候，检测是否进入到战斗中
            if self.is_in_battle(False):
                self.run_general_battle(
                    config=self.config.orochi.general_battle_config,
                    battle_key=self._orochi_battle_key()
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
        self.orochi_enter()
        layer = self.config.orochi.orochi_config.layer
        self.check_layer(layer)
        self.check_lock(self.config.orochi.general_battle_config.lock_team_enable)

        def is_in_orochi(screenshot=False) -> bool:
            if screenshot:
                self.screenshot()
            return self.appear(self.I_OROCHI_FIRE)

        while 1:
            self.screenshot()

            # 检查猫咪奖励
            if self.appear_then_click(self.I_PET_PRESENT, action=self.C_RANDOM_RIGHT, interval=1):
                continue

            if not is_in_orochi():
                continue

            if self.current_count >= self.limit_count:
                logger.info('Orochi count limit out')
                break
            if datetime.now() - self.start_time >= self.limit_time:
                logger.info('Orochi time limit out')
                break

            # 点击挑战
            while 1:
                self.screenshot()
                if self.appear_then_click(self.I_OROCHI_FIRE, interval=1):
                    pass

                if not self.appear(self.I_OROCHI_FIRE):
                    self.run_general_battle(
                        config=self.config.orochi.general_battle_config,
                        battle_key=self._orochi_battle_key(),
                        exit_matcher=self.I_OROCHI_FIRE,
                    )
                    break

        self.goto_page(page_main)

    def run_wild(self):
        logger.info('Start run wild')

        # 已经在战斗中不必初始化，保证已经组队开始战斗的情况下可以自动执行后续任务
        if not self.is_in_battle(True):
            self.goto_page(page_soul_zones)
            self.orochi_enter()
            layer = self.config.orochi.orochi_config.layer
            self.check_layer(layer)
            self.check_lock(self.config.orochi.general_battle_config.lock_team_enable)
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
            self.ensure_public()
            self.create_ensure()

        success = True
        while 1:
            self.screenshot()
            # 无论胜利与否, 都会出现是否邀请一次队友
            # 区别在于，失败的话不会出现那个勾选默认邀请的框
            if self.check_and_invite(self.config.orochi.invite_config.default_invite):
                continue

            # 检查猫咪奖励
            if self.appear_then_click(self.I_PET_PRESENT, action=self.C_RANDOM_RIGHT, interval=1):
                continue

            if self.current_count >= self.limit_count:
                if self.is_in_room():
                    logger.info('Orochi count limit out')
                    break

            if datetime.now() - self.start_time >= self.limit_time:
                if self.is_in_room():
                    logger.info('Orochi time limit out')
                    break

            if not self.is_in_room():
                if self.is_room_dead():
                    logger.warning('Orochi task failed')
                    success = False
                    break
                continue

            # 点击挑战
            logger.info('Wait for starting')
            while 1:
                self.screenshot()
                # 在进入战斗前必然会出现挑战界面，因此点击失败必须重复点击，防止卡在挑战界面，
                # 点击成功后如果网络卡顿，导致没有进入战斗，则无法进入 run_general_battle 流程，
                # 所以如果判断是在战斗中，则执行通用战斗流程
                if not self.is_in_battle(False):
                    if not self.is_in_room() and self.is_room_dead():
                        break
                    if not self.appear_then_click(self.I_OROCHI_WILD_FIRE, interval=1, threshold=0.8):
                        continue

                self.screenshot()
                if not self.appear(self.I_OROCHI_WILD_FIRE, threshold=0.8):
                    self.run_general_battle(
                        config=self.config.orochi.general_battle_config,
                        battle_key=self._orochi_battle_key(),
                        exit_matcher=any_of(self.I_OROCHI_WILD_FIRE, self.I_CHECK_TEAM),
                    )
                    break

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

    def is_room_dead(self) -> bool:
        # 如果在探索界面或者是出现在组队界面，那就是可能房间死了
        sleep(0.5)
        if self.appear(self.I_MATCHING) or self.appear(self.I_CHECK_EXPLORATION):
            sleep(0.5)
            if self.appear(self.I_MATCHING) or self.appear(self.I_CHECK_EXPLORATION):
                return True
        return False

    def orochi_switch_soul(self) -> None:
        # 判断是否开启根据选层切换御魂
        orochi_switch_soul = self.config.orochi.switch_soul
        if not orochi_switch_soul.auto_switch_soul:
            return

        group_team: str = None
        layer = self.config.orochi.orochi_config.layer
        match layer:
            case Layer.TEN:
                group_team = orochi_switch_soul.ten_switch
            case Layer.ELEVEN:
                group_team = orochi_switch_soul.eleven_switch
            case Layer.TWELVE:
                group_team = orochi_switch_soul.twelve_switch
            case Layer.THIRTEEN:
                group_team = orochi_switch_soul.thirteen_switch

        if orochi_switch_soul.auto_switch_soul:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(group_team)


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    c = Config('日常2')
    d = Device(c)
    t = ScriptTask(c, d)

    t._open_invite_panel_if_needed(True)
