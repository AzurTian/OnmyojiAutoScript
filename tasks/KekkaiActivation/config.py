# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from enum import Enum
from pydantic import BaseModel, Field
from tasks.Component.config_base import ConfigBase, TimeDelta
from tasks.Component.config_scheduler import Scheduler
from tasks.Utils.config_enum import ShikigamiClass


class CardType(str, Enum):
    FISH = '斗鱼'
    TAIKO = '太鼓'

class CardStar(str, Enum):
    SIX = '六星'
    FIVE = '五星'


class ActivationScheduler(Scheduler):
    priority: int = Field(default=2, description='priority_help')
    success_interval: TimeDelta = Field(default=TimeDelta(days=1), description='success_interval_help')
    failure_interval: TimeDelta = Field(default=TimeDelta(hours=10), description='failure_interval_help')


class ActivationConfig(BaseModel):
    card_type: CardType = Field(default=CardType.TAIKO, description='card_rule_help')
    card_star: CardStar = Field(default=CardStar.SIX, description='六星：六星及以下、五星：五星及以下')
    swipe_retry_limit: int = Field(default=3, description='最多滑动X次后触发未找到符合条件的卡')
    min_taiko_num: int = Field(default=8, description='挂卡太鼓每小时最少收益,低于则不挂卡')
    min_fish_num: int = Field(default=16, description='挂卡斗鱼每小时最少收益,低于则不挂卡')
    exchange_before: bool = Field(default=True, description='exchange_before_help')
    exchange_max: bool = Field(default=True, description='exchange_max_help')
    auto_fill: bool = Field(default=False, description='auto_fill_help')
    shikigami_class: ShikigamiClass = Field(default=ShikigamiClass.N, description='shikigami_class_help')
    card_not_found_count: int = Field(default=0, description='未发现卡次数')


class KekkaiActivation(ConfigBase):
    scheduler: ActivationScheduler = Field(default_factory=ActivationScheduler)
    activation_config: ActivationConfig = Field(default_factory=ActivationConfig)
