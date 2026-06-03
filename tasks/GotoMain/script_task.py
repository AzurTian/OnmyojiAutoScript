# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from datetime import datetime

from module.exception import (
    GameNotRunningError,
    GamePageUnknownError,
    GameStuckError,
    GameTooManyClickError,
    TaskEnd,
)
from module.logger import logger
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main
from tasks.Restart.server_update import (
    delay_pending_tasks_for_server_update,
    is_server_update_window,
)


class ScriptTask(GameUi):

    def run(self) -> None:
        self.device.stuck_record_clear()
        try:
            self.goto_page(page_main)
        except (GamePageUnknownError, GameStuckError, GameTooManyClickError, GameNotRunningError) as e:
            # 异常兑换：若处于停服窗口期，把"游戏页面异常 / 卡死 / 未运行"统一延后而不是抛回 Scheduler 触发 Restart
            if is_server_update_window() and self._delay_for_server_update(
                reason=f'{type(e).__name__} during goto_main inside server update window'
            ):
                raise TaskEnd('Goto main aborted due to server update window')
            raise e

        raise TaskEnd

    def _delay_for_server_update(self, reason: str) -> bool:
        delay_target = delay_pending_tasks_for_server_update(self.config, reason=reason)
        outcome = {
            'task': 'GotoMain',
            'status': 'server_update_delayed',
            'wait_until': delay_target,
        }
        self.config.task_runtime_outcome = outcome
        return True
