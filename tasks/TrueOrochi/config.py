# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from pydantic import BaseModel, Field
from enum import Enum

from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase, TimeDelta, dynamic_hide
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig

class GreenMarkType(str, Enum):
    LEFT_1 = 'left_1'
    LEFT_2 = 'left_2'
    LEFT_3 = 'left_3'
    LEFT_4 = 'left_4'
    LEFT_5 = 'left_5'
    LEFT_6 = 'left_6'
    MAIN = 'main'

class TrueOrochiScheduler(Scheduler):
    priority: int = Field(default=10, description='priority_help')
    success_interval: TimeDelta = Field(default=TimeDelta(days=3), description='success_interval_help')
    failure_interval: TimeDelta = Field(default=TimeDelta(days=1), description='failure_interval_help')

class TrueOrochiConfig(BaseModel):
    find_true_orochi: bool = Field(default=True, description='find_true_orochi_help')
    current_success: int = Field(default=0, description='current_success_help')

    hide_fields = dynamic_hide('current_success')

class TrueOrochiSwitchSoulConf(SwitchSoulConfig):
    enable_switch_layer_soul: bool = Field(default=False, description='enable_switch_layer_soul_help')

class TrueOrochi(ConfigBase):
    scheduler: TrueOrochiScheduler = Field(default_factory=TrueOrochiScheduler)
    true_orochi_config: TrueOrochiConfig = Field(default_factory=TrueOrochiConfig)
    switch_soul: TrueOrochiSwitchSoulConf = Field(default_factory=TrueOrochiSwitchSoulConf)
