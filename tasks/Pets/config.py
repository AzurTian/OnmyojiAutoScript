# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from datetime import timedelta
from pydantic import BaseModel, Field

from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase

class PetsConfig(ConfigBase):
    # 快速喂养
    pets_feast: bool = Field(default=True)
    enable_orochi_ten_once: bool = Field(default=False)
    enable_switch_layer_soul: bool = Field(default=False, description='enable_switch_layer_soul_help')

class Pets(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    pets_config: PetsConfig = Field(default_factory=PetsConfig)


