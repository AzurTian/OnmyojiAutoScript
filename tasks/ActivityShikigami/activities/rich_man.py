import random
from cached_property import cached_property
from module.base.protect import random_sleep
from module.base.timer import Timer
from module.logger import logger
from tasks.ActivityShikigami.base_act import BaseAct
from tasks.DemonEncounter.data.answer import Answer
from tasks.Quiz.debug import Debugger, remove_symbols


class RichManAct(BaseAct, Debugger):

    @cached_property
    def answer(self) -> Answer:
        # Misspelling
        return Answer()

    def _run_pass(self):
        """
            更新前请先看 ./README.md
        """
        logger.hr(f'Start run climb type PASS', 1)
        self.click(self.I_TO_BATTLE_MAIN)
        switch_souled = False
        click_ticket, no_tickets = 0, random.randint(4, 6)
        click_fire, no_fire = 0, random.randint(3, 5)
        already_passed = False
        while True:
            self.screenshot()
            self.update_status()
            if self.appear(self.I_RM_NO_TICKET, interval=2) or click_ticket > no_tickets:
                logger.warning(f'Click ticket {click_ticket} times, no tickets left')
                break
            if click_fire > no_fire:
                logger.warning(f'Click fire {click_fire} times, no fire left')
                break
            if self.ui_reward_appear_click():  # 获得奖励
                continue
            if self.appear(self.I_RM_FORWARD, interval=1.2):  # 等待骰子结果
                continue
            if self.appear(self.I_RM_CHECK_BOSS, interval=1.5):
                already_passed = True
                logger.info('Already passed')
            if already_passed and self.appear(self.I_RM_BOSS, interval=1.2):  # 已经通关了且出现首领则退出,否则还要打
                logger.info('Boss passed, exit')
                self.appear_then_click(self.I_UI_BACK_YELLOW, interval=1.2)
                continue
            already_passed = False
            if self.appear_then_click(self.I_UI_CONFIRM, interval=2):
                continue
            if self.appear_then_click(self.I_RM_THROW, interval=2):  # 开始扔骰子
                logger.hr('Throw ticket', 3)
                click_ticket = 0
                self.device.stuck_record_clear()
                self.device.stuck_record_add('BATTLE_STATUS_S')
                while True:
                    self.screenshot()
                    if self.ui_reward_appear_click():  # 获得奖励
                        break
                    if self.appear(self.I_RM_THROW_WIN, interval=1.5):  # 扔骰子获胜
                        logger.info('Throw win')
                        continue
                    if self.appear(self.I_RM_THROW_EQUAL, interval=1.5):  # 扔骰子平局
                        logger.info('Throw equal')
                        continue
                    if self.appear_then_click(self.I_RM_THROW, interval=2):  # 开始扔骰子
                        logger.info('Throw again')
                        self.device.stuck_record_clear()
                        self.device.stuck_record_add('BATTLE_STATUS_S')
                        continue
                continue
            if self.appear(self.I_RM_BUY_AP) or self.appear(self.I_RM_BUY_REWARD) or \
                    self.appear(self.I_RM_BUY_TICKET):  # 开始买东西
                logger.hr('Buy envent', 3)
                click_ticket = 0
                rich_man_conf = self.config.model.activity_shikigami.rich_man
                timeout_timer = Timer(5).start()
                while True:
                    self.screenshot()
                    if self.ui_reward_appear_click():  # 获得奖励跳出循环
                        break
                    if self.appear_then_click(self.I_UI_CONFIRM, interval=1) or \
                            self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1):
                        timeout_timer.reset()
                        continue
                    if timeout_timer.reached():  # 如果购买超时了则说明购买有问题, 则不买了
                        logger.warning('Buy timeout, exit buy')
                        self.appear_then_click(self.I_UI_BACK_RED, interval=1.5)
                        continue
                    if not rich_man_conf.buy_ap and not rich_man_conf.buy_ticket and not rich_man_conf.buy_reward:
                        self.appear_then_click(self.I_UI_BACK_RED, interval=1.5)  # 一个都不买直接退出
                        continue
                    if self.config.model.activity_shikigami.rich_man.buy_ticket and self.appear_then_click(
                            self.I_RM_BUY_TICKET, interval=1.5):
                        continue
                    if self.config.model.activity_shikigami.rich_man.buy_reward and self.appear_then_click(
                            self.I_RM_BUY_REWARD, interval=1.5):
                        continue
                    if self.config.model.activity_shikigami.rich_man.buy_ap and self.appear_then_click(self.I_RM_BUY_AP,
                                                                                                       interval=1.5):
                        continue
            if self.appear(self.I_RM_QUESTION, interval=2):  # 开始答题
                click_ticket = 0
                logger.hr('Start question', 3)
                q, a1, a2, a3 = self.detect_question_and_answers()
                index = self.answer.answer_one(question=q, options=[a1, a2, a3])
                if index is None:
                    logger.error('Now question has no answer, please check')
                    self.append_one(question=q, options=[a1, a2, a3])
                    self.config.notifier.push(title='Quiz',
                                              content=f"New question: \n{q} \n{[a1, a2, a3]}")
                    index = 1
                logger.attr(index, 'Answer')
                self.click([self.O_RM_ANSWER_1, self.O_RM_ANSWER_2, self.O_RM_ANSWER_3][index - 1], interval=1)
                self.device.click_record_clear()
                continue
            if self.appear(self.I_ACT_FIRE, interval=2):  # 开始战斗
                click_ticket = 0
                if not switch_souled:
                    self.switch_soul(self.I_BATTLE_MAIN_TO_RECORDS)
                    switch_souled = True
                if self.conf.general_climb.random_sleep:
                    random_sleep(probability=0.2)
                self.click(self.I_ACT_FIRE)
                click_fire += 1
                self.run_general_battle(self.conf.pass_battle_conf, f"act_{self.climb_type}")
                continue
            # if self.appear(self.I_CHECK_BATTLE_MAIN, interval=3.5):  # 扔门票骰子
            #     self.click(self.I_CHECK_BATTLE_MAIN)
            #     self.device.click_record_clear()
            #     click_ticket += 1
            #     click_fire = 0
            #     continue
        while True:
            self.screenshot()
            if self.appear(self.I_TO_BATTLE_MAIN, interval=1):
                break
            if self.appear_then_click(self.I_UI_CONFIRM, interval=1) or self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1):
                continue
            self.close_unknown_pages()

    def detect_question_and_answers(self) -> tuple:
        self.screenshot()
        results = self.O_RM_QUESTION.detect_and_ocr(self.device.image)
        question = ''
        answer_1 = remove_symbols(self.O_RM_ANSWER_1.ocr(self.device.image))
        answer_2 = remove_symbols(self.O_RM_ANSWER_2.ocr(self.device.image))
        answer_3 = remove_symbols(self.O_RM_ANSWER_3.ocr(self.device.image))

        for result in results:
            # box 是四个点坐标 左上， 右上， 右下， 左下
            # x1, y1, x2, y2 = result.box[0][0], result.box[0][1], result.box[2][0], result.box[2][1]
            # w, h = x2 - x1, y2 - y1
            y_start = result.box[0][1]
            y_end = result.box[2][1]
            text = result.ocr_text
            if y_start >= 0 and y_end <= 150:
                question += text

        return remove_symbols(question), answer_1, answer_2, answer_3
