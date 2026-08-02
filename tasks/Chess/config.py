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

    remaining_players: int = Field(
        title='剩余人数',
        default=1,
        ge=1,
        le=8,
        description='存活人数小于或等于该数值时主动退出；1表示不提前退出',
    )
    rank_protection: bool = Field(
        title='保段位',
        default=False,
        description='开启后每完成一局主动退出三局；退出局不计入执行次数',
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
