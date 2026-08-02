# This Python file uses the following encoding: utf-8

import time

from module.exception import GameStuckError, TaskEnd
from module.logger import logger
from tasks.Chess.assets import ChessAssets
from tasks.Chess.config import Chess
from tasks.Chess.runtime.economy import ChessEconomyMixin
from tasks.Chess.runtime.hand_operations import ChessHandOperationsMixin
from tasks.Chess.runtime.recognition import ChessRecognitionMixin
from tasks.Chess.runtime.round_state import ChessRoundStateMixin
from tasks.Chess.runtime.settings import ChessRuntimeSettings
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.GameUi.game_ui import GameUi
from tasks.Chess.page import page_chess, random_click


class ScriptTask(
    ChessRecognitionMixin,
    ChessHandOperationsMixin,
    ChessRoundStateMixin,
    ChessEconomyMixin,
    ChessRuntimeSettings,
    GameUi,
    GeneralBattle,
    ChessAssets,
):
    """百鬼棋局任务入口：仅负责任务、整局与回目编排。"""

    conf: Chess = None

    def run(self):
        """按执行次数循环百鬼棋局，并可在鼬乐币刷满时提前结束。"""
        chess_task_config = getattr(self.config, 'chess', None)
        chess_config = getattr(chess_task_config, 'chess_config', None)
        selected_lineup = getattr(
            chess_config,
            'lineup_bond',
            self.DEFAULT_LINEUP_KEY,
        )
        strategy = self.select_lineup_strategy(selected_lineup)

        # 启动恢复会主动退出遗留对局；正常循环只保留保段位退三局。
        self._recover_interrupted_chess_game()
        self.goto_page(page_chess)

        # Config 持有完整 ConfigModel，Chess 专属配置位于
        # self.config.chess.chess_config。旧配置未包含新字段时使用默认值，
        # 避免升级后任务在进入棋局大厅时直接崩溃。
        target_count = int(getattr(chess_config, 'run_count', 1))
        coin_full_exit = bool(
            getattr(chess_config, 'coin_full_exit', False)
        )
        rank_protection = bool(
            getattr(chess_config, 'rank_protection', False)
        )
        completed = 0
        rank_protection_exits_remaining = 0
        logger.info(
            'Chess task constraints: '
            f'lineup={strategy["key"]} ({strategy["display_name"]}), '
            f'run_count={target_count}, coin_full_exit={coin_full_exit}, '
            f'rank_protection={rank_protection}'
        )

        while (
            target_count == -1
            or completed < target_count
            or rank_protection_exits_remaining > 0
        ):
            self.screenshot()
            if coin_full_exit and self._coin_is_full():
                logger.info(
                    'Stop Chess task before next game: coin reached 600/600'
                )
                break

            logger.debug(
                'Chess game loop '
                f'{completed + 1}/'
                f'{"infinite" if target_count == -1 else target_count}'
            )
            self._rank_protection_exit_requested = bool(
                rank_protection and rank_protection_exits_remaining > 0
            )
            self._rank_protection_exit_succeeded = False
            game_rank = self.run_one_game()

            if (
                self._rank_protection_exit_requested
                and self._rank_protection_exit_succeeded
            ):
                rank_protection_exits_remaining -= 1
                logger.info(
                    'Chess rank-protection exit completed: '
                    f'remaining={rank_protection_exits_remaining}/3, '
                    f'completed_games={completed}'
                )
                continue

            completed += 1
            if rank_protection and game_rank is not None and game_rank <= 4:
                rank_protection_exits_remaining = 3
                logger.info(
                    'Chess rank protection activated: '
                    f'last_rank=第{game_rank}名, schedule 3 active exits'
                )
            else:
                rank_protection_exits_remaining = 0
                if rank_protection:
                    logger.info(
                        'Chess rank protection not activated: '
                        f'last_rank='
                        f'{"未知" if game_rank is None else f"第{game_rank}名"}, '
                        'requires 第1至第4名'
                    )
            logger.info(
                f'Chess completed games: {completed}/'
                f'{"infinite" if target_count == -1 else target_count}, '
                f'rank_protection_exits_pending='
                f'{rank_protection_exits_remaining}'
            )

            # _run_round_loop 正常返回时已经回到棋局大厅，此处刷新后检查
            # 本局获得的鼬乐币；勾选时次数和满币任一条件先满足即结束。
            if coin_full_exit:
                self.screenshot()
                if self._coin_is_full():
                    logger.info(
                        'Stop Chess task after game: coin reached 600/600'
                    )
                    break

        logger.info(
            f'Chess task loop finished: completed={completed}, '
            f'target={target_count}, coin_full_exit={coin_full_exit}, '
            f'rank_protection={rank_protection}'
        )
        self.set_next_run(task='Chess', success=True, finish=True)
        raise TaskEnd('Chess')

    def run_one_game(self) -> int | None:
        """运行一局，并以最后一次存活人数快照作为本局估算名次。"""
        self._start_chess_game()
        self._run_round_loop()
        snapshot = getattr(self, '_round_snapshot', None) or {}
        rank = snapshot.get('alive_players')
        if isinstance(rank, int) and 1 <= rank <= 8:
            logger.info(
                f'Chess game ended: 第{rank}名 '
                f'(last_alive_players={rank}, '
                f'round={snapshot.get("round")})'
            )
            return rank
        logger.warning(
            'Chess game ended: rank unavailable because the last '
            f'alive-player snapshot is invalid [{rank}]'
        )
        return None

    def run_one_round(self, round_no: int) -> int | None:
        """执行一个回目：回合开始 -> 备 -> 战/鬼/待 -> 等待新回合。"""
        logger.debug(f'Chess round {round_no}')
        self._read_round_resources(round_no)
        phase = 'await_preparation'
        preparation_done = False
        next_round_candidate = None
        next_round_confirmed = 0
        empty_frames = 0
        unknown_since = None
        battle_hand_cleanup_done = False

        while True:
            self.device.stuck_record_clear()
            if self._refresh_round_state_screenshot():
                empty_frames = 0
                time.sleep(self.ROUND_STATE_SCREENSHOT_INTERVAL)
                continue
            if self._finish_chess_game_if_visible():
                return None
            if getattr(self, '_rank_protection_exit_requested', False):
                logger.info(
                    'Chess rank protection: actively exit this game; '
                    'the game will not count toward completed runs'
                )
                if self.active_exit_chess_game():
                    self._rank_protection_exit_succeeded = True
                    return None
                logger.warning(
                    'Chess rank-protection exit was unavailable; '
                    'retry on the next state refresh'
                )
            observed_round = self._read_round_number()
            mode = self._read_chess_mode()

            if observed_round is None and mode is None:
                empty_frames += 1
                if empty_frames >= self.RESULT_EMPTY_CONFIRM_FRAMES:
                    if self._confirm_game_end_after_empty_state(
                        f'round_{round_no}'
                    ):
                        self._return_to_chess_lobby()
                        return None
                    empty_frames = 0
                    time.sleep(self.ROUND_STATE_SCREENSHOT_INTERVAL)
                    continue
            else:
                empty_frames = 0

            round_transition_pending = False
            if observed_round is not None and observed_round != round_no:
                if observed_round == next_round_candidate:
                    next_round_confirmed += 1
                else:
                    next_round_candidate = observed_round
                    next_round_confirmed = 1
                round_transition_pending = True
                if next_round_confirmed >= self.ROUND_CONFIRM_FRAMES:
                    logger.debug(
                        f'Chess round boundary confirmed: {round_no} -> '
                        f'{observed_round}, phase={phase}, '
                        f'preparation_done={preparation_done}'
                    )
                    return observed_round
            else:
                next_round_candidate = None
                next_round_confirmed = 0

            # 回目数字第一次变化时暂停所有旧回目动作，等待第二帧确认。
            if round_transition_pending:
                time.sleep(self.ROUND_STATE_SCREENSHOT_INTERVAL)
                continue

            in_game = mode is not None or self._is_in_chess_game()
            if in_game:
                unknown_since = None
            elif unknown_since is None:
                unknown_since = time.monotonic()
            elif time.monotonic() - unknown_since >= self.UNKNOWN_STATE_TIMEOUT:
                raise GameStuckError(
                    f'Chess: lost all markers during round {round_no}'
                )

            if mode in ('战', '鬼', '待'):
                if mode == '战':
                    self._run_battle_economy_until_budget_limit()
                    if not battle_hand_cleanup_done:
                        battle_hand_cleanup_done = (
                            self._handle_battle_sell_stage()
                        )
                    self._handle_passive_stage('战')
                else:
                    self._handle_passive_stage(mode)
                if phase == 'await_preparation':
                    preparation_done = True
                    phase = 'await_battle_end'
                    logger.warning(
                        f'Chess round {round_no}: resumed in passive mode '
                        f'{mode}; treat preparation as already passed'
                    )

            elif mode == '备':
                # Buff 面板是当前备阶段的高优先级中断事件。选完后不推进
                # phase/preparation_count；下一轮循环会把它当作新的同阶段备，
                # 从上式神、上御魂的起点重新执行。
                if self.appear(self.I_SELECT_BUFF):
                    logger.debug('Chess preparation interrupted by buff selection')
                    self.select_random_buff()
                    continue

                if phase == 'await_preparation':
                    # 回合开始先独立购买一次：开商店、扫商店、买目标。
                    # 15 秒保护只约束后面的升级/刷新循环，不影响这次买卡。
                    self.purchase_lineup_cards_once()
                    self._run_preparation_economy_until_time_limit()
                    if not self._is_preparation_mode():
                        time.sleep(self.ROUND_STATE_SCREENSHOT_INTERVAL)
                        continue
                    if self._handle_preparation_stage(1):
                        preparation_done = True
                        phase = 'await_battle'
                        logger.debug(
                            f'Chess round {round_no}: preparation '
                            'complete; wait for 战/鬼/待'
                        )

            interval = (
                self.HYAKKI_SCREENSHOT_INTERVAL
                if mode == '鬼'
                else self.ROUND_STATE_SCREENSHOT_INTERVAL
            )
            time.sleep(interval)

    def _run_round_loop(self) -> None:
        """运行单局回目循环；Chess 自行持续刷新通用卡死计时。"""
        self.device.stuck_record_clear()
        try:
            self._run_game_by_rounds_without_device_stuck_timeout()
        finally:
            self.device.stuck_record_clear()

    def _handle_preparation(self) -> bool:
        """统一备阶段：Buff 弹窗优先处理，随后上式神、上御魂。"""
        if self.appear(self.I_SELECT_BUFF):
            self.select_random_buff()
            return False
        if not self._is_preparation_mode():
            return False
        # deploy_shikigami_from_hand 内部负责确认商店关闭、人数上限和
        # 每次拖动后的重新定位，准备阶段不重复实现这些约束。
        self.deploy_shikigami_from_hand()
        if self._is_shop_open() or not self._is_preparation_mode():
            logger.warning(
                'Stop Chess preparation before soul phase: '
                'shop is open or mode left preparation'
            )
            return False
        # 上式神与上御魂保持为两个独立操作，由准备阶段明确编排顺序。
        verified_board_names = {
            name
            for name in getattr(self, '_board_lineup_names', set())
            if name in self.shikigami_deploy_positions
        }
        self.equip_souls_from_hand(verified_board_names)
        return self._is_preparation_mode()

    def _run_preparation_economy_until_time_limit(self) -> None:
        """备阶段升级/刷新循环：仅这部分受剩余时间限制。"""
        if not self._is_preparation_mode():
            return

        self._schedule_economy_cycle()
        while getattr(self, '_economy_pending', False):
            if not self._is_preparation_mode():
                return
            if self.appear(self.I_SELECT_BUFF):
                return
            # 只有升级/刷新循环受剩余时间限制；第二套布局没有 now_time
            # OCR，_read_remaining_time 会返回 None，因此不会误打断购买。
            remaining = self._read_remaining_time()
            if remaining is not None and remaining <= 15:
                logger.info(
                    'Stop Chess preparation upgrade/refresh loop: '
                    f'remaining_time={remaining} <= 15'
                )
                return
            result = self._run_economy_atomic_batch(battle_mode=False)
            if result in ('complete', 'blocked'):
                return
            self.screenshot()

    def _run_battle_economy_until_budget_limit(self) -> None:
        """战阶段续跑升级/刷新循环；同样受剩余时间 <= 15 保护。"""
        if self._read_chess_mode() != '战':
            return
        self._schedule_economy_cycle()
        while (
            self._read_chess_mode() == '战'
            and getattr(self, '_economy_pending', False)
        ):
            remaining = self._read_remaining_time()
            if remaining is not None and remaining <= 15:
                logger.info(
                    'Stop Chess battle upgrade/refresh loop: '
                    f'remaining_time={remaining} <= 15'
                )
                return
            result = self._run_economy_atomic_batch(battle_mode=True)
            if result in ('complete', 'blocked'):
                return
            self.screenshot()

    def _handle_preparation_stage(self, stage_index: int) -> bool:
        """执行一次完整备阶段；卖卡已移至独立的战阶段环节。"""
        logger.debug(f'Chess preparation stage {stage_index}/2')
        return self._handle_preparation() and self._is_preparation_mode()

    def _handle_battle_sell_stage(self) -> bool:
        """战阶段独立卖卡：持续清理杂卡和纹章，直到确认手牌干净。"""
        if self._read_chess_mode() != '战':
            return False
        logger.debug('Chess battle hand-card cleanup')
        sold = self.cleanup_non_lineup_hand_cards(allowed_modes=('战',))
        logger.debug(f'Chess battle hand-card cleanup complete: sold={sold}')
        return self._read_chess_mode() == '战'

    def _handle_passive_stage(self, mode: str) -> bool:
        """战、鬼、待阶段只等待，不主动改变商店状态。"""
        return mode in ('战', '鬼', '待')

    def _handle_battle_economy(self) -> str:
        """卖卡完成后，在战阶段续跑一个尚未完成的经济原子动作。"""
        if self._read_chess_mode() != '战':
            return 'blocked'
        if not getattr(self, '_economy_pending', False):
            return 'complete'
        logger.debug(
            'Chess battle economy continuation: '
            f'state={self._economy_step_state}'
        )
        return self._run_economy_atomic_batch(battle_mode=True)

    def _handle_round_end(self) -> bool:
        """在下一次可用的备阶段补做系统卡回收、上阵和御魂。"""
        if not getattr(self, '_formation_pending', False):
            return True
        if not self._is_preparation_mode():
            return False

        logger.debug('Chess pending system-card recall')
        if not self._ensure_shop_closed():
            return False
        if not self.recall_all_board_cards():
            return False
        time.sleep(self.BOARD_REDEPLOY_SETTLE_WAIT)
        self.screenshot()
        if not self._is_preparation_mode():
            return False
        # 回收之后先恢复阵容，再允许经济操作。
        logger.debug('Chess immediate redeploy after pending recall')
        if not self._handle_preparation():
            return False

        self._formation_pending = False
        logger.debug('Chess pending formation recovery completed')
        return True

    def _refresh_round_state_screenshot(self) -> bool:
        """刷新回目状态截图；选 Buff 出现时必须优先处理完毕。"""
        self.screenshot()
        if not self.appear(self.I_SELECT_BUFF):
            return False
        logger.info(
            'Chess round-state refresh interrupted by buff selection; '
            'resolve buff before reading round and mode'
        )
        self.select_random_buff()
        self.screenshot()
        return True

    def _confirm_game_end_after_empty_state(self, context: str) -> bool:
        """回目和模式连续为空后，用新截图中的阵容入口复核对局状态。"""
        if self._refresh_round_state_screenshot():
            logger.debug(
                'Chess empty-state result postponed after buff selection: '
                f'context={context}'
            )
            return False
        if self.appear(self.I_OPEN_LINEUP):
            logger.debug(
                'Chess empty-state result rejected: '
                f'I_OPEN_LINEUP is still visible, context={context}'
            )
            return False
        logger.info(
            'Chess game end confirmed after empty round/mode: '
            f'I_OPEN_LINEUP is absent, context={context}'
        )
        return True

    def _wait_for_round_start(self) -> int | None:
        """等待稳定回目数字；返回 None 表示本局已经结算。"""
        candidate = None
        confirmed = 0
        empty_frames = 0
        while True:
            self.device.stuck_record_clear()
            if self._refresh_round_state_screenshot():
                candidate = None
                confirmed = 0
                empty_frames = 0
                time.sleep(self.ROUND_STATE_SCREENSHOT_INTERVAL)
                continue
            if self._finish_chess_game_if_visible():
                return None

            round_no = self._read_round_number()
            mode = self._read_chess_mode()
            if round_no is not None:
                empty_frames = 0
                if round_no == candidate:
                    confirmed += 1
                else:
                    candidate = round_no
                    confirmed = 1
                if confirmed >= self.ROUND_CONFIRM_FRAMES:
                    return round_no
            else:
                candidate = None
                confirmed = 0
                if mode is None:
                    empty_frames += 1
                    if empty_frames >= self.RESULT_EMPTY_CONFIRM_FRAMES:
                        if self._confirm_game_end_after_empty_state(
                            'wait_for_round_start'
                        ):
                            self._return_to_chess_lobby()
                            return None
                        empty_frames = 0
                else:
                    empty_frames = 0
            time.sleep(self.ROUND_STATE_SCREENSHOT_INTERVAL)

    def _is_in_chess_game(self) -> bool:
        """阵容入口或商店任一出现，即认为仍处于棋局内。"""
        return self.appear(self.I_OPEN_LINEUP) or self.appear(self.I_MARKET)

    def _wait_until_in_chess_game(
        self,
        timeout: float,
        retry_start: bool = False,
    ) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.screenshot()
            if self._is_in_chess_game():
                return
            if retry_start and self.appear(self.I_CHESS_START):
                self.appear_then_click(self.I_CHESS_START, interval=2.0)
            time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
        raise GameStuckError('Chess: timeout waiting for in-game markers')

    def _start_chess_game(self) -> None:
        """从棋局大厅开战，确认进入局内后直接开始回合流程。"""
        logger.debug('Chess game start')
        # 御魂容量只在单局内记忆。新对局重新允许所有已上阵式神接受
        # 御魂，避免上一局的“已满”状态污染下一局。
        self._soul_full_positions = set()
        self._board_lineup_names = set()
        self._player_deployed_positions = set()
        self._round_snapshot = None
        self._reset_economy_state()
        strategy = self.get_lineup_strategy()
        logger.debug(
            'Reset Chess per-game state: '
            f'lineup={strategy["key"]} ({strategy["display_name"]})'
        )
        self._wait_until_in_chess_game(
            timeout=self.GAME_ENTER_TIMEOUT,
            retry_start=True,
        )
        logger.debug(
            'Chess entered game; skip lineup preset and start round loop'
        )

    def _recover_interrupted_chess_game(self) -> bool:
        """仅在任务启动时清理上次脚本中断后遗留的棋局。"""
        self.screenshot()

        # 已在大厅时无需恢复。
        if self.appear(self.I_CHECK_CHESS):
            return False

        # 上次可能已经进入结算、分享或排名阶段，直接继续既有返回流程。
        if (
            self.appear(self.I_EXIT_TO_CHESS)
            or self.appear(self.I_EXIT_TO_CHESS_2)
            or self.appear(self.I_SHARE)
            or self.appear(self.I_CHECK_RANK)
            or self.appear(self.I_RANK_GOTO_CHESS)
        ):
            logger.debug('Chess startup recovery: unfinished result flow detected')
            self._return_to_chess_lobby()
            return True

        mode = self._read_chess_mode()
        if mode is None and not self._is_in_chess_game():
            return False

        logger.warning(
            f'Chess startup recovery: interrupted in-game state detected, mode={mode}'
        )
        if not self.active_exit_chess_game():
            raise GameStuckError(
                'Chess: interrupted game detected but active exit was unavailable'
            )
        return True

    def _run_game_by_rounds_without_device_stuck_timeout(self) -> None:
        """单局协调器：逐个调用单回目函数，直至完成结算返回。"""
        round_no = self._wait_for_round_start()
        while round_no is not None:
            round_no = self.run_one_round(round_no)

    def _finish_chess_game_if_visible(self) -> bool:
        """发现任一结算入口时完成返回大厅流程。"""
        if not self._chess_result_flow_visible():
            return False
        self._return_to_chess_lobby()
        return True

    def active_exit_chess_game(self) -> bool:
        """Chess 专属主动退出；不扩展通用 GeneralBattle 接口。"""
        logger.debug('Chess active exit requested')
        deadline = time.monotonic() + self.RESULT_RETURN_TIMEOUT
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

            # 只有确实点击过确认按钮后，它的消失才代表主动退出成功。
            if dialog_seen and confirm_clicked and not confirm_visible:
                logger.debug('Chess active exit success')
                self._return_to_chess_lobby()
                return True

            now = time.monotonic()
            if dialog_seen:
                if confirm_visible and now >= next_confirm_click_at:
                    self.click(self.I_CHESS_EXIT_CONFIRM)
                    confirm_clicked = True
                    next_confirm_click_at = now + 2.0
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                continue

            if now >= next_exit_click_at:
                if self.appear(self.I_CHESS_EXIT):
                    self.click(self.I_CHESS_EXIT)
                next_exit_click_at = now + 2.0
            time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)

        logger.warning(
            'Chess active exit timed out: '
            f'dialog_seen={dialog_seen}, confirm_clicked={confirm_clicked}'
        )
        return False

    def _chess_result_flow_visible(self) -> bool:
        """检测任一已知结算/返回大厅标志。"""
        return (
            self.appear(self.I_CHECK_CHESS)
            or self.appear(self.I_EXIT_TO_CHESS)
            or self.appear(self.I_EXIT_TO_CHESS_2)
            or self.appear(self.I_SHARE)
            or self.appear(self.I_CHECK_RANK)
            or self.appear(self.I_RANK_GOTO_CHESS)
        )

    def _return_to_chess_lobby(self) -> None:
        """点击返回与分享页，并持续安全点击直到进入可识别页面。"""
        logger.debug('Chess game finished')
        deadline = time.monotonic() + self.RESULT_RETURN_TIMEOUT
        share_seen = False
        exit_clicked = False
        safe_clicks = 0
        rank_recovery_started = False
        fallback_exit_at = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            self.screenshot()

            if (
                rank_recovery_started
                and self.appear(self.I_CHECK_CHESS)
            ):
                logger.debug('Returned to Chess lobby from recovered rank page')
                return

            # 任务重启时可能已经停在排名界面，此时没有机会重新经历分享
            # 页面，保留恢复入口；正常结算只有在分享流程完成后才处理排名。
            rank_page = self.appear(self.I_CHECK_RANK)
            rank_button = self.appear(self.I_RANK_GOTO_CHESS)
            if (rank_page or rank_button) and not exit_clicked:
                logger.debug('Chess rank page detected, return to Chess lobby')
                rank_recovery_started = True
                if rank_button:
                    self.appear_then_click(self.I_RANK_GOTO_CHESS, interval=1.5)
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                continue

            if not exit_clicked:
                if self.appear(self.I_EXIT_TO_CHESS):
                    logger.debug(
                        'Chess return-to-lobby button detected, click it; '
                        'share page is now mandatory'
                    )
                    self.appear_then_click(self.I_EXIT_TO_CHESS, interval=1.5)
                    exit_clicked = True
                    time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                    continue
                if self.appear(self.I_EXIT_TO_CHESS_2):
                    logger.debug(
                        'Chess active-exit result detected; click it and '
                        'require share page next'
                    )
                    self.appear_then_click(
                        self.I_EXIT_TO_CHESS_2,
                        interval=1.5,
                    )
                    exit_clicked = True
                    time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                    continue
                if self.appear(self.I_SHARE):
                    # 脚本重启时可能已经点击过返回并停在分享页。
                    logger.debug(
                        'Chess return flow resumed from existing share page'
                    )
                    exit_clicked = True
                    share_seen = True
                    continue
                if time.monotonic() >= fallback_exit_at:
                    # 模板偶发未命中时，正常结算按钮位置是固定的。
                    logger.warning(
                        'Chess return button image was not detected; '
                        'click its fixed safe position and require share page'
                    )
                    self.click(self.I_EXIT_TO_CHESS)
                    exit_clicked = True
                    time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                    continue
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                continue

            if not share_seen and self.appear(self.I_SHARE):
                share_seen = True
                logger.debug(
                    'Chess share page detected after return-to-lobby click'
                )

            if not share_seen:
                # 即便大厅标志发生误命中，也必须先等到分享页，禁止提前
                # 返回上层循环并开始下一局。
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                continue

            if rank_page or rank_button:
                logger.debug(
                    'Chess rank page detected after share safe clicks'
                )
                rank_recovery_started = True
                if rank_button:
                    self.appear_then_click(
                        self.I_RANK_GOTO_CHESS,
                        interval=1.5,
                    )
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                continue

            if self.appear(self.I_CHECK_CHESS):
                logger.debug(
                    'Returned to Chess lobby after share flow: '
                    f'safe_clicks={safe_clicks}'
                )
                return

            # 分享页出现后不再限制点击次数。只要尚未进入棋局大厅或
            # 排名页，就继续点击左侧安全区域推动结算动画和弹窗。
            safe_click = random_click(
                ltrb=(True, False, False, False)
            )
            safe_clicks += 1
            logger.debug(
                'Chess share safe click: '
                f'{safe_clicks}, target={safe_click.name}'
            )
            self.click(safe_click)
            time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
        raise GameStuckError('Chess: failed to return to lobby after result')
