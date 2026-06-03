import random
import re
from module.atom.image import RuleImage
from module.atom.ocr import RuleOcr
from module.base.timer import Timer
from module.logger import logger
from tasks.GameUi.navigator import GameUi
from tasks.SixRealms.assets import SixRealmsAssets
from typing import List, Optional, Callable
import tasks.SixRealms.page as pages


class SixRealmsCommon(GameUi, SixRealmsAssets):

    def get_skill_select(self, skill_rule_list: List[RuleImage]) -> RuleImage:
        """
        获取技能对应的选择按钮
        :param skill_rule_list: 技能列表
        :return: 技能对应的选择按钮(默认最后一个)
        """
        if not skill_rule_list:
            return self.I_SELECT_3
        for skill_rule in skill_rule_list:
            if not self.appear(skill_rule):
                continue
            logger.info(f'Recognize skill: {skill_rule.name}')
            x, y = skill_rule.front_center()
            if x < 360:
                return self.I_SELECT_0
            if 360 <= x < 640:
                return self.I_SELECT_1
            if 640 <= x < 960:
                return self.I_SELECT_2
            break
        return self.I_SELECT_3

    def get_coin_num(self, coin_rule: RuleImage | RuleOcr) -> int:
        """
        根据规则获取钱币数量(图像:获取右下角数字 文字:直接返回对应数字)
        :param coin_rule: 钱币规则
        :return: 钱币数量
        """
        if isinstance(coin_rule, RuleOcr):
            coin_num = coin_rule.ocr(self.device.image)
            logger.info(f'Current coin: {coin_num}')
            return coin_num
        x, y, width, height = coin_rule.roi_front
        self.O_EXTRA_COIN_NUM.roi = [x + 25, y + 47, width - 5, height - 23]
        extra_coin = self.O_EXTRA_COIN_NUM.ocr_digit(self.device.image)
        extra_coin = int(extra_coin) if extra_coin != "" else 0
        return extra_coin

    def open_shop(self, store_rule: RuleImage, store_page: pages.Page) -> bool:
        """
        手动打开商店
        :param store_rule: 进入商店的规则
        :param store_page: 商店页面
        :return: 成功进入商店True, 否则False
        """
        timeout_timer = Timer(5).start()
        while not timeout_timer.reached():
            self.screenshot()
            if self.get_current_page() == store_page:
                return True
            if self.appear_then_click(self.I_UI_CONFIRM):
                continue
            if self.appear_then_click(store_rule, interval=1.5):
                continue
        self.appear_then_click(self.I_UI_CANCEL)
        return False

    def enter_battle(self, fire_rule: RuleImage, boss_unlock: RuleImage = None, boss_lock: RuleImage = None,
                     normal_unlock: RuleImage = None, normal_lock: RuleImage = None) -> bool:
        """
        进入战斗
        :param fire_rule: 点击进入战斗的挑战规则
        :param boss_unlock: boss战前的解锁
        :param boss_lock: boss战前的锁定
        :param normal_unlock: 普通怪战前的解锁
        :param normal_lock: 普通怪战前的锁定
        :return: 成功进入战斗True, 否则False
        """
        normal_unlock = normal_unlock if normal_unlock else self.I_BATTLE_TEAM_UNLOCK
        normal_lock = normal_lock if normal_lock else self.I_BATTLE_TEAM_LOCK
        if self.appear(normal_unlock):
            self.ui_click(normal_unlock, normal_lock, interval=0.8)
        if boss_unlock and self.appear(boss_unlock):
            self.ui_click(boss_unlock, boss_lock, interval=0.8)
        self.device.stuck_record_clear()
        timeout_timer = Timer(5).start()
        while not timeout_timer.reached():
            self.screenshot()
            if self.get_current_page() in (pages.page_battle_prepare, pages.page_battle, pages.page_battle_result):
                return True
            self.appear_then_click(fire_rule, interval=0.8)
        return False

    def refresh_store(self, refresh_rule: RuleImage, refresh_times_rule: RuleOcr) -> bool:
        """
        刷新商店
        :param refresh_rule: 刷新图标
        :param refresh_times_rule: 刷新次数文本
        :return: 成功刷新返回True, 否则False
        """
        logger.info('Refresh store')
        text = refresh_times_rule.ocr(self.device.image)
        matches = re.search(f"剩\d+次", text)
        if not matches:
            logger.warning('Refresh time not match, exit')
            return False
        refresh_time = int(matches.group()[1])
        logger.info(f'Refresh time: {refresh_time}')
        if refresh_time <= 0:
            logger.warning('Refresh time is 0')
            return False
        if not self.appear_then_click(refresh_rule):
            return False
        self.wait_animate_stable(self.C_STORE_ANIMATE_KEEP, timeout=1.5)
        logger.info('Refresh store done')
        return True

    def buy_skill(self, skill_rule: RuleImage, skill_price: int, coin_num_rule: RuleOcr,
                  fresh_rule: RuleImage, refresh_times_rule: RuleOcr, buy_num: int = 99) -> tuple[int, int]:
        """
        购买技能
        :param skill_rule: 技能图标
        :param skill_price: 技能价格
        :param coin_num_rule: 金币数量文本
        :param fresh_rule: 刷新图标
        :param refresh_times_rule: 刷新次数文本
        :param buy_num: 最大购买次数
        :return: (剩余金币数量, 购买次数)
        """
        coin_num = coin_num_rule.ocr(self.device.image)
        buy_interval_timer = Timer(1.5)  # 控制购买间隔
        buy_cnt = 0
        while True:
            self.screenshot()
            if self.appear_then_click(self.I_UI_CONFIRM, interval=0.7):
                continue
            if not buy_interval_timer.reached():
                continue
            buy_interval_timer.reset()
            coin_num = coin_num_rule.ocr(self.device.image)
            logger.info(f'Current coin: {coin_num}')
            if buy_cnt >= buy_num:
                logger.info(f'Buy {skill_rule.name} done')
                break
            if coin_num < skill_price:
                logger.info(f'Not enough coin to buy {skill_rule.name}')
                break
            if self.appear(skill_rule):  # 点击购买技能的左侧位置
                x, y = skill_rule.front_center()
                x -= random.randint(35, 60)
                y += random.randint(-skill_rule.roi_front[3] // 2, skill_rule.roi_front[3] // 2)
                self.device.click(x=x, y=y, control_name=skill_rule.name)
                buy_cnt += 1
                continue
            if coin_num < skill_price + 100:
                logger.info('Not enough coin to refresh and buy')
                break
            if not self.refresh_store(fresh_rule, refresh_times_rule):
                break
        logger.info(f'Finish purchase {skill_rule.name} times: {buy_cnt}')
        return coin_num, buy_cnt

    def get_remain_turns(self, remain_rule: RuleOcr) -> int:
        """
        获取剩余回合数
        :param remain_rule: 回合数文本
        :return: 剩余回合数(识别失败则返回99)
        """
        remain_turns_txt = remain_rule.ocr(self.device.image)
        match = re.search(r'\d{1,2}', remain_turns_txt)
        remain_turns = 99
        if not set(remain_turns_txt).isdisjoint(set('回合')) and match:
            remain_turns = int(match.group())
        return remain_turns

    def _filter_island(self, appeared_islands: list[RuleImage]) -> list[RuleImage]:
        """
        自定义岛屿选择逻辑
        :param appeared_islands: 识别到的岛屿列表
        :return: 过滤后的岛屿
        """
        return appeared_islands

    def choose_and_enter_island(self, island_rule_list: list[RuleImage]):
        """
        选择并进入第一个岛屿(并不保证进入成功, 因此需要允许多次调用该函数)
        :param island_rule_list: 备选的岛屿列表
        """
        self.prepare_appear_cache(island_rule_list)
        appeared_lands = [land for land in island_rule_list if self.appear(land)]
        if len(appeared_lands) == 0:
            logger.info('No land recognized, retry')
            return
        filtered_islands = self._filter_island(appeared_lands)
        if len(filtered_islands) == 0:
            logger.info('No remain island can choose, retry')
            return
        target_land = filtered_islands[0]  # 取第一个岛屿
        self.appear_then_click(target_land, interval=0.8)
        