# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from datetime import timedelta, time, datetime
from time import sleep

from tasks.GameUi.default_pages import page_battle_prepare, page_battle
from tasks.GameUi.matcher import any_of
from typing import List, Callable, Optional

from cached_property import cached_property

from module.atom.image import RuleImage
from module.atom.ocr import RuleOcr
from module.base.timer import Timer
from module.exception import TaskEnd
from module.image.recipes import match_highlight_rule
from module.logger import logger
from tasks.Component.Costume.config import MainType
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.GameUi.page import page_main, page_exploration, page_shikigami_records
from tasks.Secret.script_task import ScriptTask as SecretScriptTask
from tasks.WantedQuests.assets import WantedQuestsAssets
from tasks.WantedQuests.config import CooperationType, CooperationSelectMask, WQInfo, WQType, WantedQuestsConfig
from tasks.WantedQuests.explore import WQExplore, ExploreWantedBoss


class ScriptTask(WQExplore, SecretScriptTask, WantedQuestsAssets):
    # 追踪界面(显示"前往"按钮的界面,左上角位置,神秘任务不好使)显示以下名称时,任务不再执行
    unwanted_boss_name_list: list = []
    # 已经执行过的悬赏封印(仅记录执行过的, 不一定成功运行)
    wq_executed_set: set[WQInfo] = set()

    def run(self):
        con = self.config.model.wanted_quests
        unwanted_boss_names = con.wanted_quests_config.unwanted_boss_names
        if unwanted_boss_names is not None and unwanted_boss_names != '':
            import re
            self.unwanted_boss_name_list = re.split(r"[，,]", unwanted_boss_names)

        # 自动换御魂
        if con.switch_soul_config.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(con.switch_soul_config.switch_group_team)
        if con.switch_soul_config.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(con.switch_soul_config.group_name, con.switch_soul_config.team_name)

        preSuc = False
        if (self.get_config()).cooperation_only:
            preSuc = self.pre_work_cooperation_only()
        else:
            preSuc = self.pre_work()
        if not preSuc:
            # 无法完成预处理 很有可能你已经完成了悬赏任务
            logger.warning('Cannot pre-work')
            logger.warning('You may have completed the reward task')
            self.next_run()
            raise TaskEnd('WantedQuests')

        error_count = 0
        while 1:
            self.screenshot()
            if not self.is_wq_remained():
                logger.info("no more wq remained")
                break
            if self.appear(self.I_WQ_BOX):
                logger.info("get reward")
                self.ui_get_reward(self.I_WQ_BOX)
                continue
            if self.appear(self.I_E_REWARD_BOX_BIG):
                logger.info("get treasure")
                self.ui_get_reward(self.I_E_REWARD_BOX_BIG)
                continue
            if error_count > 3:
                logger.warning('failed too many times, exit')
                break
            cu, re, total, self.O_WQ_TEXT_ALL.area = self.find_wq(self.device.image)
            if re == -1:
                error_count += 1
                # 没找到任务 尝试上滑
                self.swipe(self.S_WQ_LIST_UP, interval=1)
                sleep(1)
                continue
            error_count = 0
            if not self.open_wq_info():
                continue
            self.execute_mission(total - cu)
            sleep(1.5)
        self.next_run()
        raise TaskEnd('WantedQuests')

    def open_wq_info(self) -> bool:
        """打开对应怪物悬赏详情界面"""
        timeout_timer = Timer(5).start()
        while not timeout_timer.reached():
            self.screenshot()
            if self.appear(self.I_TRACE_TRUE):
                return True
            self.click(self.O_WQ_TEXT_ALL, interval=1.2)
        return False

    def next_run(self):
        before_end: time = self.get_config().before_end
        if before_end == time(hour=0, minute=0, second=0):
            self.set_next_run(task='WantedQuests', success=True, finish=True)
            return
        time_delta = timedelta(hours=-before_end.hour, minutes=-before_end.minute, seconds=-before_end.second)
        now_datetime = datetime.now()
        now_time = now_datetime.time()
        if time(hour=5) <= now_time < time(hour=18):
            # 如果是在5点到18点之间，那就设定下一次运行的时间为第二天的5点 + before_end
            next_run_datetime = datetime.combine(now_datetime.date() + timedelta(days=1), time(hour=5))
            next_run_datetime = next_run_datetime + time_delta
        elif time(hour=18) <= now_time < time(hour=23, minute=59, second=59):
            # 如果是在18点到23点59分59秒之间，那就设定下一次运行的时间为第二天的18点 + before_end
            next_run_datetime = datetime.combine(now_datetime.date() + timedelta(days=1), time(hour=18))
            next_run_datetime = next_run_datetime + time_delta
        else:
            # 如果是在0点到5点之间，那就设定下一次运行的时间为今天的18点 + before_end
            next_run_datetime = datetime.combine(now_datetime.date(), time(hour=18))
            next_run_datetime = next_run_datetime + time_delta
        self.set_next_run(task='WantedQuests', target=next_run_datetime)

    def pre_work(self):
        """
        前置工作，
        :return:
        """
        self.goto_page(page_main)
        done_timer = Timer(5)
        while 1:
            self.screenshot()
            if self.appear(self.I_TRACE_DISABLE):
                break
            if self.appear_then_click(self.I_WQ_SEAL, interval=1):
                continue
            if self.appear_then_click(self.I_WQ_DONE, interval=1):
                continue
            if self.appear_then_click(self.I_TRACE_ENABLE, interval=1):
                continue
            if self.special_main and self.click(self.C_SPECIAL_MAIN, interval=3):
                logger.info('Click special main left to find wanted quests')
                continue
            if self.appear(self.I_UI_BACK_RED):
                if not done_timer.started():
                    done_timer.start()
            if done_timer.started() and done_timer.reached():
                self.ui_click_until_disappear(self.I_UI_BACK_RED)
                return False
        # 已追踪所有任务
        logger.info('All wanted quests are traced')

        # 存在协作任务则邀请
        self.screenshot()
        if self.appear(self.I_WQ_INVITE_1) or self.appear(self.I_WQ_INVITE_2) or self.appear(self.I_WQ_INVITE_3):
            if self.need_invite_vip():
                self.all_cooperation_invite()
            else:
                self.invite_five()
        self.ui_click_until_disappear(self.I_UI_BACK_RED)
        self.goto_page(page_exploration)
        return True

    def pre_work_cooperation_only(self):
        if self.get_current_page() != page_main:
            self.goto_page(page_main)
        # 打开悬赏封印 界面
        done_timer = Timer(5)
        while 1:
            self.screenshot()
            if self.appear(self.I_TRACE_ENABLE) or self.appear(self.I_TRACE_DISABLE):
                break
            if self.appear_then_click(self.I_WQ_SEAL, interval=1):
                continue
            if self.appear_then_click(self.I_WQ_DONE, interval=1):
                continue
            if self.special_main and self.click(self.C_SPECIAL_MAIN, interval=3):
                logger.info('Click special main left to find wanted quests')
                continue
            if self.appear(self.I_UI_BACK_RED):
                if not done_timer.started():
                    done_timer.start()
            if done_timer.started() and done_timer.reached():
                self.ui_click_until_disappear(self.I_UI_BACK_RED)
                return False

        if not (self.appear(self.I_WQ_INVITE_1) or self.appear(self.I_WQ_INVITE_2) or self.appear(self.I_WQ_INVITE_3)):
            logger.info("there is no cooperation quest")
            return False

        # 追踪任务 并邀请
        self.all_cooperation_invite()

        self.ui_click_until_disappear(self.I_UI_BACK_RED)
        self.goto_page(page_exploration)
        return True

    def trace_one(self, btn: RuleImage):
        """
            参数必须为邀请按钮(I_WQ_INVITE_n ),特定场景,就不做通用的函数了,怪麻烦的,若还有什么奇葩需求,再扩展吧
        @param btn: 邀请按钮,
        @type btn:
        """
        self.screenshot()
        if not self.appear(btn):
            return
        while 1:
            self.screenshot()
            # 追踪成功  或  是现世任务 不需要追踪
            if self.appear(self.I_WQ_TRACE_ONE_ENABLE) or self.appear(self.I_WQ_TRACE_ONE_REALWORLD):
                break
            if self.appear(self.I_WQ_TRACE_ONE_DISABLE):
                self.click(self.I_WQ_TRACE_ONE_DISABLE, interval=1.5)
                continue
            # 根据邀请按钮位置生成 对应的点击位置 打开追踪界面
            # NOTE magic Number

            self.device.click(btn.roi_front[0], btn.roi_front[1] - 40, control_name=str(btn) + ' y-40')
            # 防止点击后界面来不及刷新
            sleep(1.5)
        # 关闭单个任务的追踪界面
        self.ui_click_until_smt_disappear(self.C_WQ_TRACE_ONE_CLOSE, stop=self.I_WQ_TRACE_ONE_CHECK_OPENED,
                                          interval=1.5)

    def execute_mission(self, num_want: int):
        """
        执行对应的悬赏任务
        :param num_want: 一共要打败的怪物数量
        :return:
        """
        logger.hr('Start wanted quests')
        if not self.appear(self.I_GOTO_1):
            # 如果没有出现 '前往'按钮， 那就是这个可能是神秘任务但是没有解锁
            logger.info('This is a secret mission but not unlock')
            self.ui_click(self.I_TRACE_TRUE, self.I_TRACE_FALSE)
            return False
        # 跳过不想打的
        monster_name = self.O_WQ_MONSTER_TYPE.detect_text(self.device.image)
        if monster_name in self.unwanted_boss_name_list:
            logger.warning(f'unwanted {monster_name}')
            self.ui_click(self.I_TRACE_TRUE, self.I_TRACE_FALSE)
            return False
        # 获取排序后的悬赏信息列表
        ordered_wq_infos = self.get_ordered_wq_infos(num_want)
        if not ordered_wq_infos:
            logger.info('Current wanted quest skipped all, cancel it')
            self.ui_click(self.I_TRACE_TRUE, self.I_TRACE_FALSE)
            return False
        wq_call_dict: dict[WQType, Callable] = {
            WQType.CHALLENGE: self.challenge,
            WQType.EXPLORE: self.explore,
            WQType.SECRET: self.secret
        }
        # 获取当前需要执行的悬赏策略
        wq_info = self.get_need_exec_wq(ordered_wq_infos)
        if not wq_info:
            logger.info('Current wanted quests can not be executed')
            self.ui_click(self.I_TRACE_TRUE, self.I_TRACE_FALSE)
            return False
        try:
            logger.info(f'Choose wq: {wq_info}')
            wq_call_dict[wq_info.type](wq_info.goto_btn, wq_info.do_num)
        except ExploreWantedBoss:
            logger.warning('Maybe only need attack boss')
        finally:
            self.wq_executed_set.add(wq_info)
            self.goto_page(page_exploration)

    def get_need_exec_wq(self, ordered_wq_infos: List[WQInfo]) -> Optional[WQInfo]:
        """获取需要执行的悬赏(按优先级选择最靠前的)"""
        for wq_info in ordered_wq_infos:
            if WQType.CHALLENGE == wq_info.type:
                number_challenge = self.O_WQ_NUMBER.ocr(self.device.image)
                if number_challenge < 5:  # 挑战卷5张都没有了, 省着点吧试试别的
                    logger.warning("Challenge ticket num < 5, skip")
                    continue
            return wq_info
        return None

    def get_ordered_wq_infos(self, num_want: int) -> List[WQInfo]:
        """获取当前悬赏妖怪页面排好序的信息列表, 会自动排除无法执行的悬赏"""
        wq_type_ocr = [self.O_WQ_TYPE_1, self.O_WQ_TYPE_2, self.O_WQ_TYPE_3, self.O_WQ_TYPE_4]
        wq_info_ocr = [self.O_WQ_INFO_1, self.O_WQ_INFO_2, self.O_WQ_INFO_3, self.O_WQ_INFO_4]
        goto_btn_list = [self.I_GOTO_1, self.I_GOTO_2, self.I_GOTO_3, self.I_GOTO_4]
        wq_info_list = []
        for i in range(4):
            wq_info = self.build_wq_info(wq_type_ocr[i], wq_info_ocr[i], goto_btn_list[i], num_want)
            if not wq_info:
                continue
            # 跳过高层秘闻
            if wq_info.dest[-1] in {"捌", "玖", "拾", "番外"}:
                logger.warning('This secret layer is too high, skip')
                continue
            # 跳过已经执行过的(例:都是探索第5层4只怪, 上次计算需要打2次但是这次还是打2次, 肯定出问题了也不需要执行了)
            if wq_info in self.wq_executed_set:
                logger.warning('This wanted quest has been executed, skip')
                continue
            wq_info_list.append(wq_info)
        # 排序
        type_ordered_list = self.get_config()._wq_type_ordered_list
        wq_info_list.sort(key=lambda x: type_ordered_list.index(x.type))
        return wq_info_list

    def build_wq_info(self, type_rule: RuleOcr, info_rule: RuleOcr, goto_btn_rule: RuleImage, num_want: int) -> Optional[WQInfo]:
        """
        构建单条悬赏信息
        :param type_rule: 悬赏类型
        :param info_rule: 悬赏信息
        :param goto_btn_rule: 前往按钮
        :param num_want: 想要攻击的数量
        :return: WQInfo
        """
        wq_type_txt = type_rule.ocr(self.device.image)
        # 适配老逻辑, 将式神碎片改为挑战
        wq_type_txt = '挑战' if wq_type_txt == '式神' else wq_type_txt
        if wq_type_txt == '' or not WQType.contains(wq_type_txt):
            logger.warning(f'Unknown wq type: {wq_type_txt}')
            return None
        wq_type = WQType(wq_type_txt)
        type_ordered_list = self.get_config()._wq_type_ordered_list
        if wq_type not in type_ordered_list:
            logger.warning(f'{wq_type.value} is not in the order list')
            return None
        wq_info_txt = info_rule.ocr(self.device.image)
        wq_info_txt = wq_info_txt.replace('：', ':').replace('（', '(').replace('）', ')')
        import re
        match = re.search(r"(.+?)\s*\(?[数教]量[:：]\s*(\d+)", wq_info_txt)
        if not match:
            logger.warning(f'Unknown wq info: {wq_info_txt}')
            return None
        wq_dest, wq_number = match.group(1).strip(), int(match.group(2))
        do_num = num_want // wq_number + (num_want % wq_number > 0)
        return WQInfo(wq_type, wq_dest, wq_number, goto_btn_rule, do_num)

    def challenge(self, goto_btn, num):
        self.ui_click(goto_btn, self.I_WQC_FIRE)
        self.ui_click(self.I_WQC_UNLOCK, self.I_WQC_LOCK)
        self.ui_click_until_disappear(self.I_WQC_FIRE)
        # 锁定阵容进入战斗
        wq_config = GeneralBattleConfig(lock_team_enable=True)
        self.run_general_battle(config=wq_config, exit_matcher=self.I_WQC_FIRE)

    def secret(self, goto, num=1):
        self.ui_click(goto, self.I_WQSE_FIRE)
        for i in range(num):
            self.screenshot()
            # 若是当周特殊秘闻则禁止连续进攻, 战斗结束之后直接退到探索页面重新进入挑战(避免当周秘闻没打结果跳转到第一层)
            if self.appear(self.I_WQSE_SPECIAL_FIRE):
                logger.warning('Current is special secret, exit and retry')
                return 
            # 又臭又长的对话针的是服了这个网易
            click_count = 0
            while 1:
                self.screenshot()
                if self.get_current_page() in [page_battle_prepare, page_battle]:
                    self.run_general_battle(self.battle_config, exit_matcher=any_of(self.I_UI_BACK_RED, self.I_WQSE_SPECIAL_FIRE))
                    break
                if self.appear_then_click(self.I_WQSE_FIRE, interval=1):
                    continue
                if self.appear(self.I_UI_BACK_RED, threshold=0.7) and not self.appear(self.I_WQSE_FIRE):
                    self.click(self.C_SECRET_CHAT, interval=0.8)
                    click_count += 1
                    if click_count >= 6:
                        logger.warning('Secret mission chat too long, force to close')
                        click_count = 0
                        self.device.click_record_clear()
        logger.info('Secret mission finished')

    def invite_random(self, add_button: RuleImage):
        self.screenshot()
        if not self.appear(add_button):
            return False
        self.ui_click(add_button, self.I_WQ_INVITE_ENSURE, interval=2.5)
        logger.info('enter invite form')
        sleep(1)
        self.click(self.I_WQ_FRIEND_1)
        sleep(0.4)
        self.click(self.I_WQ_FRIEND_2)
        sleep(0.4)
        self.click(self.I_WQ_FRIEND_3)
        sleep(0.4)
        self.click(self.I_WQ_FRIEND_4)
        sleep(0.4)
        self.click(self.I_WQ_FRIEND_5)
        sleep(0.2)
        self.screenshot()
        if not self.appear(self.I_SELECTED):
            logger.warning('No friend selected')
            return False
        self.ui_click_until_disappear(self.I_INVITE_ENSURE)
        sleep(0.5)

    def invite_five(self):
        """
        邀请好友，默认点五个
        :return:
        """

        logger.hr('Invite friends')
        self.invite_random(self.I_WQ_INVITE_1)
        self.invite_random(self.I_WQ_INVITE_2)
        self.invite_random(self.I_WQ_INVITE_3)

    def all_cooperation_invite(self, name_all: str = None):
        """
            所有的协作任务依次邀请
            如果配置了只完成协作任务 还会将该任务设置为追踪
        @return:

        """
        self.screenshot()
        if not self.appear(self.I_WQ_INVITE_1):
            return False

        ret = self.get_cooperation_info()
        if len(ret) == 0:
            logger.info("no Cooperation found")
            return False
        typeMask = 15
        typeMask = CooperationSelectMask[(self.get_config()).cooperation_type.value]
        for item in ret:
            # 该任务是需要邀请的任务类型
            if not (item['type'] & typeMask):
                # BUG 存在多个协作任务时,邀请完第一个协作任务对方接受后,未邀请的任务位置无法确定(缺少信息)
                # 例如 按顺序存在 abc 3个协作任务,邀请完a,好友接受后,这三个任务在界面上的顺序变化,abc 还是bca
                # 如果顺序不变 则应该没有问题
                logger.info("cooperationType %s But needed Type %s ,Skipped", item['type'], typeMask)
                break
            '''
               尝试5次 如果邀请失败 等待20s 重新尝试
               阴阳师BUG: 好友明明在线 但邀请界面找不到该好友(好友未接受任何协作任务的情况下)
           '''
            index = 0
            item['inviteResult'] = False
            if name_all is None:
                name = self.get_invite_vip_name(item['type'])
            else:
                name = name_all
            logger.warning("find cooperationType %s ,start invite %s", item['type'], name)
            while index < 5:
                if self.cooperation_invite(item['inviteBtn'], name):
                    item['inviteResult'] = True
                    index = 5
                    continue
                logger.info("%s not found,Wait 20s,%d invitations left", name, 5 - index - 1)
                index += 1
                sleep(20) if index < 5 else sleep(0)
                # NOTE 等待过程如果出现协作邀请 将会卡住 为了防止卡住
                self.screenshot()
            # 邀请追踪一起吧,只有邀请成功才追踪
            if item['inviteResult']:
                self.invite_success_callback(item['type'], name)
                if (self.get_config()).cooperation_only:
                    logger.info("start trace_one")
                    self.trace_one(item['inviteBtn'])
        return ret

    def cooperation_invite(self, btn: RuleImage, name: str):
        """
            单个协作任务邀请
        @param btn:
        @param name:
        @return:
        """
        self.ui_click(btn, stop=self.I_WQ_INVITE_ENSURE, interval=2.5)

        # 选人
        self.O_WQ_INVITE_COLUMN_1.keyword = name
        self.O_WQ_INVITE_COLUMN_2.keyword = name

        find = False
        for i in range(2):
            self.wait_until_appear(self.I_WQ_INVITE_FRIEND_LIST_APPEAR, wait_time=4)
            self.screenshot()
            in_col_1 = self.ocr_appear_click(self.O_WQ_INVITE_COLUMN_1)
            in_col_2 = self.ocr_appear_click(self.O_WQ_INVITE_COLUMN_2)
            find = in_col_2 or in_col_1
            if find:
                self.wait_until_appear(self.I_WQ_INVITE_SELECTED, wait_time=2)
                self.screenshot()
                if self.appear(self.I_WQ_INVITE_SELECTED):
                    logger.info("friend found and selected")
                    break
                # TODO OCR识别到文字 但是没有选中 尝试重新选择  (选择好友时,弹出协作邀请导致选择好友失败)
            # 检测跨服好友按钮是否高亮
            while 1:
                self.screenshot()
                if not self.appear_highlight(self.I_WQ_INVITE_DIFF_SVR_HIGHLIGHT):
                    self.click(self.I_WQ_INVITE_DIFF_SVR)
                    continue
                break
            # 等待好友列表加载
            self.wait_until_appear(self.I_WQ_INVITE_DIFF_SVR_HIGHLIGHT, wait_time=4)
        # 没有找到需要邀请的人,点击取消 返回悬赏封印界面
        if not find:
            self.screenshot()
            self.ui_click_until_disappear(self.I_WQ_INVITE_CANCEL, interval=1.5)
            return False
        #
        self.ui_click_until_disappear(self.I_WQ_INVITE_ENSURE, interval=1)
        return True

    def get_cooperation_info(self) -> List:
        """
            获取协作任务详情
        @return: 协作任务类型与邀请按钮
        """
        self.screenshot()
        retList = []
        i = 0
        for index in range(3):
            btn = self.__getattribute__("I_WQ_INVITE_" + str(index + 1))
            if not self.appear(btn):
                break
            if self.appear(self.__getattribute__("I_WQ_COOPERATION_TYPE_JADE_" + str(index + 1))):
                retList.append({'type': CooperationType.Jade, 'inviteBtn': btn})
                continue
            if self.appear(self.__getattribute__("I_WQ_COOPERATION_TYPE_DOG_FOOD_" + str(index + 1))):
                retList.append({'type': CooperationType.Food, 'inviteBtn': btn})
                continue
            if self.appear(self.__getattribute__("I_WQ_COOPERATION_TYPE_CAT_FOOD_" + str(index + 1))):
                retList.append({'type': CooperationType.Food, 'inviteBtn': btn})
                continue
            if self.appear(self.__getattribute__("I_WQ_COOPERATION_TYPE_SUSHI_" + str(index + 1))):
                retList.append({'type': CooperationType.Sushi, 'inviteBtn': btn})
                continue
            # NOTE 因为食物协作里面也有金币奖励 ,所以判断金币协作放在最后面
            if self.appear(self.__getattribute__("I_WQ_COOPERATION_TYPE_GOLD_" + str(index + 1))):
                retList.append({'type': CooperationType.Gold, 'inviteBtn': btn})
                continue
        logger.info(f"get cooperation size {len(retList)}")
        return retList

    # 使用平均亮度检测是否一致
    def appear_highlight(self, rule_image: RuleImage):
        return match_highlight_rule(rule_image, self.device.image, frame_id=self.device.image_frame_id)

    @cached_property
    def special_main(self) -> bool:
        # 特殊的庭院需要点一下，左边然后才能找到图标
        main_type = self.config.global_game.costume_config.costume_main_type
        if main_type == MainType.COSTUME_MAIN_3:
            return True
        return False

    def get_config(self) -> WantedQuestsConfig:
        return self.config.wanted_quests.wanted_quests_config

    def need_invite_vip(self):
        return bool(self.get_config().invite_friend_name)

    def get_invite_vip_name(self, ctype: CooperationType):
        return self.get_config().invite_friend_name

    def invite_success_callback(self, ctype: CooperationType, name):
        """
           邀请成功回调
        @param ctype:
        @type ctype:
        @param name:
        @type name:
        """

        return True

    def process_ocr(self, txt):
        def detect_spliter(txt):
            index = txt.find('/')
            if index != -1:
                return index
            # 由于斜杠'/'经常被误识别为'7',且悬赏封印悬赏怪物总数没有与‘7’相关的数字
            reg = re.compile(r'^(\d+)([7/])(\d+)$')
            match = reg.match(txt)
            if match:
                return match.start(2)
            return -1

        index = detect_spliter(txt)
        if index < 0:
            return 0, 0, 0
        return int(txt[:index]), 1, int(txt[index + 1:])

    def txt_ocr_appear(self, ocr_item: RuleOcr, reg, img):
        res = ocr_item.ocr(img)
        regex = re.compile(reg)
        ismatch = regex.match(res)
        return ismatch is not None

    def find_wq(self, img) -> tuple[int, int, int, List[int]]:
        """
        在探索页面从悬赏列表中找到可以执行的任务, 自动过滤已完成的任务(根据下方数字判断, 例12/12)

        :param img: 当前截图
        :return: (已完成数量, 剩余数量, 总数量, roi列表)
        """

        def calc_xywh(box) -> List[int]:
            """计算最终ocr文本位于整张截图的roi(因为detect_and_ocr返回的位置是基于截取之后的图像的位置,所以需要拼接)"""
            rec_x, rec_y, rec_w, rec_h = box[0, 0], box[0, 1], box[1, 0] - box[0, 0], box[2, 1] - box[0, 1]
            x = rec_x + self.O_WQ_TEXT_ALL.roi[0]
            y = rec_y + self.O_WQ_TEXT_ALL.roi[1]
            w = rec_w
            h = rec_h
            return [x, y, w, h]

        res_list = self.O_WQ_TEXT_ALL.detect_and_ocr(img, model="medium")
        import re
        reg_time = re.compile(r'^D?([01]?[0-9]|2[0-3]):([0-5]?[0-9]):?([0-5]?[0-9])?$')
        reg_fengyin = re.compile(r'.*[封|野]印.*')
        # 由于斜杠'/'经常被误识别为'7',且悬赏封印悬赏怪物总数没有与‘7’相关的数字
        reg_progress = re.compile(r'^(\d+)([7/])(\d+)$')
        # 没有检测到斜杠，符合格式：前N位与后N位相同,表示已完成
        reg_XX = re.compile(r'^(\d+)\1$')
        # 过滤掉协或者未知悬赏等其他无用字符
        reg_other = re.compile(r'[?？协边]')
        for index, res in enumerate(res_list):
            if reg_fengyin.match(res.ocr_text):
                continue
            if reg_time.match(res.ocr_text):
                continue
            if reg_other.match(res.ocr_text) is not None:
                continue
            if match := reg_progress.match(res.ocr_text):
                spliter_index = match.start(2)
                xywh = calc_xywh(res.box)
                cu, re, total = int(res.ocr_text[:spliter_index]), 1, int(res.ocr_text[spliter_index + 1:])
                # 识别结果规范性检查
                if total > 14:
                    logger.warning("Total number of wanted quests is greater than 14")
                    total = total % 10
                if cu > total:
                    logger.warning('Current number of wanted quests is greater than total number')
                    cu = cu % 10
                if cu == total:
                    # 该任务已完成，一般是悬赏任务，邀请人没有做导致的
                    continue
                logger.info(f'find wq {res.ocr_text} @ {xywh}')
                return cu, re, total, xywh
            # 例如：1414 66 1212
            if reg_XX.match(res.ocr_text):
                continue
        return -1, -1, -1, [0, 0, 0, 0]

    def is_wq_remained(self):
        # 检测是否还存在任务
        return self.appear(self.O_WQ_LIST_CHECK)


