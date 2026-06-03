# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from cached_property import cached_property
from dataclasses import dataclass
from enum import Enum
from module.atom.image import RuleImage

from pydantic import BaseModel, Field

from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig
from tasks.Component.config_base import ConfigBase, Time
from tasks.Component.config_scheduler import Scheduler
from typing import List


class WQType(str, Enum):
    """悬赏类型"""
    CHALLENGE = '挑战'
    EXPLORE = '探索'
    SECRET = '秘闻'
    YOKAI = '妖气'

    def __repr__(self):
        return self.value

    @staticmethod
    def contains(type_str: str):
        try:
            WQType(type_str)
            return True
        except ValueError:
            return False


@dataclass(frozen=True)
class WQInfo:
    """悬赏信息"""
    type: WQType    # 悬赏类型
    dest: str       # 目的地(探索第十章/秘闻第七层/...)
    number: int     # 怪物数量
    goto_btn: RuleImage # 前往按钮
    do_num: int     # 执行次数(探索一章节4个怪,需要打12个怪,则执行3次)


class CooperationType(int, Enum):
    """
        用于区分悬赏封印协作类型
    """
    Gold = 1  # 金币协作
    Jade = 2  # 勾玉协作
    Food = 4  # 狗/猫粮协作
    Sushi = 8  # 体力协作

    def __hash__(self):
        return self.value

    def __str__(self):
        return str(self.value)


class CooperationSelectMask(int, Enum):
    """
        掩码,对协作任务进行筛选
    """
    NoInvite = 0  # 不自动邀请
    GoldOnly = 1  # 仅 金币 协作进行邀请
    JadeOnly = 2  # 仅 勾玉 协作进行邀请
    GoldAndJade = 3
    FoodOnly = 4  # 仅 狗/猫粮 协作进行邀请
    GoldAndFood = 5
    JadeAndFood = 6
    GoldAndJadeAndFood = 7
    SushiOnly = 8  # 仅 体力 协作进行邀请
    GoldAndSushi = 9
    JadeAndSushi = 10
    GoldAndJadeAndSushi = 11
    FoodAndSushi = 12
    GoldAndFoodAndSushi = 13
    JadeAndFoodAndSushi = 14
    Any = 15  # 所有协作任务都邀请


class CooperationSelectMaskDescription(str, Enum):
    NoInvite = 'NoInvite'
    GoldOnly = 'GoldOnly'
    JadeOnly = 'JadeOnly'
    GoldAndJade = 'GoldAndJade'
    FoodOnly = 'FoodOnly'
    GoldAndFood = 'GoldAndFood'
    JadeAndFood = 'JadeAndFood'
    GoldAndJadeAndFood = 'GoldAndJadeAndFood'
    SushiOnly = 'SushiOnly'
    GoldAndSushi = 'GoldAndSushi'
    JadeAndSushi = 'JadeAndSushi'
    GoldAndJadeAndSushi = 'GoldAndJadeAndSushi'
    FoodAndSushi = 'FoodAndSushi'
    GoldAndFoodAndSushi = 'GoldAndFoodAndSushi'
    JadeAndFoodAndSushi = 'JadeAndFoodAndSushi'
    Any = 'Any'


class WantedQuestsConfig(BaseModel):
    before_end: Time = Field(default=Time(0, 0, 0), description='before_end_help')
    invite_friend_name: str = Field(default=str(""), description="invite_friend_name_help")
    cooperation_type: CooperationSelectMaskDescription = Field(default=CooperationSelectMaskDescription.Any,
                                                               description="cooperation_type_help")
    # 找怪优先级  挑战 > 秘闻 > 探索
    battle_priority: str = Field(default='挑战 > 秘闻 > 探索', description='battle_priority_help')
    # 只完成协作任务
    cooperation_only: bool = Field(default=False, description="cooperation_only_help")
    # 忽略任务的任务目标名称（“酒吞童子”等）,多个用逗号“，,"分隔
    unwanted_boss_names: str = Field(default='酒吞童子,阎魔', description='unwanted_boss_name_help')

    @cached_property
    def _wq_type_ordered_list(self) -> List[WQType]:
        from module.logger import logger
        wq_type_ordered_txt = self.battle_priority.replace(' ', '').replace('\n', '')
        if wq_type_ordered_txt == '':
            return [WQType.CHALLENGE, WQType.SECRET, WQType.EXPLORE]
        wq_type_list = []
        for wq_type_txt in wq_type_ordered_txt.split('>'):
            wq_type_txt = wq_type_txt.strip()
            if not WQType.contains(wq_type_txt):
                logger.warning(f'Read unsupported wq type: {wq_type_txt}, skip')
                continue
            wq_type_list.append(WQType(wq_type_txt))
        return wq_type_list


class WantedQuests(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    wanted_quests_config: WantedQuestsConfig = Field(default_factory=WantedQuestsConfig)
    switch_soul_config: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
