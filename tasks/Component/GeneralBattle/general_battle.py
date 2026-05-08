# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from __future__ import annotations

import difflib
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from tasks.GameUi.default_pages import random_click
from typing import Callable, Union

from module.atom.gif import RuleGif
from module.atom.image import RuleImage
from module.atom.ocr import RuleOcr
from module.base.timer import Timer
from module.base.utils import color_similar, get_color
from module.logger import logger
from tasks.Component.GeneralBattle.assets import GeneralBattleAssets
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig, GreenMarkType, GreenMarkEnum
from tasks.Component.GeneralBuff.config_buff import BuffClass
from tasks.Component.GeneralBuff.general_buff import GeneralBuff
from tasks.GameUi.common import RecognizerLike, invoke_task_callable
from tasks.GameUi.matcher import Matcher, ensure_matcher
from tasks.GameUi.navigator import GameUi
from tasks.GameUi.page import page_battle, page_battle_prepare, page_battle_result, page_reward
from tasks.GameUi.page_definition import Page

# 战斗结束后用于确认“已经回到任务自身页面”的识别条件。
# 推荐优先复用调用方战后原本就会 `wait_until_appear(...)` 的稳定特征。
ExitMatcher = Union[Matcher | RecognizerLike | Page]
BattleInspectionAction = Callable[["BattleContext"], None]


@dataclass
class BattleBehaviorState:
    """记录一组一次性行为在某个生命周期内的执行状态。"""

    # 已执行行为名集合；共享状态与调用级状态都通过该集合判断是否需要再次执行。
    done: set[str] = field(default_factory=set)


@dataclass
class BattleTimedInspection:
    """声明 battle 阶段的一个具名定时巡检项。"""

    # 巡检项稳定标识；用于运行时 timer 容器索引。
    name: str
    # 巡检触发间隔，单位秒。
    interval: float
    # 巡检到期后的执行动作。
    action: BattleInspectionAction
    # 巡检项自己的运行时 timer；仅在进入 `page_battle` 后才会启动。
    timer: Timer = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """初始化巡检项自身的 timer。"""

        if self.interval <= 0:
            raise ValueError(f"Timed battle inspection interval must be > 0: {self.name}")
        self.timer = Timer(self.interval)

    def arm(self) -> None:
        """在进入新的 battle 窗口时启动或重置 timer。"""

        if self.timer.started():
            self.timer.reset()
            return
        self.timer.start()

    def tick(self, context: "BattleContext") -> bool:
        """推进一次巡检项计时，命中时执行动作。

        Returns:
            bool: 本轮是否实际触发了巡检动作。
        """

        if not self.timer.started():
            self.timer.start()
            return False
        if not self.timer.reached_and_reset():
            return False
        self.action(context)
        return True


@dataclass
class BattleContext:
    """保存单次 `run_general_battle()` 调用期内的战斗上下文字段。"""

    # 当前调用使用的战斗硬超时计时器；每次进入 `run_general_battle()` 时重建。
    battle_timer: Timer
    # 长战斗卡死保护刷新计时器；每次进入 `run_general_battle()` 时重建。
    long_refresh_timer: Timer
    # 当前调用使用的战斗类型分组键；决定共享行为状态的归属。
    battle_key: str
    # 当前 `battle_key` 共享的一次性行为状态。
    shared_behavior_state: BattleBehaviorState
    # 当前 `run_general_battle()` 调用级的一次性行为状态。
    call_behavior_state: BattleBehaviorState
    # 当前调用内本轮连战的一次性行为状态；进入下一轮时重置。
    round_behavior_state: BattleBehaviorState
    # 当前调用各行为默认使用的作用域映射。
    behavior_scopes: dict[str, "BattleBehaviorScope"]
    # 当前调用 battle 阶段生效的具名定时巡检项。
    timed_battle_inspections: dict[str, BattleTimedInspection]
    # 当前调用需要开启的 buff 配置；供 handler 和子类覆写逻辑直接读取。
    buff: Union[BuffClass | list[BuffClass] | None] = None
    # 最近一次稳定识别到的战斗页面；用于驱动连战和超时逻辑。
    last_page: Page | None = None
    # 单次调用内的连战轮次计数；首轮从 1 开始。
    continuous_count: int = 1
    # 结算结束后暂时识别不到战斗页面时的首个时间戳；用于 x 秒兜底。
    reward_no_battle_ts: float | None = None
    # 当前调用是否已进入快速退出路径；该状态只在本次调用内有效。
    quick_exit: bool = False
    # 最近一次结算页解析出的胜负结果；用于退出时返回最终布尔值。
    is_win: bool = False


class BattleBehaviorScope(str, Enum):
    """声明一次性行为应在哪个生命周期内只执行一次。"""

    # 同一 `battle_key` 下跨多次 `run_general_battle()` 调用只执行一次。
    BATTLE_KEY = "battle_key"
    # 单次 `run_general_battle()` 调用中只执行一次；连战会继续复用该状态。
    CALL = "call"
    # 单次 `run_general_battle()` 调用内每一轮连战各执行一次。
    ROUND = "round"