if __name__ == '__main__':
    import re
    # 原始版本
    strict_pattern = re.compile(r"^(.+?)\(?[数教]量:\s*(\d+)\)?$")
    # OCR容错版本
    ocr_pattern = re.compile(r"(.+?)\s*\(?[数教]量[:：]\s*(\d+)")
    test_cases = [
        "第十章(数量:2)",
        '第十章(数量:2)"',
        '第十章(数量:2""',
        "第十章 数量:2",
        "第十章 数量：2",
        "第十章(数量：2)",
        "第十章 (数量: 2)",
        "第十章(教量:2)",
        "第十章(数量:2abc)",
        "第十章(数量:20)",
        "第十章数量:2",
        "第十章",
        "",
    ]
    test_cases.extend([
        "第十章（数量：2）",  # 中文括号
        "第十章(数最:2)",  # OCR错字
        "第十章(数量:Z)",  # OCR数字识别失败
        "第十章(数量:2 )",
        "第十章(数量: 2)",
        "第十章(数量:02)",
        "第十章(数量:2.”)",
        "第十章(数量:2。)",
    ])

    def test(pattern, text):
        match = pattern.search(text)
        if not match:
            return "❌ 不匹配"
        return (
            f"✅ 匹配 "
            f"dest=[{match.group(1).strip()}], "
            f"number=[{int(match.group(2))}]"
        )

    for text in test_cases:
        print("=" * 60)
        print(f"输入: {repr(text)}")
        print("\n【严格模式】")
        print(test(strict_pattern, text))
        print("\n【OCR容错模式】")
        print(test(ocr_pattern, text))
        print()
