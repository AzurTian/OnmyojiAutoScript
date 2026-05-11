# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from datetime import timedelta, time

from enum import Enum

from pydantic import BaseModel, Field, field_validator

from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase, Time
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig


class SixRealmsType(str, Enum):
    MOON_SEA = 'MoonSea'
    PEACOCK_KINGDOM = 'PeacockKingdom'


class SixRealmsGate(BaseModel):
    # 限制时间
    limit_time: Time = Field(default=Time(minute=30), description='limit_time_help')
    # 限制次数
    limit_count: int = Field(default=1, description='limit_count_help')
    six_realms_type: SixRealmsType = Field(default=SixRealmsType.MOON_SEA, description='six_realms_type_help')

    @property
    def limit_time_v(self) -> timedelta:
        if isinstance(self.limit_time, time):
            return timedelta(hours=self.limit_time.hour, minutes=self.limit_time.minute, seconds=self.limit_time.second)
        return self.limit_time


class SixRealms(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    six_realms_gate: SixRealmsGate = Field(default_factory=SixRealmsGate)
    switch_soul_config_1: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
    switch_soul_config_2: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)

