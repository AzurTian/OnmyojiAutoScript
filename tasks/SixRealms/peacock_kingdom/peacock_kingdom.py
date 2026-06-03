import time

from module.atom.image import RuleImage
from module.exception import TaskEnd
from module.logger import logger
from tasks.SixRealms.peacock_kingdom.base_peacock_kingdom import BasePeacockKingdom
import tasks.SixRealms.peacock_kingdom.page as pages
from typing import Callable


class PeacockKingdom(BasePeacockKingdom):

    def _default_detect_categories(self) -> set[str]:
        categories = super()._default_detect_categories()
        categories.add("six_realms")
        categories.add("peacock_kingdom")
        return categories

    @property
    def pk_page_handle_dict(self) -> dict[pages.Page, Callable]:
        return {
            pages.page_peacock_kingdom: self.run_on_pk,
            pages.page_pk_prepare: lambda : self.goto_page(pages.page_pk_main),
            pages.page_pk_main: self.run_on_pk_main,
            pages.page_pk_shop_land: self.run_on_pk_store,
            pages.page_pk_mistery_land: lambda : self.goto_page(pages.page_pk_main),
            pages.page_pk_chaos_land: self.run_on_pk_chaos,
            pages.page_pk_bloom_land: lambda : self.goto_page(pages.page_pk_main),
            pages.page_pk_battle_land: self.run_on_pk_battle,
            pages.page_pk_challenge: self.run_on_pk_challenge,
            pages.page_pk_map: lambda: self.goto_page(pages.page_pk_main),
            pages.page_pk_exit: lambda: self.click(pages.random_click(ltrb=(True, False, False, False)), interval=1.2),
            pages.page_sr_prepare_exit: lambda: self.goto_page(pages.page_pk_prepare),
            pages.page_sr_open_store: lambda: self.goto_page(pages.page_pk_main),
            pages.page_battle_prepare: self.run_on_pk_challenge,
            pages.page_battle: self.run_on_pk_challenge,
            pages.page_battle_result: self.run_on_pk_challenge,
            pages.page_reward: lambda: self.click(pages.random_click(), interval=1.2),
        }

    def run(self):
        self.before_run()
        logger.hr('Peacock Kingdom', 1)
        while True:
            self.screenshot()
            current_page = self.get_current_page()
            if current_page is None:
                time.sleep(0.5)
                continue
            handle = self.pk_page_handle_dict.get(current_page, None)
            if handle is None:
                self.goto_page(pages.page_peacock_kingdom)
                continue
            try:
                handle()
            except TaskEnd:
                break
                
    def run_on_pk(self):
        """孔雀国界面"""
        if self.appear_then_click(self.I_PK_CONTINUE, interval=1):
            return
        if self.appear_then_click(self.I_PK_START, interval=1):
            return

    def run_on_pk_prepare(self):
        """进入孔雀国主界面前的准备界面"""
        if self.appear_then_click(self.I_PK_START_CONFIRM, interval=1.5) or \
                self.appear_then_click(self.I_PK_START_CONFIRM2, interval=1.5) or \
                self.appear_then_click(self.I_PK_START_THIRD_SKILL, interval=1.5) or \
                self.appear_then_click(self.I_MFIRST_SKILL, interval=1.5):
            return

    def _filter_island(self, appeared_islands: list[RuleImage]) -> list[RuleImage]:
        remain_turns = self.get_remain_turns(self.O_REMAIN_TURNS)
        appeared_shop = self.appear(self.I_PK_LAND_STORE)
        # 当前没有商店且已经跳过两个绽放之屿了(剩余不到9回合), 还是没有轰雷, 则只要钱够就开商店找轰雷
        if not appeared_shop and self.skill_roaring_thunder == 0 and remain_turns <= 9 and self.coin_num >= 600:
            self.open_shop(self.I_M_STORE_ACTIVITY, pages.page_pk_shop_land)
            return []
        # 出现商店&岛屿数量>2&金币不够买轰雷&剩余回合数>1, 则不选择商店, 先攒金币
        if appeared_shop and len(appeared_islands) >= 2 and self.coin_num < 300 and remain_turns > 1:
            logger.info('Money is not enough, choose other land')
            appeared_islands.remove(self.I_PK_LAND_STORE)
        return appeared_islands

    def run_on_pk_main(self):
        """孔雀国主界面 执行策略选岛屿"""
        if self.appear(self.I_PK_BOSS_PREPARE) and \
                self.enter_battle(self.I_PK_BOSS_FIRE, boss_unlock=self.I_PK_BOSS_UNLOCK, boss_lock=self.I_PK_BOSS_LOCK):
            logger.info('Start boss battle')
            self.run_general_battle(battle_key='boss', exit_matcher=pages.page_peacock_kingdom)
            raise TaskEnd
        # 优先级：商店 > 神秘 > 绽放之屿 > 战斗 > 混沌
        islands = [self.I_PK_LAND_STORE, self.I_PK_LAND_MYSTERY, self.I_PK_LAND_BLOOM, self.I_PK_LAND_FIRE,
                 self.I_PK_LAND_CHAOS]
        self.choose_and_enter_island(islands)

    def run_on_pk_challenge(self):
        """孔雀国挑战界面"""
        if self.enter_battle(self.I_PK_BATTLE_FIRE):
            self.run_general_battle(battle_key="normal", exit_matcher=pages.page_pk_main)

    def run_on_pk_store(self):
        """宁息商店"""
        logger.hr('shop land')
        if self.skill_roaring_thunder >= 1:
            logger.info('Skill level is enough, skip shopping')
            self.goto_page(pages.page_pk_main)
            return
        self.coin_num, buy_times = self.buy_skill(self.I_PK_STORE_SKILL_THUNDER, 300, self.O_COIN_NUM,
                                                  self.I_PK_STORE_REFRESH, self.O_PK_STORE_REFRESH_TIME, 1)
        self.skill_roaring_thunder += buy_times
        logger.info(f'Skill level: {self.skill_roaring_thunder}')
        self.goto_page(pages.page_pk_main)

    def run_on_pk_chaos(self):
        """混沌之屿 宝箱/精英"""
        logger.hr('chaos land')
        is_box: bool = self.appear(self.I_PK_CHAOS_BOX)
        if is_box:
            logger.info('Do not get box')
            self.goto_page(pages.page_pk_main)
            return
        self.ui_click(self.C_NPC_FIRE_CENTER, self.I_PK_BATTLE_FIRE, interval=0.8)
        if self.enter_battle(self.I_PK_BATTLE_FIRE):
            logger.info('Start elite battle')
            self.run_general_battle(battle_key="elite", exit_matcher=pages.page_pk_main)

    def run_on_pk_battle(self):
        """鏖战之屿 普通怪"""
        logger.hr('fire land')
        self.ui_click(self.C_NPC_FIRE_RIGHT, self.I_PK_BATTLE_FIRE, interval=0.8)
        if self.enter_battle(self.I_PK_BATTLE_FIRE):
            logger.info('Start normal battle')
            self.run_general_battle(battle_key="normal", exit_matcher=pages.page_pk_main)
