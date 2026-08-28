# This Python file uses the following encoding: utf-8
from enum import Enum

from pydantic import BaseModel, Field


class QuickLoadoutMode(str, Enum):
    NUMBER = 'mode_number'
    OCR = 'mode_ocr'


class QuickLoadoutConfig(BaseModel):
    """战斗界面内的一键配置。"""

    # 是否启用战斗前一键配置
    enable: bool = Field(default=False)
    # 预设选择模式：mode_number按编号选择，mode_ocr按名称识别
    mode: QuickLoadoutMode = Field(default=QuickLoadoutMode.NUMBER)
    # 一键配置左侧预设组编号
    group_number: int = Field(default=1, ge=1, le=7)
    # 所选预设组中的预设编号
    preset_number: int = Field(default=1, ge=1)
    # OCR模式使用的预设组名称
    group_name: str = Field(default='')
    # OCR模式使用的预设名称
    preset_name: str = Field(default='')

    def validate_target(self) -> None:
        if self.mode != QuickLoadoutMode.OCR:
            return
        if not self.group_name.strip():
            raise ValueError('Quick loadout group name cannot be empty in OCR mode')
        if not self.preset_name.strip():
            raise ValueError('Quick loadout preset name cannot be empty in OCR mode')


class NamedQuickLoadoutConfig(QuickLoadoutConfig):
    """支持按任务关卡名称选择不同预设的一键配置。"""

    # 是否按任务提供的关卡名称OCR选择不同预设
    custom_preset_enable: bool = Field(
        default=False,
        description='quick_loadout_custom_preset_enable_help',
    )
    # 格式：关卡名:(预设组,预设); ALL匹配未特别指定的关卡
    custom_preset: str = Field(
        default='ALL:(1,1);',
        description='quick_loadout_custom_preset_help',
    )
