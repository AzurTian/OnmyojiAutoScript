# 实现：
# 切号选项：账号，区服
# 是否开启协站完成推送
# 使用方案 觉醒15次+结界突破3次
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime, time

from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig


class AssistBattleConfig(BaseModel):
    evozone_enable: bool = Field(
        default=False,
        description='启用觉醒副本，默认1层打满每日15次',
    )
    realmraid_enable: bool = Field(default=True, description='启用结界突破')
    realmraid_easy_enable: bool = Field(default=True, description='结界突破低勋优先')
    three_refresh: bool = Field(default=True, description='结界突破是否三次就刷新')
    switch_soul_enable: bool = Field(
        default=False, description='是否启用结界突破换御魂，直接套用个人突破内配置'
    )
    kekkaiutilize_enable: bool = Field(
        default=False, description='顺便蹭个结界卡，默认蹭卡规则default'
    )


class SwitchAccountConfig(BaseModel):
    account: str = Field(default='', description='账号')
    server: str = Field(default='', description='区服')


class AssistBattle(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    assist_battle_config: AssistBattleConfig = Field(default_factory=AssistBattleConfig)
