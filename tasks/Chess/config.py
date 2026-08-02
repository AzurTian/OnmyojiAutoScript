# This Python file uses the following encoding: utf-8

from pydantic import Field

from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler
from tasks.Chess.lineup import LineupBond


class ChessConfig(ConfigBase):
    """百鬼棋局循环与结束条件。"""

    lineup_bond: LineupBond = Field(
        title='选择阵容羁绊',
        default=LineupBond.QIJIAOSHAN,
        description='选择百鬼棋局使用的阵容羁绊与对应运营策略',
    )

    early_exit: bool = Field(
        title='是否提前退出',
        default=False,
        description='勾选后在存活人数达到下方阈值时主动退出当前对局',
    )
    remaining_players: int = Field(
        title='剩余人数',
        default=0,
        ge=0,
        le=8,
        description='存活人数小于或等于该数值时主动退出，范围0至8；0表示不退出',
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
        description='勾选后检测到鼬乐币为600/600时立即结束百鬼棋局',
    )


class Chess(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    chess_config: ChessConfig = Field(default_factory=ChessConfig)
