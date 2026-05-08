# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey

from module.logger import logger
from module.base.timer import Timer

from tasks.Exploration.base import BaseExploration, Scene
from tasks.Exploration.config import AutoRotate, UserStatus, ExplorationLevel
import tasks.Exploration.page as pages


class SoloExploration(BaseExploration):

    def run_solo(self):
        logger.hr('solo')
        explore_init = False
        search_fail_cnt = 0
        self.goto_page(pages.page_exp_main)
        while True:
            self.screenshot()
            scene = self.get_current_scene()
            match scene:
                case Scene.WORLD:
                    if self.appear(self.I_TREASURE_BOX_CLICK):  # 宝箱
                        logger.info('Treasure box appear, get it.')
                        self.ui_click_until_disappear(self.I_TREASURE_BOX_CLICK)
                    if self.check_exit():
                        return
                    self.open_expect_level()
                case Scene.ENTRANCE:
                    if self.check_exit():
                        return
                    self.ui_click(self.I_E_EXPLORATION_CLICK, stop=self.I_E_SETTINGS_BUTTON)
                case Scene.MAIN:
                    if not explore_init:
                        if self._config.exploration_config.auto_rotate == AutoRotate.yes:
                            # 第一次进入就直接看一下轮换式神够不够，先补上
                            self.enter_settings_and_do_operations()
                            # 轮换打开
                            self.ui_click(self.I_E_AUTO_ROTATE_OFF, stop=self.I_E_AUTO_ROTATE_ON)
                        else:
                            # 轮换关闭
                            self.ui_click(self.I_E_AUTO_ROTATE_ON, stop=self.I_E_AUTO_ROTATE_OFF)
                        explore_init = True
                    else:
                        # 已经初始化了, 但是当前轮换是off状态, 则需要添加式神
                        if self._config.exploration_config.auto_rotate == AutoRotate.yes and \
                                self.appear(self.I_E_AUTO_ROTATE_OFF):
                            self.enter_settings_and_do_operations()
                            self.ui_click(self.I_E_AUTO_ROTATE_OFF, stop=self.I_E_AUTO_ROTATE_ON)
                    # 小纸人
                    if self.appear(self.I_BATTLE_REWARD):
                        if self._config.exploration_config.collect_paper_reward and self.ui_get_reward(self.I_BATTLE_REWARD):
                            continue
                        logger.info("Not collect paper doll reward")
                        self.quit_explore()
                    # boss
                    if self.appear(self.I_BOSS_BATTLE_BUTTON):
                        if self.fire(self.I_BOSS_BATTLE_BUTTON):
                            logger.info(f'Boss battle, minions cnt {self.minions_cnt}')
                        continue
                    # 小怪
                    fight_button = self.search_up_fight()
                    if fight_button is not None:
                        if self.fire(fight_button):
                            logger.info(f'Fight, minions cnt {self.minions_cnt}')
                        continue
                    # 向后拉,寻找怪
                    if search_fail_cnt >= 4:
                        search_fail_cnt = 0
                        if self._config.exploration_config.exploration_level == ExplorationLevel.EXPLORATION_28 and self.appear(self.I_SWIPE_END):
                            self.quit_explore()
                            continue
                        elif self._config.exploration_config.exploration_level != ExplorationLevel.EXPLORATION_28 and self._match_end.stable(self.device.image, refresh_after_stable=True, frame_id=self.device.image_frame_id):
                            self.quit_explore()
                            continue
                        if self.swipe(self.S_SWIPE_BACKGROUND_RIGHT, interval=2):
                            continue
                    else:
                        search_fail_cnt += 1
                case Scene.BATTLE_PREPARE | Scene.BATTLE_FIGHTING:
                    self.check_take_over_battle(is_screenshot=False, config=self._config.general_battle_config)
                case Scene.UNKNOWN:
                    continue

    def run_leader(self):
        logger.hr('leader')
        explore_init = False
        search_fail_cnt = 0
        friend_leave_timer = Timer(5)
        team_log = False
        self.goto_page(pages.page_exploration)
        while 1:
            self.screenshot()
            scene = self.get_current_scene()
            # 探索大世界
            if scene == Scene.WORLD:
                self.wait_until_stable(self.I_CHECK_EXPLORATION)
                if self.appear(self.I_TREASURE_BOX_CLICK):
                    # 宝箱
                    logger.info('Treasure box appear, get it.')
                    self.wait_until_stable(self.I_UI_CANCEL, timer=Timer(0.6, 1))
                    while 1:
                        self.screenshot()
                        if self.appear(self.I_REWARD):
                            self.ui_click_until_disappear(self.I_REWARD)
                            logger.info('Get reward.')
                            break
                        if self.ui_reward_appear_click():
                            continue
                        if self.appear_then_click(self.I_UI_CANCEL, interval=0.8):
                            continue
                        if self.appear_then_click(self.I_TREASURE_BOX_CLICK, interval=1):
                            continue
                if self.check_exit():
                    self.wait_until_stable(self.I_UI_CANCEL, timer=Timer(0.6, 2))
                    if self.appear(self.I_UI_CANCEL):
                        self.ui_click_until_disappear(self.I_UI_CANCEL)
                    break
                if self.appear(self.I_UI_CONFIRM):
                    self.ui_click_until_disappear(self.I_UI_CONFIRM)
                    # 可以加一下，清空第一次 explore_init
                    continue
                self.open_expect_level()
                continue
            # 邀请好友, 非常有可能是后面邀请好友，然后直接跳到组队了
            elif scene == Scene.ENTRANCE:
                while 1:
                    self.screenshot()
                    if self.is_in_room():
                        break
                    if self.appear_then_click(self.I_ENSURE_PRIVATE_FALSE, interval=0.5):
                        continue
                    if self.appear_then_click(self.I_ENSURE_PRIVATE_FALSE_2, interval=0.5):
                        continue
                    if self.appear_then_click(self.I_EXP_CREATE_TEAM, interval=1):
                        continue
                    if self.appear_then_click(self.I_EXP_CREATE_ENSURE, interval=2):
                        continue
            elif scene == Scene.TEAM:
                self.wait_until_stable(self.I_ADD_2, timer=Timer(0.8, 1), timeout=Timer(3))
                if self.appear(self.I_FIRE, threshold=0.8) and not self.appear(self.I_ADD_2):
                    self.ui_click_until_disappear(self.I_FIRE, interval=1)
                    continue
                if self.appear(self.I_ADD_2) and \
                        self.run_invite(config=self.config.model.exploration.invite_config, is_first=True):
                    continue
                else:
                    logger.warning('Invite failed, quit')
                    while 1:
                        self.screenshot()
                        if self.appear(self.I_CHECK_EXPLORATION):
                            break
                        if self.appear_then_click(self.I_UI_CONFIRM, interval=0.5):
                            continue
                        if self.appear_then_click(self.I_UI_BACK_RED, interval=0.7):
                            continue
                        if self.appear_then_click(self.I_UI_BACK_YELLOW, interval=1):
                            continue
                    break
            elif scene == Scene.MAIN:
                if not explore_init:
                    if self._config.exploration_config.auto_rotate == AutoRotate.yes:
                        self.enter_settings_and_do_operations()
                        self.ui_click(self.I_E_AUTO_ROTATE_OFF, stop=self.I_E_AUTO_ROTATE_ON)
                    else:
                        # 轮换关闭
                        self.ui_click(self.I_E_AUTO_ROTATE_ON, stop=self.I_E_AUTO_ROTATE_OFF)
                    explore_init = True
                    continue
                else:
                    # 已经初始化了, 但是当前轮换是off状态, 则需要添加式神
                    if self._config.exploration_config.auto_rotate == AutoRotate.yes and \
                            self.appear(self.I_E_AUTO_ROTATE_OFF):
                        self.enter_settings_and_do_operations()
                        self.ui_click(self.I_E_AUTO_ROTATE_OFF, stop=self.I_E_AUTO_ROTATE_ON)
                # 小纸人
                if self.appear(self.I_BATTLE_REWARD):
                    if self._config.exploration_config.collect_paper_reward and self.ui_get_reward(
                            self.I_BATTLE_REWARD):
                        continue
                    logger.info("Not collect paper doll reward")
                    self.quit_explore()
                # 中途有人跑路
                if not self.appear(self.I_TEAM_EMOJI):
                    if not friend_leave_timer.started():
                        logger.warning('Mate leave, start timer')
                        friend_leave_timer = Timer(5)
                        friend_leave_timer.start()
                    elif friend_leave_timer.started() and friend_leave_timer.reached():
                        logger.warning('Mate leave timer reached')
                        logger.warning('Exit team')
                        self.quit_explore()
                    # 队友已经跑路了, 不管超没超时都不能进攻
                    continue
                else:
                    if not team_log:
                        logger.info('Team emoji appear again, clear friend_leave_timer')
                        team_log = True
                    friend_leave_timer = Timer(5)
                # boss
                if self.appear(self.I_BOSS_BATTLE_BUTTON):
                    if self.fire(self.I_BOSS_BATTLE_BUTTON):
                        logger.info(f'Boss battle, minions cnt {self.minions_cnt}')
                    continue
                # 小怪
                fight_button = self.search_up_fight()
                if fight_button is not None:
                    if self.fire(fight_button):
                        logger.info(f'Fight, minions cnt {self.minions_cnt}')
                    continue
                # 向后拉,寻找怪
                if search_fail_cnt >= 4:
                    search_fail_cnt = 0
                    if self._config.exploration_config.exploration_level == ExplorationLevel.EXPLORATION_28 and self.appear(
                            self.I_SWIPE_END):
                        self.quit_explore()
                        continue
                    elif self._config.exploration_config.exploration_level != ExplorationLevel.EXPLORATION_28 and self._match_end.stable(
                            self.device.image, refresh_after_stable=True, frame_id=self.device.image_frame_id):
                        self.quit_explore()
                        continue
                    if self.swipe(self.S_SWIPE_BACKGROUND_RIGHT, interval=2):
                        continue
                else:
                    search_fail_cnt += 1
            elif scene == Scene.BATTLE_PREPARE or scene == Scene.BATTLE_FIGHTING:
                self.check_take_over_battle(is_screenshot=False, config=self._config.general_battle_config)
                team_log = False
            elif scene == Scene.UNKNOWN:
                continue

    def run_member(self):
        logger.hr('member')
        explore_init = False
        wait_timer = Timer(50).start()
        friend_leave_timer = Timer(5)
        team_log, leader_leave_log = False, False
        self.device.stuck_record_clear()
        self.device.stuck_record_add('PAUSE')
        self.goto_page(pages.page_exploration)
        while True:
            self.screenshot()
            scene = self.get_current_scene()
            if scene == Scene.WORLD:
                if self.appear(self.I_TREASURE_BOX_CLICK):
                    # 宝箱
                    logger.info('Treasure box appear, get it.')
                    self.ui_click_until_disappear(self.I_TREASURE_BOX_CLICK)
                if self.check_exit():
                    break
                if self.check_then_accept():
                    pass
                if wait_timer.reached():
                    logger.warning('Wait timer reached')
                    break
                continue
            elif scene == Scene.ENTRANCE:
                self.ui_click_until_disappear(self.I_UI_BACK_RED)
            elif scene == Scene.TEAM:
                continue
            elif scene == Scene.MAIN:
                if not explore_init:
                    if self._config.exploration_config.auto_rotate == AutoRotate.yes:
                        self.enter_settings_and_do_operations()
                        self.ui_click(self.I_E_AUTO_ROTATE_OFF, stop=self.I_E_AUTO_ROTATE_ON)
                    else:
                        # 轮换关闭
                        self.ui_click(self.I_E_AUTO_ROTATE_ON, stop=self.I_E_AUTO_ROTATE_OFF)
                    explore_init = True
                    continue
                else:
                    # 已经初始化了, 但是当前轮换是off状态, 则需要添加式神
                    if self._config.exploration_config.auto_rotate == AutoRotate.yes and \
                            self.appear(self.I_E_AUTO_ROTATE_OFF):
                        self.enter_settings_and_do_operations()
                        self.ui_click(self.I_E_AUTO_ROTATE_OFF, stop=self.I_E_AUTO_ROTATE_ON)
                # 小纸人
                if self.appear(self.I_BATTLE_REWARD):
                    logger.info("发现小纸人奖励，按配置退出探索")
                    self.quit_explore()
                    continue
                if not self.appear(self.I_TEAM_EMOJI):
                    if not leader_leave_log:
                        logger.warning('Leader may have run away, wait a while...')
                        leader_leave_log = True
                    if not friend_leave_timer.started():
                        logger.warning('Mate leave, start timer')
                        friend_leave_timer = Timer(5)
                        friend_leave_timer.start()
                        # 好友离开计时器刚开, 总的等待计时器也必须重置
                        wait_timer.reset()
                        self.device.stuck_record_clear()
                        self.device.stuck_record_add('PAUSE')
                    elif friend_leave_timer.started() and friend_leave_timer.reached():
                        logger.warning('Mate leave timer reached')
                        logger.warning('Exit team')
                        self.quit_explore()
                        wait_timer.reset()
                        self.device.stuck_record_clear()
                        self.device.stuck_record_add('PAUSE')
                    continue
                else:
                    if not team_log:
                        logger.info('Team emoji appear again, clear friend_leave_timer')
                        team_log = True
                    # 出现好友标志, 重置计时器
                    wait_timer.reset()
                    self.device.stuck_record_clear()
                    self.device.stuck_record_add('PAUSE')
                    friend_leave_timer = Timer(5)
                    leader_leave_log = False
            elif scene == Scene.BATTLE_PREPARE or scene == Scene.BATTLE_FIGHTING:
                self.check_take_over_battle(is_screenshot=False, config=self._config.general_battle_config)
                # 进入战斗了则需要重新打印日志
                team_log = False
                leader_leave_log = False
            elif scene == Scene.UNKNOWN:
                continue


class ScriptTask(SoloExploration):

    def run(self):
        logger.hr('exploration')
        self.pre_process()

        match self._config.exploration_config.user_status:
            case UserStatus.ALONE:
                self.run_solo()
            case UserStatus.LEADER:
                self.run_leader()
            case UserStatus.MEMBER:
                self.run_member()
            case _:
                self.run_solo()

        self.post_process()


if __name__ == "__main__":
    from module.config.config import Config
    from module.device.device import Device

    config = Config('oas1')
    device = Device(config)
    t = ScriptTask(config, device)
    t.run()
