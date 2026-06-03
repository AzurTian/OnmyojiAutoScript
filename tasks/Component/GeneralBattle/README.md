# GeneralBattle FSM

`GeneralBattle` 现在按 4 个战斗阶段驱动：

- `_handle_prepare(context, config)`
- `_handle_in_battle(context, config)`
- `_handle_result(context, config)`
- `_handle_reward(context, config)`

`run_general_battle(config, buff, battle_key)` 会在单一循环里截图、识别 `page_battle_prepare` / `page_battle` / `page_battle_result` / `page_reward`，再把处理分派到对应 handler。

## 准备页点击时机

- 默认情况下，只要识别到 `page_battle_prepare`，基类就会按现有节奏尝试点击准备按钮。
- 当 `GeneralBattleConfig.lock_team_enable = True` 时，基类会改为“连续停留在准备页 3 秒后再点击准备”。
- 这个 3 秒窗口只统计连续停留时长；中途离开 `page_battle_prepare` 后会重置，下一次重新进入准备页时重新计时。

## 定时巡检

`GeneralBattle` 在 `page_battle` 阶段提供统一的定时巡检框架：

- 通过 `_get_timed_battle_inspections(config, battle_key)` 声明当前 battle 生效的巡检项。
- 每个巡检项都要有稳定唯一的 `name`、独立的 `interval` 和自己的 `action`。
- `timer` 直接内聚在 `BattleTimedInspection` 自身；进入新的 `page_battle` 时统一启动或重置，不需要再往 `BattleContext` 里追加 `xxx_timer` 字段。
- 巡检框架只负责“什么时候触发”，具体健康态判断和恢复动作由巡检项自己实现。
- 巡检 timer 不会在调用 `run_general_battle()` 时就开始计时，而是等到首次进入 `page_battle` 后才启用。

基类默认内置一个 `recover_auto_mode` 巡检项：

- 间隔为 60 秒。
- 触发时复用 `GameUi` 的 `O_BATTLE_HAND` / `O_BATTLE_AUTO`。
- 仅当明确识别到“手动”时才点击切回自动；已经是自动时不会额外点击。

### 扩展示例

如果后续要追加一个“每 30 秒检查绿标状态”的巡检项，不需要再增加新的上下文字段，只要覆写钩子并追加一个声明即可：

```python
from tasks.Component.GeneralBattle.general_battle import BattleTimedInspection

def _get_timed_battle_inspections(self, config, battle_key):
    inspections = list(super()._get_timed_battle_inspections(config, battle_key))
    inspections.append(
        BattleTimedInspection(
            name="green_mark_status",
            interval=30,
            action=lambda context: self._inspect_green_mark_status(context, config),
        )
    )
    return tuple(inspections)
```

要求：

- `name` 必须唯一，否则构建上下文时会直接报错。
- `interval` 必须大于 0。
- 巡检动作内部自己决定“是否健康”和“如何恢复”，不要把业务判断塞回统一调度层。

### 生命周期

- 每次从非 `page_battle` 页面首次进入 `page_battle` 时，会统一启动或重置当前生效巡检项的 timer。
- battle 首帧也会走同一套巡检推进逻辑，但因为 timer 刚启动，不会立刻触发。
- 持续停留在 `page_battle` 的后续循环里，会继续逐个巡检项检查各自 timer 是否到期。
- 连战下一轮重新进入 `page_battle` 时，会开启新的巡检窗口，不继承上一轮剩余计时。

## 快速结束识别

`run_general_battle(config, buff, battle_key, exit_matcher=None)` 支持在结算/奖励之后用任务自身页面特征提前结束，不再一律等待 `reward_no_battle_ts` 的 2 秒兜底。

- `exit_matcher` 参数优先级高于 `_exit_matcher()` 钩子。
- `_exit_matcher()` 适合整任务固定返回页。
- `exit_matcher=` 适合同一任务不同场景返回不同页面。
- 支持类型：`Matcher`、`RecognizerLike`、`Page`。
- `RecognizerLike` 在这里就是 `RuleImage`、`RuleOcr`、`RuleGif` 或自定义 `callable(task) -> bool`。
- 仅当上一轮页面是 `page_battle_result` 或 `page_reward`，且 `continuous_battle=False` 时才会触发快速结束。
- 未声明 matcher 时，行为与之前一致，继续走 2 秒兜底。

### 选择原则

- 优先选“战后调用方本来就会等到的稳定特征”，例如房间页入口按钮、返回按钮、任务主界面标题。
- 不要选战斗中、结算动画中也可能短暂出现的元素，否则虽然主循环有限制窗口，仍会增加误判成本。
- 同一任务所有战斗都回同一个页面时，覆写 `_exit_matcher()` 最省事。
- 同一任务不同模式回不同页面时，用 `run_general_battle(..., exit_matcher=...)` 在调用点传参。
- 如果需要组合条件，直接用 `any_of(...)` / `all_of(...)`，不要在任务里重复造判断轮子。
- 连战场景会自动跳过 exit matcher；不要指望它在 `continuous_battle=True` 时帮你提前结束。

