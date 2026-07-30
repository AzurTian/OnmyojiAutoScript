# This Python file uses the following encoding: utf-8

from pydantic import Field

from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler
from tasks.Chess.strategy.lineup import LineupBond


class ChessConfig(ConfigBase):
    """百鬼棋局循环与结束条件。"""

    lineup_bond: LineupBond = Field(
        title='选择阵容羁绊',
        default=LineupBond.QIJIAOSHAN,
        description='选择百鬼棋局使用的阵容羁绊与对应运营策略',
    )

    rank_protection: bool = Field(
        title='保段位',
        default=False,
        description='开启后每完成前四名一局主动退出三局；退出局不计入执行次数',
    )

    run_count: int = Field(
        title='执行次数',
        default=1,
        ge=-1,
        description='完成目标局数后结束；设置为-1时一直执行',
    )
    coin_full_exit: bool = Field(
        title='刷满鼬乐币',
        default=False,
        description='勾选后检测到鼬乐币已满时立即结束百鬼棋局',
    )
    continue_grigri_refresh_below_nine: bool = Field(
        title='符咒低于9分继续刷新',
        default=True,
        description=(
            '开启后，在没有9分或10分选项时继续刷新低于6分且尚有'
            '次数的位置；6分及以上选项保留'
        ),
    )


class Chess(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    chess_config: ChessConfig = Field(default_factory=ChessConfig)
