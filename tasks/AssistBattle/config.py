# 实现：
# 是否开启协战完成推送
# 使用方案 觉醒15次+结界突破3次
from typing import Any, Dict

from pydantic import BaseModel, Field, ValidationError, model_serializer, model_validator

from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase
from tasks.Component.SwitchAccount.switch_account_config import AccountInfo


class AssistBattleConfig(BaseModel):
    account_count: int = Field(default=1, ge=1, description='协战账号数量')
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


class AssistBattle(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    assist_battle_config: AssistBattleConfig = Field(default_factory=AssistBattleConfig)
    account_list: list[AccountInfo] = None

    @model_validator(mode='before')
    @classmethod
    def validator_account_list(cls, value: dict) -> Any:
        account_count = value.get('assist_battle_config', {}).get('account_count', 1)
        account_list = value.setdefault('account_list', [])

        remove_keys = []
        for key, item_value in value.items():
            if key == 'account_list' or 'account_list' not in key:
                continue
            try:
                account = AccountInfo(**item_value)
                if account.is_valid():
                    account_list.append(account)
                remove_keys.append(key)
            except (TypeError, ValidationError):
                continue

        for key in remove_keys:
            del value[key]

        if len(account_list) < account_count:
            account_list.extend(AccountInfo() for _ in range(account_count - len(account_list)))
        return value

    @model_serializer()
    def serializer_model(self) -> Dict[str, Any]:
        data = {}
        for key, value in self.__dict__.items():
            if isinstance(value, list):
                for index, item in enumerate(value):
                    data[f'{key}_{index + 1}'] = item.model_dump()
            else:
                data[key] = value.model_dump() if isinstance(value, BaseModel) else value
        return data