class BattleAction(str, Enum):
    CONTINUE = "continue"
    EXIT_WIN = "exit_win"
    EXIT_LOSE = "exit_lose"
    QUICK_EXIT = "quick_exit"


class GeneralBattle(GeneralBuff, GeneralBattleAssets):
    """
    使用这个通用的战斗必须要求这个任务的 config 有 general_battle_config。
    """

    def __init__(self, config, device) -> None:
        """初始化通用战斗运行时缓存。

        Args:
            config: 当前任务配置对象。
            device: 当前设备对象。
        """
        super().__init__(config, device)
        # 以 `battle_key` 为键保存共享行为状态；同战斗类型的多次调用会复用这里的状态。
        self._battle_shared_state: dict[str, BattleBehaviorState] = {}
        # 当前 `run_general_battle()` 调用使用的战斗上下文；仅在通用战斗主循环中有效。
        self._battle_context: BattleContext | None = None
        # 标记当前任务 session 内的战斗页面覆写是否已注册，避免重复污染 session 副本。
        self._custom_pages_registered: bool = False

    def _register_custom_pages(self) -> None:
        """供子任务在 session 内覆写战斗页面识别规则。

        Returns:
            None: 基类默认不做任何处理。
        """

    def _exit_matcher(self) -> ExitMatcher | None:
        """返回任务级默认的战斗结束识别条件。

        子任务可覆写此方法，声明“战斗结算完成后，理论上应该回到哪里”。
        典型返回值是任务主界面的按钮、房间页标记或一个 `Page` 对象。
        若任务内不同调用点会回到不同页面，优先在 `run_general_battle(..., exit_matcher=...)`
        里显式传参覆盖，而不是在这里写复杂分支。

        Returns:
            ExitMatcher | None: 默认结束识别条件；`None` 表示禁用快速结束，回退到 2 秒兜底。
        """

        return None

    def _evaluate_exit_matcher(self, target: ExitMatcher | None) -> bool:
        """执行一次 exit matcher 判断。

        分派规则保持最小化，不引入新的识别栈：

        - `None`：直接返回 `False`
        - `Page`：解析为当前 session page 后用 `match_page_once()` 判定
        - 自定义 callable：透传当前任务实例，兼容零参/单参函数
        - 其他 Rule/Matcher：统一走 `ensure_matcher(...).evaluate(self)`

        Args:
            target: 待判定的结束识别条件。

        Returns:
            bool: 当前截图是否已经满足该结束识别条件。
        """

        if target is None:
            return False
        if isinstance(target, Page):
            session_page = self.navigator.resolve_page(target)
            if session_page is None:
                return False
            return bool(self.match_page_once(session_page))
        if callable(target) and not isinstance(target, (RuleImage, RuleGif, RuleOcr)):
            return bool(invoke_task_callable(target, self))

        matcher = ensure_matcher(target)
        if matcher is None:
            return False
        return bool(matcher.evaluate(self))

    def is_in_battle(self, is_screenshot: bool = True) -> bool:
        """兼容旧任务的战斗态快速检测。

        Args:
            is_screenshot: 是否先执行一次截图。

        Returns:
            bool: 当前是否处于准备、战斗、结算或奖励相关页面。
        """

        if is_screenshot:
            self.screenshot()
        return (
            self.appear(self.I_BATTLE_INFO)
            or self.appear(self.I_PREPARE_HIGHLIGHT)
            or self.appear(self.I_FRIENDS)
            or self.appear(self.I_EXIT)
            or self.appear(self.I_WIN)
            or self.appear(self.I_DE_WIN)
            or self.appear(self.I_FALSE)
            or self.appear(self.I_REWARD)
            or self.appear(self.I_REWARD_GOLD)
        )

    def is_in_real_battle(self, is_screenshot: bool = True) -> bool:
        """兼容旧任务的纯战斗中检测。

        Args:
            is_screenshot: 是否先执行一次截图。

        Returns:
            bool: 当前是否处于真正的战斗中页面。
        """

        if is_screenshot:
            self.screenshot()
        return self.appear(self.I_BATTLE_INFO)

    def is_in_prepare(self, is_screenshot: bool = True) -> bool:
        """兼容旧任务的准备页检测。

        Args:
            is_screenshot: 是否先执行一次截图。

        Returns:
            bool: 当前是否处于准备页。
        """

        if is_screenshot:
            self.screenshot()
        return (
            self.appear(self.I_BUFF)
            or self.appear(self.I_PREPARE_HIGHLIGHT)
            or self.appear(self.I_PREPARE_DARK)
            or self.appear(self.I_PRESET)
            or self.appear(self.I_PRESET_WIT_NUMBER)
        )

    def _resolve_battle_timeout(self, config: GeneralBattleConfig) -> int:
        """解析当前战斗应使用的硬超时时间。

        Args:
            config: 当前通用战斗配置。

        Returns:
            int: 本次战斗的超时秒数。
        """
        if config.battle_timeout is not None and config.battle_timeout > 0:
            return config.battle_timeout
        global_battle = getattr(getattr(self.config, "global_game", None), "battle", None)
        return getattr(global_battle, "battle_timeout", 420)

    def _build_context(
        self,
        config: GeneralBattleConfig,
        buff: Union[BuffClass | list[BuffClass] | None],
        battle_key: str,
    ) -> BattleContext:
        """构建一次战斗调用期使用的战斗上下文。

        Args:
            config: 当前通用战斗配置。
            buff: 当前调用需要开启的 buff 配置。
            battle_key: 当前战斗类型分组键。

        Returns:
            BattleContext: 初始化后的战斗上下文对象。
        """
        timeout = self._resolve_battle_timeout(config)
        return BattleContext(
            battle_timer=Timer(timeout).start(),
            long_refresh_timer=Timer(180).start(),
            battle_key=battle_key,
            shared_behavior_state=self._battle_shared_state.setdefault(battle_key, BattleBehaviorState()),
            call_behavior_state=BattleBehaviorState(),
            round_behavior_state=BattleBehaviorState(),
            behavior_scopes=self._get_battle_behavior_scopes(config, battle_key),
            timed_battle_inspections=self._build_timed_battle_inspections(config, battle_key),
            buff=buff,
            quick_exit=bool(config.quick_exit),
        )

    def _get_battle_behavior_scopes(self, config: GeneralBattleConfig, battle_key: str) -> dict[str, BattleBehaviorScope]:
        """返回本次通用战斗中各一次性行为的默认执行作用域。

        子任务可覆写此方法，按战斗类型调整某个行为的生命周期，而不必重写整段
        `_handle_prepare()` / `_handle_in_battle()` 主流程。

        Args:
            config: 当前通用战斗配置。
            battle_key: 当前战斗类型分组键，用于声明共享状态归属。

        Returns:
            dict[str, BattleBehaviorScope]: 行为名到作用域的映射。
        """
        return {
            "preset": BattleBehaviorScope.BATTLE_KEY,
            "buff": BattleBehaviorScope.BATTLE_KEY,
            "green": BattleBehaviorScope.CALL,
        }

    def _get_timed_battle_inspections(self, config: GeneralBattleConfig, battle_key: str) -> tuple[BattleTimedInspection, ...]:
        """返回当前 battle 生效的定时巡检项集合。

        子任务可覆写此方法，为特定 `battle_key` 追加更多具名巡检项。

        Args:
            config: 当前通用战斗配置。
            battle_key: 当前战斗类型分组键。

        Returns:
            tuple[BattleTimedInspection, ...]: 当前 battle 生效的巡检项集合。
        """

        return (
            BattleTimedInspection(
                name="recover_auto_mode",
                interval=60,
                action=self._inspection_recover_auto_mode,
            ),
        )

    def _build_timed_battle_inspections(
        self,
        config: GeneralBattleConfig,
        battle_key: str,
    ) -> dict[str, BattleTimedInspection]:
        """构建当前 battle 使用的具名巡检项索引。

        Args:
            config: 当前通用战斗配置。
            battle_key: 当前战斗类型分组键。

        Returns:
            dict[str, BattleTimedInspection]: 以巡检项名称为键的声明映射。

        Raises:
            ValueError: 巡检项名称重复或间隔非法。
        """

        inspections: dict[str, BattleTimedInspection] = {}
        for inspection_decl in self._get_timed_battle_inspections(config, battle_key):
            if inspection_decl.name in inspections:
                raise ValueError(f"Duplicate timed battle inspection name: {inspection_decl.name}")
            inspections[inspection_decl.name] = BattleTimedInspection(
                name=inspection_decl.name,
                interval=inspection_decl.interval,
                action=inspection_decl.action,
            )
        return inspections

    def _get_battle_context(self) -> BattleContext:
        """返回当前通用战斗调用的战斗上下文。

        Returns:
            BattleContext: 当前 `run_general_battle()` 调用使用的战斗上下文。

        Raises:
            RuntimeError: 当前不在 `run_general_battle()` 主循环中，无法访问战斗上下文。
        """

        if self._battle_context is None:
            raise RuntimeError("Battle context is only available during run_general_battle()")
        return self._battle_context

    def _get_behavior_scope(self, behavior_name: str) -> BattleBehaviorScope:
        """解析某个行为本次调用应使用的作用域。

        Args:
            behavior_name: 待解析的行为名。

        Returns:
            BattleBehaviorScope: 该行为应使用的作用域。
        """

        context = self._get_battle_context()
        return context.behavior_scopes.get(behavior_name, BattleBehaviorScope.CALL)

    def _get_behavior_state(self, scope: BattleBehaviorScope) -> BattleBehaviorState:
        """根据作用域选择状态容器。

        Args:
            scope: 当前行为的执行作用域。

        Returns:
            BattleBehaviorState: 本次行为应读写的状态容器。
        """

        context = self._get_battle_context()
        if scope == BattleBehaviorScope.BATTLE_KEY:
            return context.shared_behavior_state
        if scope == BattleBehaviorScope.ROUND:
            return context.round_behavior_state
        return context.call_behavior_state

    def _run_battle_behavior_once(self, behavior_name: str, action: Callable[[], None]) -> bool:
        """按作用域保证某个行为在对应生命周期内只执行一次。

        Args:
            behavior_name: 行为名；用于在状态容器中记录执行结果。
            action: 需要在首次执行时触发的行为函数。

        Returns:
            bool: `True` 表示本次实际执行了行为，`False` 表示已执行过而跳过。
        """

        state = self._get_behavior_state(self._get_behavior_scope(behavior_name))
        if behavior_name in state.done:
            return False
        action()
        state.done.add(behavior_name)
        return True

    @staticmethod
    def build_quick_exit_config(config: GeneralBattleConfig | None = None) -> GeneralBattleConfig:
        """基于现有配置构造一个快速退出专用配置副本。

        Args:
            config: 原始通用战斗配置；为空时使用默认配置。

        Returns:
            GeneralBattleConfig: 仅将 `quick_exit` 置为 `True` 的配置副本。
        """
        base_config = config if config is not None else GeneralBattleConfig()
        return base_config.model_copy(update={"quick_exit": True})

    def _reset_round_context(self, context: BattleContext, config: GeneralBattleConfig, *, continuous_count: int) -> None:
        """在连战开启时重置下一轮战斗的运行时字段。

        Args:
            context: 当前战斗上下文对象。
            config: 当前通用战斗配置。
            continuous_count: 下一轮连战计数。

        Returns:
            None: 直接原地修改 `context`。
        """
        context.battle_timer = Timer(self._resolve_battle_timeout(config)).start()
        context.long_refresh_timer = Timer(180).start()
        context.last_page = None
        context.reward_no_battle_ts = None
        context.quick_exit = bool(config.quick_exit)
        context.continuous_count = continuous_count
        context.round_behavior_state = BattleBehaviorState()

    def _reset_timed_battle_inspection_timers(self, context: BattleContext) -> None:
        """统一重置当前 battle 生效巡检项的 timer。"""

        for inspection in context.timed_battle_inspections.values():
            inspection.arm()

    def _tick_timed_battle_inspections(self, context: BattleContext) -> None:
        """推进当前 battle 的定时巡检项。"""

        for inspection in context.timed_battle_inspections.values():
            inspection.tick(context)

    def _inspection_recover_auto_mode(self, context: BattleContext) -> None:
        """默认 battle 巡检项：检测手动并恢复自动。"""

        hand_marker = getattr(self, "O_BATTLE_HAND", None)
        auto_marker = getattr(self, "O_BATTLE_AUTO", None)
        if hand_marker is None or auto_marker is None:
            return
        if not self.appear(hand_marker):
            return

        logger.info("Timed inspection hit: recover battle auto mode")
        self.ui_click(hand_marker, auto_marker, interval=0.8)

    def _tick_long_battle(self, context: BattleContext) -> None:
        """按固定周期刷新长战斗卡死保护标记。

        Args:
            context: 当前战斗上下文对象。

        Returns:
            None: 需要刷新时原地重置底层长等待状态。
        """
        if context.long_refresh_timer.reached():
            logger.info("Refresh long battle stuck timer")
            self.device.stuck_record_clear()
            self.device.stuck_record_add("BATTLE_STATUS_S")
            context.long_refresh_timer.reset()

    def _ensure_battle_stuck_guard(self, context: BattleContext, page: Page) -> None:
        """在准备/战斗中阶段确保底层长等待标记始终存在。

        Args:
            context: 当前战斗上下文对象。
            page: 当前识别到的战斗页面。

        Returns:
            None: 需要时原地补挂战斗卡死保护标记。
        """

        if page not in {page_battle_prepare, page_battle}:
            return
        if context.last_page not in {page_battle_prepare, page_battle}:
            logger.info("Arm battle stuck guard")
            if "BATTLE_STATUS_S" not in self.device.detect_record:
                self.device.stuck_record_add("BATTLE_STATUS_S")
            context.battle_timer.reset()
            context.long_refresh_timer.reset()
            return
        if "BATTLE_STATUS_S" in self.device.detect_record:
            return

        self.device.stuck_record_add("BATTLE_STATUS_S")
        context.long_refresh_timer.reset()

    def _tick_timeout(self, context: BattleContext) -> None:
        """推进战斗超时检测。

        Args:
            context: 当前战斗上下文对象。

        Returns:
            None: 超时时将 `context.quick_exit` 置为 `True`。
        """
        if context.quick_exit:
            return
        if context.last_page not in {page_battle_prepare, page_battle}:
            return
        if context.battle_timer.reached():
            logger.warning(f"Battle timeout reached: {context.battle_timer.limit}s")
            context.quick_exit = True

    def _handle_prepare(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        """处理准备页逻辑。

        Args:
            context: 当前战斗上下文对象。
            config: 当前通用战斗配置。

        Returns:
            BattleAction: 当前轮准备页处理后的动作决策。
        """
        if context.quick_exit:
            return BattleAction.QUICK_EXIT
        if context.last_page in {page_battle, page_battle_result, page_reward}:
            if not config.continuous_battle:
                return BattleAction.EXIT_WIN if context.is_win else BattleAction.EXIT_LOSE
            action = self._handle_continuous_prepare(context, config)
            if action != BattleAction.CONTINUE:
                return action

        if self.appear_then_click(self.I_DISABLE_7DAYS_DIFF_SOUL, interval=0.6):
            return BattleAction.CONTINUE
        if self.appear_then_click(self.I_CONFIRM_CLOSE_DIFF_SOUL, interval=0.6):
            return BattleAction.CONTINUE

        self._run_battle_behavior_once(
            behavior_name="preset",
            action=lambda: self.switch_preset_team(config.preset_enable, config.preset_group, config.preset_team),
        )
        self._run_battle_behavior_once(
            behavior_name="buff",
            action=lambda: self.check_and_open_buff(context.buff),
        )
        self.appear_then_click(self.I_PREPARE_HIGHLIGHT, interval=0.8)
        return BattleAction.CONTINUE

    def _handle_in_battle(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        """处理战斗中页面逻辑。

        Args:
            context: 当前战斗上下文对象。
            config: 当前通用战斗配置。

        Returns:
            BattleAction: 当前轮战斗中处理后的动作决策。
        """
        if context.quick_exit:
            return BattleAction.QUICK_EXIT
        if context.last_page != page_battle:
            self._reset_timed_battle_inspection_timers(context)
        self._tick_timed_battle_inspections(context)
        self._run_battle_behavior_once(
            behavior_name="green",
            action=lambda: self.green_mark(config.green_enable, config.green_mark,
                                           config.green_mark_type, config.green_mark_name),
        )
        if config.random_click_swipt_enable:
            self.random_click_swipt()
        return BattleAction.CONTINUE

    def _handle_result(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        """处理结算页面逻辑。

        Args:
            context: 当前战斗上下文对象。
            config: 当前通用战斗配置。

        Returns:
            BattleAction: 当前轮结算页处理后的动作决策。
        """
        context.reward_no_battle_ts = None
        context.is_win = not self.appear(self.I_FALSE, threshold=0.8)
        self.click(random_click(), interval=0.8)
        self.device.click_record_clear()
        return BattleAction.CONTINUE

    def _handle_reward(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        """处理奖励页面逻辑。

        Args:
            context: 当前战斗上下文对象。
            config: 当前通用战斗配置。

        Returns:
            BattleAction: 当前轮奖励页处理后的动作决策。
        """
        context.reward_no_battle_ts = None
        # TODO: 部分副本奖励界面不一定是战斗成功, 需要重写
        context.is_win = True
        self.click(random_click(), interval=0.8)
        self.device.click_record_clear()
        return BattleAction.CONTINUE

    def _handle_missing_battle_page(self, context: BattleContext, config: GeneralBattleConfig,
                                    exit_matcher: ExitMatcher | None) -> BattleAction:
        """处理暂时未识别到任何战斗页面的过渡状态。

        Args:
            context: 当前战斗上下文对象。
            config: 当前通用战斗配置。
            exit_matcher: 战斗结束后的任务页面识别条件。
                仅在最近一页是 `page_battle_result/page_reward` 且未开启连战时参与快速退出判定。

        Returns:
            BattleAction: 根据结算收尾状态推导出的动作决策。
        """
        if (
            context.last_page in {page_battle_result, page_reward}
            and not config.continuous_battle
            and exit_matcher is not None
            and self._evaluate_exit_matcher(exit_matcher)
        ):
            logger.info("Exit matcher hit, battle confirmed ended")
            return BattleAction.EXIT_WIN if context.is_win else BattleAction.EXIT_LOSE
        if context.last_page not in {page_battle_result, page_reward} and context.reward_no_battle_ts is None:
            return BattleAction.CONTINUE
        if context.reward_no_battle_ts is None:
            context.reward_no_battle_ts = time.time()
            return BattleAction.CONTINUE
        if time.time() - context.reward_no_battle_ts >= 2.5:
            return BattleAction.EXIT_WIN if context.is_win else BattleAction.EXIT_LOSE
        return BattleAction.CONTINUE

    def _handle_continuous_prepare(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        """处理结算后回到准备页时的连战分支。

        Args:
            context: 当前战斗上下文对象。
            config: 当前通用战斗配置。

        Returns:
            BattleAction: 连战继续、按结果退出等动作决策。
        """
        if 0 < config.max_continuous <= context.continuous_count:
            return BattleAction.EXIT_WIN if context.is_win else BattleAction.EXIT_LOSE
        logger.hr("General battle start", 2)
        next_count = context.continuous_count + 1
        self.current_count += 1
        logger.info(f"Current count: {self.current_count}")
        logger.info(f"Continue battle round: {next_count}")
        self.device.click_record_clear()
        self._reset_round_context(context, config, continuous_count=next_count)
        return BattleAction.CONTINUE

    def _resolve_action(self, action: BattleAction) -> bool | None:
        """统一处理内部动作枚举并解析最终返回值。

        Args:
            action: 当前处理得到的动作枚举。

        Returns:
            bool | None: `True/False` 表示战斗结束结果，`None` 表示继续主循环。
        """
        if action == BattleAction.EXIT_WIN:
            logger.info("Battle result: Win")
            return True
        if action == BattleAction.EXIT_LOSE:
            logger.info("Battle result: Lose")
            return False
        if action == BattleAction.QUICK_EXIT:
            self.device.screenshot_interval_set()
            self.exit_battle()
        return None

    def run_general_battle(
        self,
        config: GeneralBattleConfig = None,
        buff: Union[BuffClass | list[BuffClass]] = None,
        battle_key: str = "default",
        exit_matcher: ExitMatcher | None = None,
    ) -> bool:
        """
        运行基于 Page FSM 的通用战斗。

        Args:
            config: 当前通用战斗配置；为空时使用默认配置。
            buff: 本轮战斗需要开启的 buff 配置。
            battle_key: 战斗类型分组键；同 key 共享 `BATTLE_KEY` 作用域行为状态。
            exit_matcher: 本次调用专用的结束识别条件。
                优先级高于 `_exit_matcher()`；适合同一任务不同入口回不同页面的场景。
                传 `None` 时会继续尝试任务级 `_exit_matcher()`，若仍为空则回退到 2 秒兜底。

        Returns:
            bool: `True` 表示本轮战斗获胜，`False` 表示失败或主动退出。
        """
        logger.hr("General battle start", 2)
        if config is None:
            config = GeneralBattleConfig()
        if not self._custom_pages_registered:
            self._register_custom_pages()
            self._custom_pages_registered = True
        self.current_count += 1
        logger.info(f"Current count: {self.current_count}")
        self.device.stuck_record_add("BATTLE_STATUS_S")
        self.device.click_record_clear()
        context = self._build_context(config, buff, battle_key)
        self._battle_context = context
        resolved_exit_matcher = exit_matcher if exit_matcher is not None else self._exit_matcher()
        try:
            while True:
                self.screenshot()
                self._tick_long_battle(context)
                self._tick_timeout(context)
                page = GameUi.detect_page_in(self, page_battle_prepare, page_battle, page_battle_result,
                                             page_reward, include_global=False)
                context.reward_no_battle_ts = None if page else context.reward_no_battle_ts
                self._ensure_battle_stuck_guard(context, page)
                match page:
                    case None:
                        action = self._handle_missing_battle_page(context, config, resolved_exit_matcher)
                    case current if current == page_battle_prepare:
                        self.device.screenshot_interval_set()
                        action = self._handle_prepare(context, config)
                    case current if current == page_battle:
                        self.device.screenshot_interval_set('combat')
                        action = self._handle_in_battle(context, config)
                    case current if current == page_battle_result:
                        self.device.screenshot_interval_set()
                        action = self._handle_result(context, config)
                    case current if current == page_reward:
                        self.device.screenshot_interval_set()
                        action = self._handle_reward(context, config)
                    case _:
                        action = BattleAction.CONTINUE
                resolved = self._resolve_action(action)
                if resolved is not None:
                    return resolved
                context.last_page = page if page else context.last_page
        finally:
            self._battle_context = None
            self.device.screenshot_interval_set()

    def exit_battle(self, skip_first: bool = False) -> bool:
        """
        在战斗的时候强制退出战斗。

        Args:
            skip_first: 是否跳过第一次截图，直接复用当前帧判断。

        Returns:
            bool: 是否识别到可退出的战斗页面并执行了退出流程。
        """
        if skip_first:
            self.screenshot()
        if not self.appear(self.I_EXIT):
            return False
        while True:
            self.screenshot()
            if self.appear(self.I_EXIT_ENSURE):
                break
            if self.appear_then_click(self.I_EXIT, interval=1.5):
                continue
        while True:
            self.screenshot()
            if self.appear_then_click(self.I_EXIT_ENSURE, interval=1):
                continue
            if self.appear_then_click(self.I_FALSE, interval=1.5):
                continue
            if not self.appear(self.I_EXIT):
                break
        logger.info('Exit battle success')
        return True

    def green_mark(self, enable: bool = False, mark_mode: GreenMarkType = GreenMarkType.GREEN_MAIN,
                   green_mark_type: GreenMarkEnum = GreenMarkEnum.CHOOSE, green_mark_name: str = ''):
        """
        绿标， 如果不使能就直接返回。

        Args:
            enable: 是否启用绿标操作。
            mark_mode: 绿标目标位置。

        Returns:
            None: 直接执行绿标相关点击。
            :param enable:
            :param mark_mode:
            :param green_mark_name:
            :param green_mark_type:
        """
        if not enable:
            return
        logger.info("Green is enable")
        self.device.screenshot_interval_set()
        match green_mark_type:
            case GreenMarkEnum.CHOOSE:
                self.green_mark_choose(mark_mode)
            case GreenMarkEnum.NAME:
                self.green_mark_name(green_mark_name)
        self.device.screenshot_interval_set('combat')

    def green_mark_choose(self, mark_mode: GreenMarkType = GreenMarkType.GREEN_MAIN):
        x, y = None, None
        match mark_mode:
            case GreenMarkType.GREEN_LEFT1:
                x, y = self.C_GREEN_LEFT_1.coord()
                logger.info("Green left 1")
            case GreenMarkType.GREEN_LEFT2:
                x, y = self.C_GREEN_LEFT_2.coord()
                logger.info("Green left 2")
            case GreenMarkType.GREEN_LEFT3:
                x, y = self.C_GREEN_LEFT_3.coord()
                logger.info("Green left 3")
            case GreenMarkType.GREEN_LEFT4:
                x, y = self.C_GREEN_LEFT_4.coord()
                logger.info("Green left 4")
            case GreenMarkType.GREEN_LEFT5:
                x, y = self.C_GREEN_LEFT_5.coord()
                logger.info("Green left 5")
            case GreenMarkType.GREEN_MAIN:
                x, y = self.C_GREEN_MAIN.coord()
                logger.info("Green main")
        while True:
            self.screenshot()
            if not self.appear(self.I_PREPARE_HIGHLIGHT):
                break
        if self.appear_then_click(self.I_LOCAL):
            time.sleep(0.3)
        self.device.click(x, y)

    def green_mark_name(self, name: str = ''):
        if name == '':
            logger.warning("Green mark name is empty")
            return
        timeout_timer = Timer(6).start()
        best = {'name': '', 'x': -1, 'y': -1, 'similarity': 0.0}
        while not timeout_timer.reached():
            self.screenshot()
            results = self.O_GREEN_MARK_AREA.detect_and_ocr(self.device.image)
            for ret in results:
                similarity = difflib.SequenceMatcher(None, ret.ocr_text, name).ratio()
                if similarity > best['similarity']:
                    x = self.O_GREEN_MARK_AREA.roi[0] + ret.box[0, 0] + 5
                    y = self.O_GREEN_MARK_AREA.roi[1] + ret.box[0, 1] + 30
                    x = 1280 if x > 1280 else x
                    y = 720 if y > 720 else y
                    best = {'name': ret.ocr_text, 'x': x, 'y': y, 'similarity': similarity}
            if best['similarity'] > 0.5:
                logger.info(f'Green name success, text: {best["name"]}[{best["similarity"]:.2f}]')
                self.device.click(best['x'], best['y'], control_name=best['name'])
                return
        logger.warning(f'Green name failed, best text: {best["name"]}[{best["similarity"]:.2f}]')

    def switch_preset_team(self, enable: bool = False, preset_group: int = 1, preset_team: int = 1):
        """
        切换预设的队伍，要求是在不锁定队伍时的情况下。

        Args:
            enable: 是否启用切换预设。
            preset_group: 目标预设组编号。
            preset_team: 目标预设队伍编号。

        Returns:
            None: 成功时切换到目标预设，失败时保留当前阵容。
        """
        if not enable:
            logger.info("Preset is disable")
            return

        logger.info("Preset is enable")
        timeout_warning = "Switch preset timeout, use current team"

        wait_preset_timer = Timer(4).start()
        while 1:
            if wait_preset_timer.reached():
                logger.warning(timeout_warning)
                return
            self.screenshot()

            if self.appear(self.I_PRESET_ENSURE):
                break
            if self.appear(self.I_PRESENT_LESS_THAN_5):
                break
            if self.appear_then_click(self.I_PRESET, threshold=0.8, interval=1):
                continue
            if self.appear_then_click(self.I_PRESET_WIT_NUMBER, threshold=0.8, interval=1):
                continue
            if self.ocr_appear(self.O_PRESET):
                self.click(self.O_PRESET, interval=1)
                continue
            if self.ocr_appear(self.O_PRESET_FULL):
                self.click(self.O_PRESET_FULL, interval=1)
                continue
        logger.info("Click preset button")

        tmp = self.__getattribute__("C_PRESET_GROUP_" + str(preset_group))
        if tmp is None:
            tmp = self.C_PRESET_GROUP_1
        color_size = [self.C_PRESET_GROUP_1.roi_back[2], self.C_PRESET_GROUP_1.roi_back[3]]
        unselected_color = (224.9, 208.3, 187.4)
        choose_group_timer = Timer(4).start()
        while True:
            if choose_group_timer.reached():
                logger.warning(timeout_warning)
                return
            self.screenshot()
            color_tmp = get_color(
                self.device.image,
                (tmp.roi_back[0], tmp.roi_back[1], tmp.roi_back[0] + color_size[0], tmp.roi_back[1] + color_size[1]),
            )
            if color_similar(color_tmp, unselected_color):
                self.click(tmp, interval=0.2)
                continue
            break

        logger.info("Select preset group")

        time.sleep(0.5)
        tmp = self.__getattribute__("C_PRESET_TEAM_" + str(preset_team))
        if tmp is None:
            tmp = self.C_PRESET_TEAM_1
        color_size = [5, 5]
        unselected_color = (216.8, 185.0, 146.8)
        choose_team_timer = Timer(4).start()
        while True:
            if choose_team_timer.reached():
                logger.warning(timeout_warning)
                return
            self.screenshot()
            color_tmp = get_color(
                self.device.image,
                (tmp.roi_back[0], tmp.roi_back[1], tmp.roi_back[0] + color_size[0], tmp.roi_back[1] + color_size[1]),
            )
            if color_similar(color_tmp, unselected_color):
                self.click(tmp, interval=0.2)
                continue
            break

        self.click(tmp)
        logger.info("Select preset team")

        wait_ensure_timer = Timer(4).start()
        while 1:
            if wait_ensure_timer.reached():
                logger.warning(timeout_warning)
                return
            self.screenshot()
            if not self.appear(self.I_PRESET_ENSURE):
                break
            if self.appear_then_click(self.I_PRESET_ENSURE, interval=1):
                continue
        logger.info("Click preset ensure")

    def random_click_swipt(self):
        """在战斗过程中执行随机点击或滑动。

        Returns:
            None: 命中概率时执行随机操作，否则短暂等待。
        """
        if 0 <= random.randint(0, 500) <= 3:
            rand_type = random.randint(0, 2)
            match rand_type:
                case 0:
                    self.click(self.C_RANDOM_CLICK, interval=20)
                case 1:
                    self.swipe(self.S_BATTLE_RANDOM_LEFT, interval=20)
                case 2:
                    self.swipe(self.S_BATTLE_RANDOM_RIGHT, interval=20)
        else:
            time.sleep(0.4)

    def check_take_over_battle(self, is_screenshot: bool, config: GeneralBattleConfig) -> bool | None:
        """
        TODO: 旧接管入口，待所有调用方迁到 goto_page 接管后删除。
        中途接入战斗并接管。

        Args:
            is_screenshot: 是否先执行一次截图。
            config: 当前通用战斗配置。

        Returns:
            bool | None: 战斗结果；如果当前不在战斗态则返回 `None`。
        """
        if is_screenshot:
            self.screenshot()
        if not self.is_in_battle(False):
            return None
        return self.run_general_battle(config=config, battle_key="__legacy_takeover__")

    def check_lock(self, enable: bool, lock_image, unlock_image):
        """
        检测是否锁定队伍。

        Args:
            enable: 目标是否应为锁队状态。
            lock_image: 已锁定状态的识别图像。
            unlock_image: 未锁定状态的识别图像。

        Returns:
            None: 直接执行锁定状态切换。
        """
        if enable:
            logger.info("Lock team")
            while 1:
                self.screenshot()
                if self.appear(lock_image):
                    break
                if self.appear_then_click(unlock_image, interval=1):
                    continue
        else:
            logger.info("Unlock team")
            while 1:
                self.screenshot()
                if self.appear(unlock_image):
                    break
                if self.appear_then_click(lock_image, interval=1):
                    continue

    def check_and_open_buff(self, buff: Union[BuffClass | list[BuffClass]] = None):
        """
        检测是否开启 buff。

        Args:
            buff: 需要开启或关闭的 buff 配置；为空时直接跳过。

        Returns:
            None: 直接执行 buff 界面点击流程。
        """
        if not buff:
            return
        logger.info(f"Open buff {buff}")
        self.ui_click(self.I_BUFF, self.I_CLOUD, interval=2)
        if isinstance(buff, BuffClass):
            buff = [buff]
        match_method = {
            BuffClass.AWAKE: (self.awake, True),
            BuffClass.SOUL: (self.soul, True),
            BuffClass.GOLD_50: (self.gold_50, True),
            BuffClass.GOLD_100: (self.gold_100, True),
            BuffClass.EXP_50: (self.exp_50, True),
            BuffClass.EXP_100: (self.exp_100, True),
            BuffClass.AWAKE_CLOSE: (self.awake, False),
            BuffClass.SOUL_CLOSE: (self.soul, False),
            BuffClass.GOLD_50_CLOSE: (self.gold_50, False),
            BuffClass.GOLD_100_CLOSE: (self.gold_100, False),
            BuffClass.EXP_50_CLOSE: (self.exp_50, False),
            BuffClass.EXP_100_CLOSE: (self.exp_100, False),
        }
        for buff_item in buff:
            func, is_open = match_method[buff_item]
            func(is_open)
            time.sleep(0.1)
        logger.info("Open buff success")
        while 1:
            self.screenshot()
            if not self.appear(self.I_CLOUD):
                break
            if self.appear_then_click(self.I_BUFF, interval=1):
                continue


def run_task_or_default_general_battle(task) -> bool:
    """优先使用任务自身的通用战斗实现，缺失时回退默认 GeneralBattle。

    Args:
        task: 当前触发 `page_battle` hook 的任务实例。

    Returns:
        bool: 通用战斗执行结果。
    """
    battle_takeover = getattr(getattr(task.config, "global_game", None), "battle", None)
    on_takeover = getattr(battle_takeover, "on_takeover", "finish")
    on_takeover_value = getattr(on_takeover, "value", on_takeover)
    battle_config = GeneralBattle.build_quick_exit_config() if on_takeover_value == "exit" else None

    battle_handler = getattr(task, "run_general_battle", None)
    if callable(battle_handler):
        if battle_config is not None:
            return battle_handler(config=battle_config)
        return battle_handler()

    match_page_once = getattr(task, "match_page_once", None)
    navigator = getattr(task, "navigator", None)
    if not callable(match_page_once) or navigator is None:
        logger.warning("Battle page recognized but no general battle handler is available")
        return False

    fallback = GeneralBattle(config=task.config, device=task.device)
    fallback.navigator = navigator
    fallback.match_page_once = match_page_once
    fallback.current_count = task.current_count
    try:
        if battle_config is not None:
            return fallback.run_general_battle(config=battle_config)
        return fallback.run_general_battle()
    finally:
        task.current_count = fallback.current_count
