# This Python file uses the following encoding: utf-8
# @brief    Ryou Dokan Toppa (阴阳竂道馆突破功能)
# @author   AzurTian
# @note     draft version without full test
import time

import re
from datetime import timedelta
from time import sleep

from future.backports.datetime import datetime

from module.base.timer import Timer
from module.exception import TaskEnd
from module.logger import logger
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.GeneralBattle.general_battle import GeneralBattle, ExitMatcher, BattleBehaviorScope, BattleContext, \
    BattleAction
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.Component.config_base import Time
from tasks.Dokan.assets import DokanAssets
from tasks.Dokan.config import Dokan
import tasks.Dokan.page as pages
from tasks.GameUi.game_ui import GameUi


def position_offset(src, offset: tuple):
    return src[0] + offset[0], src[1] + offset[1], src[2] + offset[2], src[3] + offset[3]


class DokanFinishedError(Exception):
    pass


class DokanNotStartedError(Exception):
    pass


class ScriptTask(GameUi, SwitchSoul, GeneralBattle, DokanAssets):
    attack_priority_selected: bool = False
    switch_member_soul_done: bool = False
    switch_owner_soul_done: bool = False
    conf: Dokan = None

    def _register_custom_pages(self) -> None:
        page_battle_result = self.navigator.resolve_page(pages.page_battle_result)
        if page_battle_result is None:
            return
        page_battle_result.recognizer = pages.any_of(self.I_RYOU_DOKAN_TOPPA_RANK, self.I_RYOU_DOKAN_WIN,
                                                     page_battle_result.recognizer)
        page_battle_result.priority = 75
        page_reward = self.navigator.resolve_page(pages.page_reward)
        if page_reward is None:
            return
        page_reward.recognizer = pages.any_of(self.I_RYOU_DOKAN_BATTLE_OVER, page_reward.recognizer)
        page_reward.priority = 75

    def _exit_matcher(self) -> ExitMatcher | None:
        return pages.any_of(self.I_RYOU_DOKAN_CENTER_TOP, self.I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_DONE)

    def _get_battle_behavior_scopes(self, config: GeneralBattleConfig, battle_key: str) -> dict[str, BattleBehaviorScope]:
        scopes = super()._get_battle_behavior_scopes(config, battle_key)
        if battle_key == 'dokan_owner':
            scopes['green'] = BattleBehaviorScope.ROUND
        return scopes

    def _handle_in_battle(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        count = self.conf.attack_count_config.attack_dokan_master_count()
        if context.battle_key == 'dokan_owner':
            if count <= 0:  # 不让打直接退
                return BattleAction.QUICK_EXIT
            if context.continuous_count == 2 and count == 1:  # 2阵但只允许打一次
                return BattleAction.QUICK_EXIT
        return super()._handle_in_battle(context, config)

    def exit_battle(self, skip_first: bool = False) -> bool:
        """
            尝试退出战斗界面
            1. 普通战斗结束,连续点击即可退出
                a. 存在战斗奖励
                b. 战斗失败,
            2. 在战斗界面,但是战斗还未开始(右下角有准备按钮)
                需要点击左上角退出按钮,然后点击确定
            3. 馆主战斗过程中,寮友打败馆主,弹出框体,可点击空白区域取消该框体.
            综上,点击左上角退出按钮区域
        """
        logger.info("try to quit battle...")
        while True:
            self.screenshot()
            if self.appear(self.I_RYOU_DOKAN_CENTER_TOP):
                return True
            if self.appear(self.I_RYOU_DOKAN_QUIT_BATTLE_ENSURE):
                self.ui_click_until_disappear(self.I_RYOU_DOKAN_QUIT_BATTLE_ENSURE)
                return True
            # 退出时,意外弹出"确认退出集结场景" 弹窗,导致卡住
            # 只能怀疑是上面两个appear的耗时 导致screenshot 过时导致错误点击
            # TODO: 待验证
            # 还有一种可能:在退出战斗过程中,在过场图出现前,点击左上角退出按钮,会导致该弹窗弹出(恶心)
            self.screenshot()
            if not self.appear(self.I_RYOU_DOKAN_CENTER_TOP):
                self.click(self.C_DOKAN_BATTLE_QUIT_AREA, interval=3)
                continue
            self.wait_until_appear(self.I_RYOU_DOKAN_CENTER_TOP, True, 3)
        return False

    def before_run(self):
        pages.page_dokan_rank = self.navigator.add_page(pages.Page(self.I_RYOU_DOKAN_TOPPA_RANK, priority=75, register=False))
        pages.page_dokan_rank.connect(pages.page_dokan, pages.random_click, key="page_dokan_rank->page_dokan")

    def run(self):
        self.before_run()
        self.conf = self.config.model.dokan
        if self.conf.dokan_config.monday_to_thursday and datetime.now().weekday() >= 4:
            logger.warning("weekend, exit")
            self.next_run(True)
            raise TaskEnd
        # 初始化相关动态参数,从配置文件读取相关记录,如果没有当天的记录则设置为默认值
        self.conf.attack_count_config.init_attack_count(callback=self.config.save)
        unknown_page_timer = Timer(10)
        self.goto_page(pages.page_dokan_map)
        try:
            while True:
                self.screenshot()
                current_page = self.get_current_page()
                match current_page:
                    case None:
                        self.device.click_record_clear()
                        self.device.stuck_record_clear()
                        time.sleep(0.5)
                    case pages.page_dokan_map:
                        self.run_on_dokan_map()
                    case pages.page_dokan:
                        self.run_on_dokan()
                    case pages.page_battle_prepare | pages.page_battle:
                        self.run_on_battle()
                    case pages.page_battle_result:
                        self.click(pages.random_click(ltrb=(False, False, True, False)), interval=1.5)
                    case _:
                        if not unknown_page_timer.started():
                            unknown_page_timer.start()
                        if unknown_page_timer.started() and unknown_page_timer.reached():  # 10秒都是非道馆界面, 则尝试回到道馆
                            unknown_page_timer = Timer(10)
                            self.goto_page(pages.page_dokan)
        except DokanFinishedError:
            is_dokan_activated = True
        except DokanNotStartedError:
            is_dokan_activated = False
        self.goto_page(pages.page_main)
        self.next_run(skip_today=False, is_dokan_activated=is_dokan_activated)
        raise TaskEnd

    def run_on_dokan(self):
        """道馆页面逻辑处理"""
        self.prepare_appear_cache([
            self.I_RYOU_DOKAN_GATHERING,
            self.I_RYOU_DOKAN_MASTER_BATTLE,
            self.I_RYOU_DOKAN_START_CHALLENGE,
            self.I_RYOU_DOKAN_CD,
            self.I_RYOU_DOKAN_ABANDONED_TOPPA_ABANDONED,
            self.I_RYOU_DOKAN_FAILED_VOTE_KEEP_BOUNTY,
            self.I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN,
            self.I_RYOU_DOKAN_TODAY_ATTACK_COUNT,
            self.I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_DONE,
            self.I_DOKAN_BOSS_WAITING
        ])
        self.device.stuck_record_clear()
        if self.appear(self.I_RYOU_DOKAN_GATHERING):  # 正在集结
            logger.debug(f"Dokan is gathering...")
            self.switch_priority()  # 选择优先级
            self.switch_soul_in_dokan('member')  # 切换馆员御魂
            self.device.click_record_clear()
            return
        if not self.appear(self.I_DOKAN_BOSS_WAITING) and self.appear(self.I_RYOU_DOKAN_MASTER_BATTLE) and \
                self.appear(self.I_RYOU_DOKAN_START_CHALLENGE):  # 馆主可挑战
            count = self.conf.attack_count_config.attack_dokan_master_count()
            first_master_killed = False
            if self._battle_context is not None:
                first_master_killed = self._battle_context.continuous_count > 1
            logger.info(f"Dokan master count:{count}, first master killed:{first_master_killed}")
            if (count - (1 if first_master_killed else 0)) > 0:
                logger.info("start Master first")
                if self.click_until_in_battle():
                    self.run_general_battle(self.conf.dokan_owner_battle_conf, battle_key='dokan_owner')
            # 有权限且当前道馆突破 不再打馆主,直接放弃突破
            elif self.conf.dokan_config.try_start_dokan:
                self.abandoned_toppa()
            return
        if not self.appear(self.I_DOKAN_BOSS_WAITING) and self.appear(self.I_RYOU_DOKAN_START_CHALLENGE):  # 非馆主且可挑战
            self.switch_soul_in_dokan('member')
            if self.click_until_in_battle():
                self.run_general_battle(self.conf.dokan_member_battle_conf, battle_key='dokan_member')
            return
        if not self.appear(self.I_DOKAN_BOSS_WAITING) and self.appear(self.I_RYOU_DOKAN_CD):  # 可观战
            self.device.click_record_clear()
            self.start_cheering()
            return
        if self.appear_then_click(self.I_RYOU_DOKAN_ABANDONED_TOPPA_ABANDONED, interval=2):  # 放弃突破
            return
        if self.appear(self.I_RYOU_DOKAN_FAILED_VOTE_KEEP_BOUNTY, interval=2):  # 投票
            # 每天打一次的直接 选择 保留赏金,
            # 打两次的,第一次选择 继续挑战,第二次没有选项
            if self.conf.attack_count_config.daily_attack_count == 2:
                if self.appear(self.I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN):
                    self.ui_click_until_disappear(self.I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN)
            else:
                if self.appear(self.I_RYOU_DOKAN_FAILED_VOTE_KEEP_BOUNTY):
                    logger.info("Dokan challenge failed: vote for keep the awards")
                    self.ui_click_until_disappear(self.I_RYOU_DOKAN_FAILED_VOTE_KEEP_BOUNTY)
            return
        if self.appear(self.I_RYOU_DOKAN_TODAY_ATTACK_COUNT) or self.appear(self.I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_DONE):
            logger.info("Dokan challenge finished, exit Dokan")
            self.update_remain_attack_count()  # 更新配置
            raise DokanFinishedError

    def click_until_in_battle(self) -> bool:
        """点击挑战直到进入战斗"""
        timeout_timer = Timer(5).start()
        while True:
            self.screenshot()
            if self.is_in_battle(False):
                return True
            if timeout_timer.reached():
                break
            self.appear_then_click(self.I_RYOU_DOKAN_START_CHALLENGE, interval=2)
        return False

    def run_on_dokan_map(self):
        """道馆地图页面逻辑处理"""
        # 如果地图显示挑战已完成或者剩余挑战次数为0视为完成道馆,直接退出
        if self.appear(self.I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_ZERO) or self.appear(self.I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_DONE):
            raise DokanFinishedError
        if self.appear(self.I_RYOU_DOKAN_FINDING_DOKAN):  # 道馆未开启
            try_start_dokan = self.config.dokan.dokan_config.try_start_dokan
            if not try_start_dokan:  # 未设置开启道馆则退出
                raise DokanNotStartedError
            if self.update_remain_attack_count() < 0:  # 可挑战次数为<=0,当作道馆成功完成
                raise DokanFinishedError
            if datetime.now().weekday() == 0:  # NOTE 只在周一尝试建立道馆
                self.creat_dokan()
            # 寻找合适道馆,找不到直接退出
            if not self.find_dokan(self.config.dokan.dokan_config.find_dokan_score):
                raise DokanNotStartedError
            # 寻找到道馆后等一会页面刷新
            self.wait_until_appear(self.I_RYOU_DOKAN_CENTER_TOP, True, 5)
            return
        if self.appear(self.I_RYOU_DOKAN_FOUND_DOKAN):  # 道馆已开启
            self.goto_page(pages.page_dokan)  # 跳转到道馆

    def run_on_battle(self):
        """处理战斗页面逻辑(正常来说是一定不会进入该逻辑的)"""
        if self.appear(self.I_RYOU_DOKAN_BATTLE_MASTER_FIRST) or \
                self.appear(self.I_RYOU_DOKAN_BATTLE_MASTER_SECOND):
            self.run_general_battle(self.conf.dokan_owner_battle_conf, battle_key='dokan_owner')
            return
        self.run_general_battle(self.conf.dokan_member_battle_conf, battle_key='dokan_member')

    def switch_priority(self):
        """选择优先级"""
        if self.attack_priority_selected:
            return
        self.goto_page(pages.page_dokan_priority)
        self.goto_page(pages.page_dokan)
        self.attack_priority_selected = True

    def find_dokan(self, score=4.6):
        """
        寻找符合条件的道馆进行挑战。
    
        参数:
        score (float): 赏金与人数比值的阈值，默认为4.6。
    
        返回:
        bool: 是否找到了符合条件的道馆并进行挑战。
        """

        # 刷新按钮点击次数
        num_fresh = 0
        # 备份一些重要的ROI区域，以便在循环中恢复
        backup = {'i_point_bounty': self.I_RIGHTPAD_POINT_BOUNTY.roi_back,
                  # 'o_dokan_rightpad_bounty':self.O_DOKAN_RIGHTPAD_BOUNTY.roi,
                  'i_point_people_num': self.I_CENTER_POINT_PEOPLE_NUMBER.roi_back}

        def restore_roi():
            self.I_RIGHTPAD_POINT_BOUNTY.roi_back = backup['i_point_bounty']
            self.I_CENTER_POINT_PEOPLE_NUMBER.roi_back = backup['i_point_people_num']

        def find_challengeable(ignore_score=False):
            """
                查找当前列表状态(一般为4个)中符合条件的道馆,并点击使其显示挑战按钮
            @param ignore_score: 是否忽略道馆系数限制, - True:   那么选择当前列表状态系数最低的那个,点击显示挑战按钮
                                                   - False:  如果存在系数符合条件的,点击并显示挑战按钮
                                                            如果全部不符合条件,不进行任何操作,返回时,不显示挑战按钮
            @type ignore_score: float
            @return:
            @rtype:
            """
            restore_roi()
            self.screenshot()
            bounty_list = self.find_all_element(self.I_RIGHTPAD_POINT_BOUNTY, (0, 0, 0, 50))
            logger.info(f'find elements list:{bounty_list}')
            # 默认最小分数
            min_score = 10
            idx_selected = -1
            for idx, item in enumerate(bounty_list):
                self.device.click_record_clear()
                logger.info(f"------start no.{idx} =={item}-----------")
                # 点击使挑战按钮消失的区域(C_DOKAN_CANCEL_SELECT_DOKAN), 点击可能点击到其他寮,
                # 因此需要在此处多点几次,直到挑战按钮消失,
                # 又因为出现挑战按钮动画时长较长,因此需要耗时
                self.screenshot()
                while self.appear(self.I_CENTER_CHALLENGE):
                    self.click(self.C_DOKAN_CANCEL_SELECT_DOKAN, interval=1.5)
                    self.wait_animate_stable(self.C_DOKAN_CANCEL_SELECT_DOKAN_CHECK_ANIMATE, interval=0.5, timeout=1.5)

                # 获取赏金金额
                self.O_DOKAN_RIGHTPAD_BOUNTY.roi = position_offset(item, (0, 0, 100, 0))
                bounty = self.O_DOKAN_RIGHTPAD_BOUNTY.ocr(self.device.image)
                tmp = re.search(r'(\d+)', bounty)
                if not tmp:
                    logger.warning(f"can't find bounty,item = {item},ocr bounty={bounty}")
                    continue
                bounty = float(tmp.group())
                # 扩大搜索区域,防止找不到
                self.I_RIGHTPAD_POINT_BOUNTY.roi_back = position_offset(item, (-10, -10, 20, 20))
                # Note: 道馆不可挑战时(被别的寮打了),8秒后跳过
                if not self.ui_click_until_appear_or_timeout(self.I_RIGHTPAD_POINT_BOUNTY, self.I_CENTER_CHALLENGE,
                                                             interval=1.5, timeout=8):
                    logger.info(f"can't find challenge button,idx={idx} item={item}")
                    # 道馆不可挑战,挑战按钮不会弹出 ,直接进行下一个
                    continue
                # 获取防守人数
                self.screenshot()
                if not self.appear(self.I_CENTER_POINT_PEOPLE_NUMBER):
                    logger.warning(f"can't find point people number image, item={item}")
                    continue
                self.O_DOKAN_CENTER_PEOPLE_NUMBER.roi = position_offset(
                    self.I_CENTER_POINT_PEOPLE_NUMBER.roi_front,
                    (0, 0, 0, 30))
                p_num = self.O_DOKAN_CENTER_PEOPLE_NUMBER.detect_text(self.device.image)
                tmp = re.search(r"(\d+)", p_num)
                if not tmp:
                    logger.warning(f"can't find people number in ocr result,item={item}, p_num={p_num}")
                    continue
                p_num = float(tmp.group())
                logger.info(f"bounty:{bounty},people_num:{p_num},score:{bounty / p_num}")
                item_score = bounty / p_num
                if item_score < min_score:
                    min_score = item_score
                    idx_selected = idx
                # 大于系数 或者 系数过小(文字识别错误导致)
                if item_score > score or item_score < 1.5:
                    logger.info("click to making challenge disappear")
                    continue
                if p_num < self.config.dokan.dokan_config.min_people_num:
                    logger.info("people num too small")
                    continue
                if bounty < self.config.dokan.dokan_config.min_bounty:
                    logger.info("bounty too small")
                    continue
                # 馆主不是修习等级的
                if not self.appear(self.I_CENTER_GUANZHU_XIUXI):
                    continue
                logger.info(f"find_dokan: bounty:{bounty},people_num:{p_num},score:{bounty / p_num}")
                return True
            # 在所有列表中都没有符合的,且忽略系数限制,那么就选择最低分数的那个,点击显示挑战按钮
            if ignore_score:
                x, y, w, h = bounty_list[idx_selected]
                while 1:
                    self.screenshot()
                    if self.appear(self.I_CENTER_CHALLENGE):
                        return True
                    self.device.click(x, y)
                    sleep(0.5)
            return False
        while num_fresh < self.config.dokan.dokan_config.find_dokan_refresh_count:
            for i in range(3):
                sleep(3)
                if find_challengeable():
                    logger.info("find challengeable dokan")
                    self.ui_click(self.I_CENTER_CHALLENGE, self.I_CHALLENGE_ENSURE, interval=1)
                    self.ui_click_until_disappear(self.I_CHALLENGE_ENSURE, interval=1)
                    # 更新可挑战次数
                    self.config.dokan.attack_count_config.del_attack_count(1, self.config.save)
                    # 恢复初始位置信息,防止下次使用出错
                    restore_roi()
                    return True
                # 滑动道馆列表
                self.swipe(self.S_DOKAN_LIST_UP)
            # 恢复初始位置信息,防止下次使用出错
            restore_roi()
            logger.info("=========refresh dokan list=========")
            self.ui_click(self.C_DOKAN_REFRESH, self.I_REFRESH_ENSURE, interval=1)
            self.ui_click_until_disappear(self.I_REFRESH_ENSURE, interval=1)
            logger.info("Refresh Done")
            num_fresh += 1
        # 刷新次数用完,仍未找到符合条件的道馆,选择当前列表(约4个)中系数最低的
        if find_challengeable(ignore_score=True):
            logger.warning("can't find challengeable dokan,select random one")
            self.ui_click(self.I_CENTER_CHALLENGE, self.I_CHALLENGE_ENSURE, interval=1)
            self.ui_click_until_disappear(self.I_CHALLENGE_ENSURE, interval=1)
            # 更新可挑战次数
            self.config.dokan.attack_count_config.del_attack_count(1, self.config.save)
            return True
        return False

    def creat_dokan(self):
        # 点击创建道馆
        # 当 成功建立道馆并关闭道馆信息窗口后退出
        #  或 点击创建道馆按钮无反应(道馆已经建立的情况下),5秒后退出
        while True:
            self.screenshot()
            if self.appear(self.I_RYOU_DOKAN_DOKAN_INFO_CLOSE):
                self.ui_click_until_disappear(self.I_RYOU_DOKAN_DOKAN_INFO_CLOSE)
                logger.info("Create Dokan Success")
                break
            if self.appear(self.I_RYOU_DOKAN_CREATE_DOKAN_ENSURE):
                self.ui_click_until_appear_or_timeout(self.I_RYOU_DOKAN_CREATE_DOKAN_ENSURE,
                                                      stop=self.I_RYOU_DOKAN_DOKAN_INFO_CLOSE, interval=2, timeout=10)
                continue
            if self.ui_click_until_appear_or_timeout(self.I_RYOU_DOKAN_CREATE_DOKAN,
                                                     self.I_RYOU_DOKAN_CREATE_DOKAN_ENSURE, 2, 10):
                continue
            break

    def find_all_element(self, item, offset: tuple) -> list[tuple[int, int, int, int]]:
        """
        NOTE: 仅适配查找道馆列表
        在当前对象中查找所有匹配的项目，并返回它们的信息列表。

        此函数的目的是通过循环搜索和匹配给定的项目，并将匹配的项目信息存储到一个列表中。
        如果项目出现，则将其添加到列表中，并根据预定义的规则调整项目的位置。

        参数:
        - item: 需要查找的项目。
        - offset: 如果当前区域查找不到,扩大查找区域的大小

        返回值:
        返回一个包含所有匹配项目信息的列表。
        """
        res_list = []
        while 1:
            if (item.roi_back[0] + item.roi_back[2] > (1280 + offset[2])) or (
                    item.roi_back[1] + item.roi_back[3] > (720 + offset[3])):
                break
            if self.appear(item):
                res_list.append(item.roi_front.copy())
                # 刷新搜索区域,使用上个搜索结果的Y坐标作为起始点的Y坐标,搜索结果的高度作为起始搜索高度
                item.roi_back = position_offset(item.roi_back, (
                    0, item.roi_front[1] + item.roi_front[3] - item.roi_back[1], 0,
                    item.roi_front[3] - item.roi_back[3]))
            item.roi_back = position_offset(item.roi_back, offset)
        return res_list

    def start_cheering(self):
        if not self.conf.dokan_config.dokan_auto_cheering_while_cd:
            return
        cd_text = self.O_DOKEN_FAIL_CD.detect_text(self.device.image)
        match = re.search(r'\d+', cd_text)
        remain_seconds = int(match.group()) if match else None
        if not remain_seconds:
            logger.info(f'No remain seconds, exit cheering, cd_text[{cd_text}]')
            return
        cheering_timer = Timer(remain_seconds).start()
        logger.info(f"start cheering, remain seconds:{remain_seconds}s")
        while not cheering_timer.reached():
            self.screenshot()
            # 出现观战标志点击观战
            if self.appear_then_click(self.I_RYOU_DOKAN_CD, interval=2.5):
                sleep(1.5)  # 等待一下观战列表出现动画
                continue
            if self.is_in_battle(False):
                break
            # 寻找前往按钮并点击
            if self.list_appear_click(self.L_GOTO_CHEERING, interval=3, max_swipe=3):
                continue
            # 没有找到前往(全军覆没or没人上)则随机点击其他位置关闭弹窗
            self.click(pages.random_click(), interval=5)
        else:
            logger.warning('Enter battle to cheer failed')
            return
        logger.info('Enter battle to cheer')
        cheer_cnt = 0
        self.device.stuck_record_clear()
        self.device.stuck_record_add('PAUSE')
        while not cheering_timer.reached():
            self.screenshot()
            battle_end_page = self.detect_page_in(pages.page_battle_result, pages.page_reward, include_global=False)
            if battle_end_page is not None:  # 战斗结束则退出战斗交给上层处理
                logger.info(f'Cheer finish, count[{cheer_cnt}]')
                self.exit_battle(True)
                self.device.stuck_record_clear()
                return
            # 灰色助威
            if self.appear(self.I_RYOU_DOKAN_CHEERING_GRAY, interval=2):
                continue
            # 亮色助威
            if self.appear_then_click(self.I_RYOU_DOKAN_CHEERING, interval=2):
                cheer_cnt += 1
                logger.attr(cheer_cnt, f'cheer, count time[{cheering_timer.current():.1f}s]')
                self.device.stuck_record_clear()
                self.device.click_record_clear()
                self.device.stuck_record_add('PAUSE')
                continue
        # 助威时间到了且道馆还未结束, 则退出观战交给上层重新挑战
        self.exit_battle()

    def update_remain_attack_count(self) -> int:
        """
        根据道馆地图界面 或 打完道馆后 的寮境界面,更新配置信息
        @return:
        @rtype:
        """
        self.screenshot()
        count = -1
        if self.appear(self.I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_ZERO) or self.appear(
                self.I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_DONE):
            logger.info("I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_ZERO/DONE found")
            count = 0
        elif self.appear(self.I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_ONE):
            logger.info("I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_ONE found")
            count = 1
        elif self.appear(self.I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_TWO):
            logger.info("I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_TWO found")
            count = 2
        else:
            logger.info("dont find REMAIN_ATTACK_COUNT PIC")
            count = -1
        self.config.dokan.attack_count_config.set_attack_count(count, self.config.save)
        return count

    def abandoned_toppa(self):
        if self.appear(self.I_DOKAN_ABANDONED_TOPPA):
            self.ui_click(self.I_DOKAN_ABANDONED_TOPPA, stop=self.I_DOKAN_ABANDONED_TOPPA_ENSURE)
            # 点击确认按钮后,会出现突破排名弹窗,需要点击空白区域关闭
            self.ui_click(self.I_DOKAN_ABANDONED_TOPPA_ENSURE, stop=self.I_RYOU_DOKAN_TOPPA_RANK)
            self.ui_click_until_smt_disappear(self.C_DOKAN_TOPPA_RANK_CLOSE_AREA,
                                              stop=self.I_DOKAN_ABANDONED_TOPPA_TITLE,
                                              interval=2)
        # 动画延时
        self.wait_until_appear(self.I_DOKAN_ABANDONED_TOPPA_TITLE, True, 5)
        # 投票放弃突破,一般来说,都主动放弃突破了,基本上点放弃没有错(虽然项目中做了继续的按钮图)
        if self.appear(self.I_DOKAN_ABANDONED_TOPPA_TITLE):
            if self.appear(self.I_RYOU_DOKAN_ABANDONED_TOPPA_ABANDONED):
                self.ui_click_until_disappear(self.I_RYOU_DOKAN_ABANDONED_TOPPA_ABANDONED)
        else:
            # 再战道馆, 保留赏金
            if self.appear(self.I_RYOU_DOKAN_FAILED_VOTE_KEEP_BOUNTY):
                self.ui_click_until_disappear(self.I_RYOU_DOKAN_FAILED_VOTE_KEEP_BOUNTY)

    def switch_soul_in_dokan(self, switch_type: str = None):
        if switch_type is None:
            return
        switch_soul_dict = {
            'member': {
                'group_team': self.config.dokan.dokan_member_switch_soul.switch_group_team,
                'group_team_name': [self.config.dokan.dokan_member_switch_soul.group_name,
                                    self.config.dokan.dokan_member_switch_soul.team_name]
            },
            'owner': {
                'group_team': self.config.dokan.dokan_owner_switch_soul.switch_group_team,
                'group_team_name': [self.config.dokan.dokan_owner_switch_soul.group_name,
                                    self.config.dokan.dokan_owner_switch_soul.team_name]
            }
        }
        switch_soul_done = getattr(self, f'switch_{switch_type}_soul_done', False)
        if switch_soul_done:
            return
        logger.hr('Start switch soul', 2)
        switch_soul = getattr(self.config.dokan, f'dokan_{switch_type}_switch_soul', None)
        switch_soul_by_name = getattr(self.config.dokan, f'dokan_{switch_type}_switch_soul_by_name', None)
        if switch_soul is not None and switch_soul.enable:
            self.goto_page(pages.page_shikigami_records)
            self.run_switch_soul(switch_soul_dict[switch_type]['group_team'])
            self.goto_page(pages.page_dokan)
        elif switch_soul_by_name is not None and switch_soul_by_name.enable:
            self.goto_page(pages.page_shikigami_records)
            self.run_switch_soul_by_name(switch_soul_dict[switch_type]['group_team_name'][0],
                                         switch_soul_dict[switch_type]['group_team_name'][1])
            self.goto_page(pages.page_dokan)
        else:
            logger.info('Skip switch soul')
        setattr(self, f'switch_{switch_type}_soul_done', True)

    def next_run(self, skip_today=False, is_dokan_activated=False):
        """
            设置下次运行时间
            该函数假定道馆时间设置为:每天固定时间尝试开启(例如:19:00),成功后设置为明天固定时间(例如19:00)
                                失败则在短时间(例如:2分钟)内再次尝试开启道馆任务
            此假定应该符合绝大多数人需求,如果存在其他需求,,,help yourself

        @param skip_today: 是否跳过今天,True->当作当天的道馆已成功打掉,False->无效
                            为了跳过周五->周天
        @type skip_today: bool
        @param is_dokan_activated:
        @type is_dokan_activated: bool
        @return:
        @rtype:
        """
        now = datetime.now()
        run_time: Time = self.config.model.dokan.dokan_config.dokan_run_time
        run_time_dt = datetime.combine(now.date(), run_time)
        if skip_today:
            if self.conf.dokan_config.monday_to_thursday and now.weekday() >= 4:  # 直接设置下周一的道馆时间
                self.set_next_run(task="Dokan", server=False,
                                  target=datetime.combine(now.date() + timedelta(days=7 - now.weekday()), run_time))
                return
            self.set_next_run(task="Dokan", server=False, target=datetime.combine(now.date() + timedelta(days=1), run_time))
            return
        # 道馆没有开启
        if not is_dokan_activated:
            # 在服务器时间之前,设置为服务器时间
            if now < run_time_dt:
                self.set_next_run(task="Dokan", server=False, target=run_time_dt)
                return
            # 在服务器时间之后,如超过1小时,则直接当作成功;未超过则当作失败
            if now - run_time_dt > timedelta(hours=1):
                self.set_next_run(task="Dokan", server=False,
                                  target=datetime.combine(now.date() + timedelta(days=1), run_time))
                return
            # 时间在道馆开启时间附近，failure_interval后执行
            self.set_next_run(task="Dokan", server=False, target=now + self.config.dokan.scheduler.failure_interval)
            return
        # 道馆已开启
        # 如果打两次,当前是第一次,设置为failure_interval后运行
        if self.config.dokan.attack_count_config.remain_attack_count == 1 and \
                self.config.dokan.attack_count_config.daily_attack_count == 2:
            self.set_next_run(task="Dokan", server=False, target=now + self.config.dokan.scheduler.failure_interval)
            return
        # 其余情况当作成功
        self.set_next_run(task="Dokan", server=False, target=datetime.combine(now.date() + timedelta(days=1), run_time))


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('日常1')
    d = Device(c)
    t = ScriptTask(c, d)
    t.run()
