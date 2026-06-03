from module.logger import logger
import tasks.SixRealms.moon_sea.page as pages
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.GeneralBattle.general_battle import GeneralBattle, BattleContext, BattleAction
from tasks.SixRealms.common import SixRealmsCommon


class BaseMoonSea(GeneralBattle, SixRealmsCommon):
    coin_num = 0  # 钱币数量
    cnt_skill101 = 0  # 柔风等级

    def before_run(self):
        self.coin_num = 0
        self.cnt_skill101 = 0
        pages.page_battle = self.navigator.resolve_page(pages.page_battle)
        pages.page_battle.recognizer = pages.any_of(self.I_BOSS_SKIP, pages.page_battle.recognizer)
        pages.page_battle_result = self.navigator.resolve_page(pages.page_battle_result)
        pages.page_battle_result.recognizer = pages.any_of(self.I_BOSS_BATTLE_AGAIN, self.I_BOSS_BATTLE_GIVEUP,
                                                           self.I_SELECT_3, self.I_SKILL_REFRESH, self.I_UI_CONFIRM_SAMLL,
                                                           pages.page_battle_result.recognizer)
        pages.page_reward = self.navigator.resolve_page(pages.page_reward)
        pages.page_reward.recognizer = pages.any_of(self.I_COIN, self.I_SR_DOUBLE_REWARD_USE, self.I_BOSS_GET_EXP,
                                                    self.I_BOSS_SHARE, self.I_BOSS_SHUTU, self.I_MS_SKILL_UNLOCK,
                                                    pages.page_reward.recognizer)

    def _handle_in_battle(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        if self.appear_then_click(self.I_BOSS_SKIP, interval=0.8):
            return BattleAction.CONTINUE
        return super()._handle_in_battle(context, config)

    def _handle_result(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        context.reward_no_battle_ts = None
        # 打输了, 直接放弃
        if self.appear(self.I_BOSS_BATTLE_GIVEUP):
            context.is_win = False
            self.click(self.I_BOSS_BATTLE_GIVEUP, interval=0.8)
            return BattleAction.CONTINUE
        # 放弃之后的2次弹窗确认
        if self.appear(self.I_UI_CONFIRM_SAMLL):
            self.click(self.I_UI_CONFIRM_SAMLL, interval=0.8)
            return BattleAction.CONTINUE
        # 选择一个技能
        if self.appear(self.I_SELECT_3, interval=1.5) and self.appear(self.I_SKILL_REFRESH):
            context.is_win = True
            self.coin_num = self.get_coin_num(self.O_COIN_NUM)
            select_btn = self.get_skill_select([self.I_SKILL101, self.I_SKILL105])
            if self.appear_then_click(select_btn, interval=1):
                if self.appear(self.I_SKILL101):
                    self.cnt_skill101 += 1
                    logger.info(f'Skill101 level: {self.cnt_skill101}')
        return BattleAction.CONTINUE

    def _handle_reward(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        context.reward_no_battle_ts = None
        if self.appear(self.I_BOSS_SHUTU):  # 极表示boss战赢了
            context.is_win = True
        if context.is_win and self.appear_then_click(self.I_SR_DOUBLE_REWARD_USE, interval=1.5):
            return BattleAction.CONTINUE
        if not context.is_win and self.appear_then_click(self.I_SR_DOUBLE_REWARD_CANCEL, interval=1.5):
            return BattleAction.CONTINUE
        if self.appear(self.I_COIN, interval=2):
            self.coin_num += self.get_coin_num(self.I_COIN)
            logger.info(f'Current coin: {self.coin_num}')
        self.click(pages.random_click(), interval=1.2)
        self.device.click_record_clear()
        return BattleAction.CONTINUE
