# 实现：
# 是否开启协战完成推送
# 使用方案 觉醒15次+结界突破3次
from typing import Any, Dict

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    model_serializer,
    model_validator,
)

from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase
from tasks.Component.SwitchAccount.switch_account_config import AccountInfo


class AssistBattleConfig(BaseModel):
    account_count: int = Field(
        default=1,
        ge=1,
        description='account_list_description',
    )
    evozone_enable: bool = Field(
        default=False,
        description='默认5层打满每日15次',
    )
    realmraid_enable: bool = Field(default=True, description='默认开启')
    realmraid_easy_enable: bool = Field(
        default=True, description='稳定优先，关闭则是从高到低'
    )
    three_refresh: bool = Field(default=True, description='是否进攻三次就刷新')
    switch_soul_enable: bool = Field(
        default=False, description='直接套用个人突破内配置，请确保其正确配置'
    )
    result_push_enable: bool = Field(
        default=False, description='请自行去脚本设置中配置并启用'
    )
    kekkaiutilize_enable: bool = Field(
        default=False, description='顺便蹭个结界卡，默认蹭卡规则default(暂未实装)'
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
            account_list.extend(
                AccountInfo() for _ in range(account_count - len(account_list))
            )
        return value

    @model_serializer()
    def serializer_model(self) -> Dict[str, Any]:
        data = {}
        for key, value in self.__dict__.items():
            if isinstance(value, list):
                for index, item in enumerate(value):
                    data[f'{key}_{index + 1}'] = item.model_dump()
            else:
                data[key] = (
                    value.model_dump() if isinstance(value, BaseModel) else value
                )
        return data

    # 隐藏用不到的last_complete_time字段
    @model_serializer()
    def serializer_model(self) -> Dict[str, Any]:
        data = {}

        for key, value in self.__dict__.items():
            if isinstance(value, list):
                for index, item in enumerate(value):
                    item_data = item.model_dump()

                    if isinstance(item, AccountInfo):
                        item_data["last_complete_time"] = 0xABCDEF

                    data[f'{key}_{index + 1}'] = item_data
            else:
                data[key] = (
                    value.model_dump() if isinstance(value, BaseModel) else value
                )

        return data
