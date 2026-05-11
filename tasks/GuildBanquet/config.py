# This Python file uses the following encoding: utf-8
# @author ohspecial
# github https://github.com/ohspecial
from enum import Enum  

from pydantic import Field, BaseModel, SerializationInfo, field_serializer

from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase, Time, dynamic_hide


class Weekday(str, Enum):
    Monday = "星期一"
    Tuesday = "星期二"
    Wednesday = "星期三"
    Thursday = "星期四"
    Friday = "星期五"
    Saturday = "星期六"
    Sunday = "星期日"

    def to_index(self):
        return list(Weekday).index(self)


class GuildBanquetConfig(BaseModel):
    auto_switch_shikigami: bool = Field(default=False, description='guild_auto_switch_shikigami_help')
    # 自定义运行时间
    day_1: Weekday = Field(default=Weekday.Wednesday, description="每周第1次运行星期设置，第一次星期要比第二次星期早")
    run_time_1: Time = Field(default=Time(hour=20, minute=0, second=0),
                             description='若当前时间没有开启宴会, 则会在1小时之内按照调度器失败间隔不断重试')
    day_2: Weekday = Field(default=Weekday.Saturday, description="每周第2次星期设置")
    run_time_2: Time = Field(default=Time(hour=20, minute=0, second=0),  description="规则同上")


class GuildBanquet(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    guild_banquet_config: GuildBanquetConfig = Field(default_factory=GuildBanquetConfig)

