from module.atom.image import RuleImage
from module.logger import logger
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.GeneralBattle.general_battle import GeneralBattle, BattleContext, BattleAction
from tasks.SixRealms.common import SixRealmsCommon
import tasks.SixRealms.peacock_kingdom.page as pages
from typing import List, Optional


class BasePeacockKingdom(GeneralBattle, SixRealmsCommon):
    coin_num: int = 0
    skill_roaring_thunder: int = 0

    def get_pk_skill_select(self, skill_rule_list: List[RuleImage]) -> Optional[RuleImage]:
        """
        获取孔雀国技能对应的选择按钮
        :param skill_rule_list: 技能列表
        :return: 技能对应的选择按钮(没识别到技能返回None)
        """
        if not skill_rule_list:
            return None
        for skill_rule in skill_rule_list:
            if not self.appear(skill_rule):
                continue
            logger.info(f'Recognize skill: {skill_rule.name}')
            x, y = skill_rule.front_center()
            if 240 < x < 340:
                return self.I_PK_SELECT_0
            if 590 <= x < 690:
                return self.I_PK_SELECT_1
            if 950 <= x < 1050:
                return self.I_PK_SELECT_2
            if 420 <= x < 520:
                return self.I_PK_SELECT_3
            if 775 <= x < 875:
                return self.I_PK_SELECT_4
            break
        return None

    def before_run(self):
        self.coin_num = 0
        self.skill_roaring_thunder = 0
        pages.page_battle = self.navigator.resolve_page(pages.page_battle)
        pages.page_battle.recognizer = pages.any_of(self.I_BOSS_SKIP, pages.page_battle.recognizer)
        pages.page_battle_result = self.navigator.resolve_page(pages.page_battle_result)
        pages.page_battle_result.recognizer = pages.any_of(self.I_BOSS_BATTLE_AGAIN, self.I_BOSS_BATTLE_GIVEUP,
                                                           self.I_PK_SELECT_0, self.I_PK_SELECT_3,
                                                           self.I_PK_SKILL_REFRESH, self.I_UI_CONFIRM_SAMLL,
                                                           pages.page_battle_result.recognizer)
        pages.page_reward = self.navigator.resolve_page(pages.page_reward)
        pages.page_reward.recognizer = pages.any_of(self.I_COIN, self.I_SR_DOUBLE_REWARD_USE, self.I_BOSS_GET_EXP,
                                                    self.I_KP_BOSS_SHARE, self.I_BOSS_SHUTU, self.I_MS_SKILL_UNLOCK,
                                                    pages.page_reward.recognizer)

    def _handle_in_battle(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        if self.appear(self.I_PK_BATTLE_THUNDER):
            self.skill_roaring_thunder = 1  # 战斗中出现了六道轰雷, 标记已获取
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
        # 力量或魅力强化
        if self.appear(self.I_PK_SELECT_0, interval=1.5) or self.appear(self.I_PK_SELECT_3, interval=1.5):
            context.is_win = True
            select_btn = self.get_pk_skill_select([self.I_PK_SKILL_POWER, self.I_PK_SKILL_CHARM])
            if select_btn:
                self.appear_then_click(select_btn, interval=1)
            return BattleAction.CONTINUE
        # 选择技能
        if self.appear(self.I_SELECT_3, interval=1.5) and self.appear(self.I_PK_SKILL_REFRESH):
            context.is_win = True
            self.coin_num = self.get_coin_num(self.O_COIN_NUM)
            skill_rules = [self.I_PK_SKILL_ROARING_THUNDER] if self.skill_roaring_thunder == 0 else []
            select_btn = self.get_skill_select(skill_rules)
            if self.appear_then_click(select_btn, interval=1):
                if select_btn != self.I_SELECT_3:
                    self.skill_roaring_thunder = 1
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