### 运行时行为

- `exit_matcher` 命中时会打印 `Exit matcher hit, battle confirmed ended`。
- 命中后直接返回最近一次结算得到的胜负，不会改写 `context.is_win`。
- `exit_matcher` 未命中时不会有额外副作用，仍按旧逻辑等待 2 秒兜底。

### 钩子示例

```python
from tasks.Component.GeneralBattle.general_battle import ExitMatcher

def _exit_matcher(self) -> ExitMatcher:
    return self.I_BACK_RED
```

上面的写法适合 `RealmRaid`、`AreaBoss` 这类“每次战斗都回同一个任务页”的场景。

### 参数示例

```python
self.run_general_battle(
    config=self.config.orochi.general_battle_config,
    battle_key=self._orochi_battle_key(),
    exit_matcher=self.I_OROCHI_FIRE,
)

self.run_general_battle(
    config=self.config.orochi.general_battle_config,
    battle_key=self._orochi_battle_key(),
    exit_matcher=self.I_CHECK_TEAM,
)
```

上面的写法适合 `Orochi`、`FallenSun` 这类同一任务里同时存在单刷、组队、野队等多种返回页的场景。

## `battle_key`

- `battle_key` 用来标识“同一种战斗类型”的共享上下文。
- 同一个 `battle_key` 会复用共享行为状态；默认情况下，切预设 / 开 buff 只做一次。
- 绿标默认按单次 `run_general_battle()` 调用执行；同一 `battle_key` 下再次调用时会重新绿标。
- 连战会复用同一次调用的 `call_behavior_state`，因此默认不会在下一轮连战中重复绿标。
- 不同战斗类型应传不同 key，避免互相污染。
- 全局接管固定使用 `__legacy_takeover__`。

## 行为作用域

- `BATTLE_KEY`：同一 `battle_key` 下跨多次 `run_general_battle()` 调用只执行一次。
- `CALL`：单次 `run_general_battle()` 调用中只执行一次；连战轮次继续复用该状态。
- `ROUND`：单次 `run_general_battle()` 调用内，每一轮连战各执行一次；进入下一轮时重置。
- 基类默认策略是 `preset -> BATTLE_KEY`、`buff -> BATTLE_KEY`、`green -> CALL`。
- 子任务可以覆写 `_get_battle_behavior_scopes(config, battle_key)` 调整某个行为的执行频率，而不必重写整个 prepare/battle handler。
- 当前 `BattleContext` 同时保存运行时字段、共享行为状态、调用级行为状态、轮次级行为状态与 `buff` 配置。
- 在 handler 或子任务扩展逻辑里，直接调用 `_run_battle_behavior_once("green", lambda: ...)` 即可复用当前通用战斗调用的上下文，不需要再手动透传行为状态。

### 作用域差异

- `BATTLE_KEY` 适合预设、buff 这类“同一种战斗类型只做一次”的行为。
- `CALL` 适合单次 `run_general_battle()` 内只做一次、但下一次重新调用可以再做一次的行为。
- `ROUND` 适合连战中每一轮都要重新校正一次的行为，例如某些特殊场景下的逐轮绿标。

### 连战示例

- 若某行为声明为 `CALL`，那么一次 `run_general_battle()` 的第 1 轮执行后，第 2 轮、第 3 轮连战都会复用，不会再次执行。
- 若某行为声明为 `ROUND`，那么同一次 `run_general_battle()` 的第 1 轮执行后，进入第 2 轮时会重新具备执行资格。
- 若某行为声明为 `BATTLE_KEY`，那么同一 `battle_key` 下后续再次调用 `run_general_battle()` 时仍会复用已经执行过的状态。

## 自定义页面识别

子任务不要改全局 `PageRegistry`，而是在 `_register_custom_pages()` 里改当前 session 的页面副本：

```python
from tasks.GameUi.page import any_of, page_reward

def _register_custom_pages(self) -> None:
    reward_page = self.navigator.resolve_page(page_reward)
    if reward_page is None:
        return
    reward_page.recognizer = any_of(self.I_GREED_GHOST, self.I_REWARD, self.I_REWARD_GOLD)
```

## Orochi 示例

```python
from tasks.Component.GeneralBattle.general_battle import BattleAction

def _register_custom_pages(self) -> None:
    reward_page = self.navigator.resolve_page(page_reward)
    if reward_page is not None:
        reward_page.recognizer = any_of(self.I_GREED_GHOST, self.I_REWARD, self.I_REWARD_GOLD)

def _handle_reward(
    self,
    context,
    config,
) -> BattleAction:
    if self.appear(self.I_GREED_GHOST):
        context.reward_no_battle_ts = None
        self.click(random.choice([self.C_REWARD_1, self.C_REWARD_2, self.C_REWARD_3]), interval=1.0)
        return BattleAction.CONTINUE
    return super()._handle_reward(context, config)
```
