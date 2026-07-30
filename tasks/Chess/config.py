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
        title='刷新非前40%符咒',
        default=True,
        description=(
            '按当前品质符咒总数的实际收益排名，保留排名前40%的'
            '选项，只刷新其余仍有刷新次数的位置；同收益边界按'
            '固定图鉴顺序确定名次'
        ),
    )


class Chess(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    chess_config: ChessConfig = Field(default_factory=ChessConfig)
