# This Python file uses the following encoding: utf-8

import time
from datetime import datetime, timedelta

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
from tasks.GameUi.page import page_chess


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

    def _wait_chess_action_state(self, condition) -> bool:
        """在单次动作后限时轮询目标图标状态。"""
        deadline = time.monotonic() + self.ACTION_ICON_WAIT_TIMEOUT
        while time.monotonic() < deadline:
            self.device.stuck_record_clear()
            self.screenshot()
            if condition():
                return True
            time.sleep(self.FAST_OPERATION_INTERVAL)
        self.device.stuck_record_clear()
        self.screenshot()
        return bool(condition())

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
        configured_limit_time = getattr(chess_config, 'limit_time', None)
        if configured_limit_time is None:
            self.limit_time = timedelta(minutes=30)
        else:
            self.limit_time = timedelta(
                hours=configured_limit_time.hour,
                minutes=configured_limit_time.minute,
                seconds=configured_limit_time.second,
            )
        coin_full_exit = bool(
            getattr(chess_config, 'coin_full_exit', False)
        )
        rank_protection = bool(
            getattr(chess_config, 'rank_protection', False)
        )
        self._matchmaking_timeout_seconds = max(
            10,
            int(getattr(chess_config, 'matchmaking_timeout_seconds', 60)),
        )
        self._consecutive_matchmaking_timeouts = 0
        completed = 0
        rank_protection_exits_remaining = 0
        logger.info(
            'Chess task constraints: '
            f'lineup={strategy["key"]} ({strategy["display_name"]}), '
            f'run_count={target_count}, limit_time={self.limit_time}, '
            f'coin_full_exit={coin_full_exit}, '
            f'rank_protection={rank_protection}, '
            f'matchmaking_timeout={self._matchmaking_timeout_seconds}s'
        )

        while (
            target_count == -1
            or completed < target_count
            or rank_protection_exits_remaining > 0
        ):
            if datetime.now() - self.start_time >= self.limit_time:
                logger.info(
                    'Chess task time reached; stop before starting next game'
                )
                break
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
        """运行一局，并返回结算页 OCR 得到的实际名次。"""
        self._start_chess_game()
        self._run_round_loop()
        rank = getattr(self, '_last_game_rank', None)
        if isinstance(rank, int) and 1 <= rank <= 8:
            logger.info(f'Chess game ended: 第{rank}名')
            return rank
        logger.warning(
            f'Chess game ended: result-page rank OCR unavailable [{rank}]'
        )
        return None

    def run_one_round(self, round_no: int) -> int | None:
        """执行一个回目：回合开始 -> 备 -> 战/鬼/待 -> 等待新回合。"""
        self._current_round_no = int(round_no)
        logger.debug(f'Chess round {round_no}')
        phase = 'await_preparation'
        preparation_done = False
        next_round_candidate = None
        next_round_confirmed = 0
        unknown_since = None
        battle_economy_done = False
        battle_hand_cleanup_done = False

        while True:
            self.device.stuck_record_clear()
            if self._refresh_round_state_screenshot():
                time.sleep(self.SLOW_POLL_INTERVAL)
                continue
            if self._finish_chess_game_after_markers_missing(
                f'round_{round_no}'
            ):
                return None
            if getattr(self, '_rank_protection_exit_requested', False):
                logger.info(
                    'Chess rank protection: actively exit this game; '
                    'the game will not count toward completed runs'
                )
                if self.exit_chess_battle():
                    self._rank_protection_exit_succeeded = True
                    return None
                logger.warning(
                    'Chess rank-protection exit was unavailable; '
                    'retry on the next state refresh'
                )
            observed_round = self._read_round_number()
            mode = self._read_chess_mode()

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
                time.sleep(self.SLOW_POLL_INTERVAL)
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
                    if not battle_hand_cleanup_done:
                        battle_hand_cleanup_done = (
                            self._handle_battle_sell_stage()
                        )
                    # 战阶段必须先完成非体系卡清理，再进入刷新升级。
                    # 若卖卡过程中阶段发生变化，本回目不再启动经济循环。
                    if (
                        battle_hand_cleanup_done
                        and not battle_economy_done
                        and self._read_chess_mode() == '战'
                    ):
                        self._run_battle_economy_until_budget_limit()
                        battle_economy_done = True
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
                # 符咒面板是当前备阶段的高优先级中断事件。选完后不推进
                # phase/preparation_count；下一轮循环会把它当作新的同阶段备，
                # 从上式神、上御魂的起点重新执行。
                if self.appear(self.I_SELECT_GRIGRI):
                    logger.debug('Chess preparation interrupted by grigri selection')
                    self.select_grigri()
                    continue

                if phase == 'await_preparation':
                    # 回合开始先独立购买一次：开商店、扫商店、买目标。
                    # 15 秒保护只约束后面的升级/刷新循环，不影响这次买卡。
                    self.purchase_lineup_cards_once()
                    self._run_preparation_economy_until_time_limit()
                    if not self._is_preparation_mode():
                        time.sleep(self.SLOW_POLL_INTERVAL)
                        continue
                    if self._handle_preparation_stage(1):
                        preparation_done = True
                        phase = 'await_battle'
                        logger.debug(
                            f'Chess round {round_no}: preparation '
                            'complete; wait for 战/鬼/待'
                        )

            interval = (
                3 * self.SLOW_POLL_INTERVAL
                if mode == '鬼'
                else self.SLOW_POLL_INTERVAL
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
        """统一备阶段：符咒弹窗优先处理，随后上式神、上御魂。"""
        if self.appear(self.I_SELECT_GRIGRI):
            self.select_grigri()
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
            if self.appear(self.I_SELECT_GRIGRI):
                return
            # 只有升级/刷新循环受剩余时间限制；第二套布局从第一套阶段
            # 框读取倒计时，第一套布局使用独立 now_time 区域。
            remaining = self._read_remaining_time()
            if remaining is not None and remaining < 15:
                logger.info(
                    'Stop Chess preparation upgrade/refresh loop: '
                    f'remaining_time={remaining} < 15'
                )
                return
            result = self._run_economy_atomic_batch(battle_mode=False)
            if result in ('complete', 'blocked'):
                return
            self.screenshot()

    def _run_battle_economy_until_budget_limit(self) -> None:
        """战阶段购买体系卡后续跑升级/刷新，并受 15 秒保护。"""
        if self._read_chess_mode() != '战':
            return
        # 与备阶段使用同一入口：先确保商店打开并购买当前体系卡，
        # 再根据金币门槛进入升级/刷新循环。
        self.purchase_lineup_cards_once()
        if self._read_chess_mode() != '战':
            return
        self._schedule_economy_cycle()
        while (
            self._read_chess_mode() == '战'
            and getattr(self, '_economy_pending', False)
        ):
            remaining = self._read_remaining_time()
            if remaining is not None and remaining < 15:
                logger.info(
                    'Stop Chess battle upgrade/refresh loop: '
                    f'remaining_time={remaining} < 15'
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
        time.sleep(self.ACTION_SETTLE_INTERVAL)
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
        """刷新回目状态截图；选符咒出现时必须优先处理完毕。"""
        self.screenshot()
        if not self.appear(self.I_SELECT_GRIGRI):
            return False
        logger.info(
            'Chess round-state refresh interrupted by grigri selection; '
            'resolve grigri before reading round and mode'
        )
        self.select_grigri()
        self.screenshot()
        return True

    def _finish_chess_game_after_markers_missing(
        self,
        context: str,
    ) -> bool:
        """两个局内标志连续三帧消失后，等待结算页并读取实际名次。"""
        if self._is_in_chess_game():
            return False

        for frame in range(2, self.GAME_END_CONFIRM_FRAMES + 1):
            time.sleep(2 * self.SLOW_POLL_INTERVAL)
            self.device.stuck_record_clear()
            self.screenshot()
            if self._is_in_chess_game():
                logger.debug(
                    'Chess game-end confirmation cancelled: '
                    f'in-game marker recovered at frame={frame}, '
                    f'context={context}'
                )
                return False

        logger.info(
            'Chess game end detected: all in-game markers absent for '
            f'{self.GAME_END_CONFIRM_FRAMES} frames, context={context}'
        )
        deadline = time.monotonic() + self.GAME_OVER_WAIT_TIMEOUT
        while time.monotonic() < deadline:
            self.device.stuck_record_clear()
            if self._is_in_chess_game():
                logger.info(
                    'Chess game-end wait cancelled: in-game marker recovered; '
                    f'reset missing-frame count, context={context}'
                )
                return False
            if self.appear(self.I_GAME_OVER_1) or self.appear(self.I_GAME_OVER_2):
                rank, raw = self._read_game_rank()
                self._last_game_rank = rank
                if rank is None:
                    logger.warning(
                        f'Chess game-over rank OCR invalid: [{raw}]'
                    )
                else:
                    logger.info(
                        f'Chess game-over rank OCR: [{raw}] -> 第{rank}名'
                    )
                self.return_to_chess_lobby()
                return True
            time.sleep(2 * self.SLOW_POLL_INTERVAL)
            self.screenshot()

        raise GameStuckError(
            'Chess: all in-game markers disappeared, but I_GAME_OVER did not '
            f'appear within {self.GAME_OVER_WAIT_TIMEOUT:.0f}s'
        )

    def _wait_for_round_start(self) -> int | None:
        """等待稳定回目数字；返回 None 表示本局已经结算。"""
        candidate = None
        confirmed = 0
        while True:
            self.device.stuck_record_clear()
            if self._refresh_round_state_screenshot():
                candidate = None
                confirmed = 0
                time.sleep(self.SLOW_POLL_INTERVAL)
                continue
            if self._finish_chess_game_after_markers_missing(
                'wait_for_round_start'
            ):
                return None

            round_no = self._read_round_number()
            if round_no is not None:
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
            time.sleep(self.SLOW_POLL_INTERVAL)

    def _is_in_chess_game(self) -> bool:
        """以阵容入口或问号图标确认当前处于百鬼棋局对局内。"""
        return (
            self.appear(self.I_OPEN_LINEUP)
            or self.appear(self.I_QUESTION_CHECK)
        )

    def _close_chess_lobby_abnormal_page(self) -> bool:
        """关闭棋局大厅开战时偶发出现的红色返回键异常页面。"""
        if not self.appear(self.I_BACK_RED):
            return False
        logger.warning(
            'Chess start blocked by abnormal lobby page; '
            'close it with back red'
        )
        for attempt in range(1, self.ACTION_ICON_MAX_ATTEMPTS + 1):
            self.device.click_record_remove(self.I_BACK_RED)
            self.click(self.I_BACK_RED)
            if self._wait_chess_action_state(
                lambda: not self.appear(self.I_BACK_RED)
            ):
                logger.info(
                    'Chess abnormal lobby page closed; '
                    f'attempt={attempt}/{self.ACTION_ICON_MAX_ATTEMPTS}'
                )
                return True
            logger.warning(
                'Chess abnormal lobby page still visible after click: '
                f'attempt={attempt}/{self.ACTION_ICON_MAX_ATTEMPTS}, '
                f'timeout={self.ACTION_ICON_WAIT_TIMEOUT:.0f}s'
            )
        raise GameStuckError(
            'Chess: failed to close abnormal lobby page after 3 attempts'
        )

    def _wait_until_in_chess_game(
        self,
        timeout: float,
        retry_start: bool = False,
    ) -> None:
        """点击开始后等待匹配，并在连续三次超时后结束任务。"""
        deadline = time.monotonic() + timeout
        waiting_logged = False
        waiting_started_at = None
        matchmaking_timeout = float(
            getattr(self, '_matchmaking_timeout_seconds', 60)
        )
        while True:
            # 匹配可能持续很久。截图本身会先检查设备卡死计时，因此必须
            # 在每次截图之前清除，不能等识别到“取消等待”后才清除。
            self.device.stuck_record_clear()
            self.screenshot()

            # 以阵容入口或问号图标确认真正进入棋局；商店按钮不再作为
            # 开局成功标志，避免大厅或匹配动画中的相似区域造成误判。
            if self._is_in_chess_game():
                logger.info('Chess matchmaking complete: entered battle')
                self._consecutive_matchmaking_timeouts = 0
                return

            if self.appear(self.I_CANCEL_WAITING):
                now = time.monotonic()
                if waiting_started_at is None:
                    waiting_started_at = now
                if not waiting_logged:
                    logger.info(
                        'Chess matchmaking: waiting for other players; '
                        f'limit={matchmaking_timeout:.0f}s'
                    )
                    waiting_logged = True
                self.device.stuck_record_clear()
                if now - waiting_started_at >= matchmaking_timeout:
                    self.click(self.C_CANCEL_WAITING)
                    self._consecutive_matchmaking_timeouts += 1
                    logger.warning(
                        'Chess matchmaking timeout: '
                        f'{self._consecutive_matchmaking_timeouts}/3, '
                        f'limit={matchmaking_timeout:.0f}s'
                    )
                    if self._consecutive_matchmaking_timeouts >= 3:
                        logger.warning('Chess matchmaking: 等待过多，结束任务')
                        self.set_next_run(
                            task='Chess',
                            success=False,
                            finish=True,
                        )
                        raise TaskEnd('Chess: 等待过多')
                    waiting_started_at = None
                    waiting_logged = False
                    deadline = now + timeout
                    time.sleep(self.ACTION_SETTLE_INTERVAL)
                    continue
                time.sleep(self.SLOW_POLL_INTERVAL)
                continue

            waiting_started_at = None
            waiting_logged = False

            if (
                retry_start
                and self.appear(self.I_BACK_RED)
                and self._close_chess_lobby_abnormal_page()
            ):
                self.device.stuck_record_clear()
                deadline = time.monotonic() + timeout
                continue

            if retry_start and self.appear(self.I_CHESS_START):
                if self.appear_then_click(
                    self.I_CHESS_START,
                    interval=2 * self.SLOW_POLL_INTERVAL,
                ):
                    self.device.stuck_record_clear()
                    deadline = time.monotonic() + timeout
            if time.monotonic() >= deadline:
                raise GameStuckError(
                    'Chess: timeout waiting for in-game markers'
                )
            time.sleep(self.SLOW_POLL_INTERVAL)

    def _start_chess_game(self) -> None:
        """从棋局大厅开战，确认进入局内后直接开始回合流程。"""
        logger.debug('Chess game start')
        # 式神本局属性：(守护之印, 御魂1, 御魂2)。
        # 守护之印不占普通御魂槽，三个属性均允许为空。
        self._board_shikigami_attributes = {}
        self._board_lineup_names = set()
        self._board_actual_positions = {}
        self._player_deployed_positions = set()
        self._arakawa_goldfish_current_position = None
        self._board_special_units = {}
        self._last_game_rank = None
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
        if self.chess_result_flow_visible():
            logger.debug('Chess startup recovery: unfinished result flow detected')
            self.return_to_chess_lobby()
            return True

        # 启动恢复属于全局页面判断，只允许使用 c_open_lineup.png 或
        # c_question_check.png。
        # chess_mode OCR 仅供已确认在局内后的回目状态机使用，不能拿来
        # 判断全局页面，否则庭院等页面中的任意非空误识别都会触发退出。
        if not self._is_in_chess_game():
            return False

        logger.warning(
            'Chess startup recovery: interrupted in-game state detected '
            'by I_OPEN_LINEUP or I_QUESTION_CHECK'
        )
        if not self.exit_chess_battle():
            raise GameStuckError(
                'Chess: interrupted game detected but active exit was unavailable'
            )
        return True

    def _run_game_by_rounds_without_device_stuck_timeout(self) -> None:
        """单局协调器：逐个调用单回目函数，直至完成结算返回。"""
        round_no = self._wait_for_round_start()
        while round_no is not None:
            round_no = self.run_one_round(round_no)
