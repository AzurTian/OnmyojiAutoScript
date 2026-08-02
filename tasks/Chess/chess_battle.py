from __future__ import annotations

"""百鬼棋局局内页面的全局恢复与退出流程。"""

import time

from module.exception import GameStuckError
from module.logger import logger
from tasks.Component.GeneralBattle.assets import GeneralBattleAssets


class ChessBattleNavigationMixin:
    """让所有继承 GameUi 的任务都能退出遗留的百鬼棋局。"""

    CHESS_EXIT_TIMEOUT = 60.0
    CHESS_EXIT_SCREENSHOT_INTERVAL = 0.35

    def chess_result_flow_visible(self) -> bool:
        """检测百鬼棋局大厅或任一结算页面。"""
        return (
            self.appear(self.I_CHECK_CHESS)
            or self.appear(self.I_CHESS_EXIT_TO_LOBBY)
            or self.appear(self.I_CHESS_EXIT_TO_LOBBY_2)
            or self.appear(self.I_CHESS_SHARE)
            or self.appear(self.I_CHECK_CHESS_RANK)
            or self.appear(self.I_CHESS_RANK_GOTO_LOBBY)
        )

    def return_to_chess_lobby(self) -> bool:
        """完成返回按钮、分享页与排名页流程，最终回到棋局大厅。"""
        logger.debug('Global Chess result flow: return to lobby')
        deadline = time.monotonic() + self.CHESS_EXIT_TIMEOUT
        share_seen = False
        exit_clicked = False
        safe_clicks = 0
        rank_recovery_started = False
        fallback_exit_at = time.monotonic() + 1.5

        while time.monotonic() < deadline:
            self.device.stuck_record_clear()
            self.screenshot()

            if rank_recovery_started and self.appear(self.I_CHECK_CHESS):
                logger.debug('Global Chess result flow: lobby reached from rank page')
                return True

            rank_page = self.appear(self.I_CHECK_CHESS_RANK)
            rank_button = self.appear(self.I_CHESS_RANK_GOTO_LOBBY)
            if (rank_page or rank_button) and not exit_clicked:
                rank_recovery_started = True
                if rank_button:
                    self.appear_then_click(
                        self.I_CHESS_RANK_GOTO_LOBBY,
                        interval=1.5,
                    )
                time.sleep(self.CHESS_EXIT_SCREENSHOT_INTERVAL)
                continue

            if not exit_clicked:
                if self.appear(self.I_CHESS_EXIT_TO_LOBBY):
                    self.appear_then_click(
                        self.I_CHESS_EXIT_TO_LOBBY,
                        interval=1.5,
                    )
                    exit_clicked = True
                    time.sleep(self.CHESS_EXIT_SCREENSHOT_INTERVAL)
                    continue
                if self.appear(self.I_CHESS_EXIT_TO_LOBBY_2):
                    self.appear_then_click(
                        self.I_CHESS_EXIT_TO_LOBBY_2,
                        interval=1.5,
                    )
                    exit_clicked = True
                    time.sleep(self.CHESS_EXIT_SCREENSHOT_INTERVAL)
                    continue
                if self.appear(self.I_CHESS_SHARE):
                    exit_clicked = True
                    share_seen = True
                    continue
                if time.monotonic() >= fallback_exit_at:
                    logger.warning(
                        'Global Chess result flow: return image missed; '
                        'click fixed return area'
                    )
                    self.click(self.I_CHESS_EXIT_TO_LOBBY)
                    exit_clicked = True
                    time.sleep(self.CHESS_EXIT_SCREENSHOT_INTERVAL)
                    continue
                time.sleep(self.CHESS_EXIT_SCREENSHOT_INTERVAL)
                continue

            if not share_seen and self.appear(self.I_CHESS_SHARE):
                share_seen = True

            if not share_seen:
                time.sleep(self.CHESS_EXIT_SCREENSHOT_INTERVAL)
                continue

            if rank_page or rank_button:
                rank_recovery_started = True
                if rank_button:
                    self.appear_then_click(
                        self.I_CHESS_RANK_GOTO_LOBBY,
                        interval=1.5,
                    )
                time.sleep(self.CHESS_EXIT_SCREENSHOT_INTERVAL)
                continue

            if self.appear(self.I_CHECK_CHESS):
                logger.debug(
                    'Global Chess result flow: lobby reached after share, '
                    f'safe_clicks={safe_clicks}'
                )
                return True

            safe_clicks += 1
            self.click(GeneralBattleAssets.C_RANDOM_LEFT)
            time.sleep(self.CHESS_EXIT_SCREENSHOT_INTERVAL)

        raise GameStuckError('Global Chess: failed to return to lobby after result')

    def exit_chess_battle(self) -> bool:
        """主动退出当前百鬼棋局并完成返回大厅流程。"""
        logger.warning('Global Chess page handler: exit interrupted battle')
        deadline = time.monotonic() + self.CHESS_EXIT_TIMEOUT
        next_exit_click_at = 0.0
        next_confirm_click_at = 0.0
        dialog_seen = False
        confirm_clicked = False

        while time.monotonic() < deadline:
            self.device.stuck_record_clear()
            self.screenshot()

            confirm_visible = self.appear(self.I_CHESS_EXIT_CONFIRM)
            cancel_visible = self.appear(self.I_CHESS_EXIT_CANCEL)
            if confirm_visible or cancel_visible:
                dialog_seen = True

            if dialog_seen and confirm_clicked and not confirm_visible:
                logger.debug('Global Chess page handler: exit confirmed')
                return self.return_to_chess_lobby()

            now = time.monotonic()
            if dialog_seen:
                if confirm_visible and now >= next_confirm_click_at:
                    self.click(self.I_CHESS_EXIT_CONFIRM)
                    confirm_clicked = True
                    next_confirm_click_at = now + 2.0
                time.sleep(self.CHESS_EXIT_SCREENSHOT_INTERVAL)
                continue

            if now >= next_exit_click_at:
                if self.appear(self.I_CHESS_EXIT):
                    self.click(self.I_CHESS_EXIT)
                next_exit_click_at = now + 2.0
            time.sleep(self.CHESS_EXIT_SCREENSHOT_INTERVAL)

        logger.warning(
            'Global Chess page handler timed out: '
            f'dialog_seen={dialog_seen}, confirm_clicked={confirm_clicked}'
        )
        return False


def handle_chess_battle_page(task) -> bool:
    """GameUi 页面边动作：退出棋局战斗并返回棋局大厅。"""
    return task.exit_chess_battle()
