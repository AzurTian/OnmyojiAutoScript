# 百鬼棋局开发说明

本文档以当前 `tasks/Chess` 实现为准，说明任务结构、各组件职责、运行流程以及新增阵容的方法。

## 1. 设计原则

百鬼棋局按“入口编排”和“具体能力”拆分：

- `script_task.py` 只负责任务、单局和单回目的流程编排。
- 识别、手牌操作、回合状态、商店经济分别由独立组件实现。
- 阵容配置只声明“使用哪些式神、放在哪些位置”，不复制通用流程。
- 图片阈值、超时和安全次数集中存放，不散落在主流程中。
- OASX 只提供用户配置，不能承载运行逻辑。

`ScriptTask` 通过 mixin 组合这些能力：

```text
ScriptTask
├─ ChessRecognitionMixin       阵容与图片识别
├─ ChessHandOperationsMixin    手牌、上阵、御魂和卖卡
├─ ChessRoundStateMixin        回目、模式、人数和资源 OCR
├─ ChessEconomyMixin           商店、购买、升级和刷新
├─ ChessRuntimeSettings        阈值、超时和运行常量
├─ GameUi                      页面导航
├─ GeneralBattle               通用战斗能力
└─ ChessAssets                 自动生成的图片、点击和 OCR 规则
```

## 2. 文件与目录职责

根目录仿照 SixRealms，仅保留任务入口、配置、自动生成资源和说明文档；
具体玩法能力与阵容数据分别收纳在子包中：

```text
Chess/
├─ script_task.py
├─ config.py
├─ assets.py
├─ README.md
├─ runtime/
│  ├─ recognition.py
│  ├─ hand_operations.py
│  ├─ round_state.py
│  ├─ economy.py
│  ├─ settings.py
│  ├─ board_positions.py
│  └─ press_and_drag.py
├─ strategy/
│  ├─ lineup.py
│  ├─ lineup_strategy.py
│  └─ shikigami_catalog.py
├─ c/
├─ shikigami/
└─ soul/
```

### `script_task.py`

百鬼棋局入口和状态机，只负责调用其他组件，不保存具体阵容名单。

公开流程按由大到小排列：

- `run()`：读取 OASX 配置、恢复中断对局、循环执行单局并处理任务结束条件。
- `run_one_game()`：开始一局、运行回目循环，并读取结算页的实际名次。
- `run_one_round()`：执行一个回目中的“备、战、鬼、待”和回目切换。

其余私有方法负责进入对局、等待回目、处理符咒、主动退出和返回大厅。

### `runtime/recognition.py`

集中处理阵容和模板识别：

- 解析 OASX 选择的阵容。
- 加载当前阵容的手牌与商店模板。
- 加载全式神手牌、全商店和御魂模板。
- 识别手牌类型。
- 对无法明确分类的卡做低阈值阵容保护，降低误卖概率。
- 将内部罗马音转换为中文日志。

切换阵容时会清除依赖阵容的模板缓存，避免沿用上一套阵容的素材规则。

### `runtime/hand_operations.py`

集中处理所有拖动和手牌动作：

- 上阵式神和确认上阵结果。
- 满员时回收系统自动上阵的式神，再重新截图定位手牌。
- 记录脚本亲自使用的站位，避免把自己的阵容当成系统卡回收。
- 发现御魂、发现纹章、普通御魂和守护之印的处理。
- 战阶段循环出售纹章与非阵容卡。

“发现纹章”必须由 OCR 完整识别四个字后进入发现卡流程，普通纹章出售
只匹配其余含“纹章”的卡，避免特殊卡在使用前被出售。
- 手牌满时先处理手牌御魂并重试购买；仍然满时再出售最右侧卡牌腾位。
- 误开式神详情页时关闭详情页。
- 读取固定站位坐标和场上勾玉检测区域。

手牌识别直接使用 `shikigami/card` 和 `soul` 中的图片模板，不再依赖手牌星级定位。

### `runtime/round_state.py`

集中处理回目状态和 OCR：

- 读取回目数，并兼容前三回目的第二套位置。
- 根据第一套或第二套布局读取 `chess_mode`。
- 读取金币、阶数、剩余时间和结算名次。
- 通过 12 个固定勾玉区域统计场上式神数量。
- 判断当前阶数允许的最大上阵人数。
- 处理符咒识别、评分、刷新和选择。

### `runtime/economy.py`

集中处理商店和经济原子操作：

- 判断商店开关状态，并在具体动作需要时开关商店。
- 扫描五个商店位置，只购买当前阵容的式神。
- 商店身份按“名字 OCR → 羁绊与价格 → 头像图片”依次识别。
- 价格框先匹配 `store_gold.png`，再 OCR 图标右侧的费用数字。
- 使用普通头像匹配和发光卡面作为最终兜底。
- 点击后以原商店头像消失确认购买成功。
- 手牌满导致购买失败时调用紧急腾位。
- 解析鼬乐币 OCR，并判断是否达到 `600/600`。
- 使用原子操作计数器执行购买经验和刷新。
- 每次刷新后立即重新扫描并购买阵容卡。

当前经济序列以阵容人数作为最终阶数：

| 当前阶数 | 原子操作循环 | 保留金币 |
|---|---|---:|
| 1–5 阶 | 升级一次、刷新一次 | 42 |
| 6–7 阶 | 升级一次、刷新一次 | 30 |
| 8 阶且未到最终阶数 | 升级一次、刷新两次 | 10 |
| 达到阵容最终阶数 | 持续刷新 | 0 |

例如九人阵容在九阶进入持续刷新；八人阵容在八阶进入持续刷新。

### `runtime/settings.py`

保存跨组件共用的运行参数：

- 手牌、商店、御魂和场上勾玉匹配阈值。
- 截图间隔、点击等待和超时。
- 上卡、卖卡和御魂处理的安全循环次数。
- 系统上阵候选位置。
- 御魂分类与中文名称。
- 当前阵容注册表和默认阵容。

调整识别门槛或等待时间时应优先修改这里，不要在业务方法中新增重复常量。

### `strategy/lineup_strategy.py`

只描述阵容本身。目前所有阵容都在该文件中声明：

- 稳定拼音键。
- OASX 中文显示名。
- 式神与固定站位。
- 梦山白藏主的守护之印目标位置。

`build_lineup_strategy()` 会把简洁配置转换为运行时标准结构。

### `strategy/lineup.py`

阵容注册中心：

- `LINEUP_REGISTRY` 保存全部可选阵容。
- `DEFAULT_LINEUP_KEY` 指定默认阵容。
- `LineupBond` 根据注册表自动生成 OASX 下拉枚举。
- `resolve_lineup_key()` 将拼音、中文或枚举统一转换为稳定拼音键。

### `strategy/soul_catalog.py`

维护御魂唯一的完整中文名、拼音、类型和图片名对照。运行时统一使用
拼音键；`resolve_soul()` 只接受完整中文名或拼音。

新增阵容后必须在这里注册，否则 OASX 不会显示，运行时也无法选择。

### `strategy/shikigami_catalog.py`

全式神唯一目录，维护三种等价索引：

```text
费用-编号 <-> 罗马音 <-> 中文名
```

运行时始终使用罗马音作为唯一键。目录同时生成标准素材路径：

```text
card/card_<romaji>.png
store/store_<romaji>.png
```

### `runtime/board_positions.py`

保存 1–12 号棋盘站位：

- `SET_POSITIONS`：上阵、下阵和御魂拖动目标坐标。
- `SET_JADE_AREAS`：各站位头顶勾玉标志的检测区域。

这些坐标不能放进 `assets.py`，因为后者会被资源生成工具覆盖。

### `runtime/press_and_drag.py`

Chess 专用长按拖动实现，兼容：

- minitouch
- uiautomator2
- scrcpy
- 其他控制方式的 ADB swipe 兜底

手牌上阵、下阵、御魂装配和卖卡统一调用该文件。

### `config.py`

定义 OASX 中的百鬼棋局配置：

| 配置 | 含义 |
|---|---|
| 选择阵容羁绊 | 从 `LINEUP_REGISTRY` 生成的中文下拉选项 |
| 保段位 | 上一局为前四名时，随后主动退出三局；退出局不计执行次数 |
| 执行次数 | 完成指定局数后结束；`-1` 表示无限循环 |
| 刷满鼬乐币 | 识别到 `600/600` 时结束任务 |

### `assets.py` 与 `c`

`assets.py` 由 `dev_tools/assets_extract.py` 根据 `c` 中的 JSON 和图片自动生成，禁止手动修改。

`c` 中的主要内容：

- `image.json`：图片识别规则。
- `click.json`：点击区域。
- `ocr.json`：OCR 区域与规则。
- 对局入口、商店、符咒、结算、主动退出等图片素材。
- `c_card_1.png` 至 `c_card_3.png`：场上式神勾玉标志模板。
- `c_hakuzosu_protect.png`：守护之印模板。

### `shikigami` 与 `soul`

```text
shikigami/
├─ shikigami_menu.txt
├─ card/card_<romaji>.png
└─ store/store_<romaji>.png

soul/
└─ sou_<pinyin>.png
```

- `card` 用于手牌识别和上阵。
- `store` 用于商店识别和购买。
- `soul` 用于御魂识别和装配；文件名拼音必须与目录完全一致。

## 3. 当前运行流程

### 3.1 任务级 `run()`

1. 读取阵容、执行次数、鼬乐币和保段位配置。
2. 如果启动时仍在上一局中，主动退出并完成返回大厅流程。
3. 导航到百鬼棋局大厅。
4. 开始新一局前检查鼬乐币是否已满。
5. 调用 `run_one_game()`。
6. 正常结束的局计入执行次数；保段位主动退出局不计数。
7. 满足次数或满币条件后结束任务。

### 3.2 单局 `run_one_game()`

1. 点击开始并等待阵容入口出现。
2. 重置单局状态：御魂满位、已确认阵容、脚本站位、经济计数器和商店状态。
3. 等待稳定回目数字。
4. 循环调用 `run_one_round()`，直至结算。
5. 阵容入口连续三帧消失后等待“对局结束”，OCR 读取实际名次。

### 3.3 单回目 `run_one_round()`

回目开始不再额外生成资源状态快照，直接按 `chess_mode` 执行：

- `备`
  1. 如果出现符咒面板，立即中断其他操作并完成符咒选择。
  2. 打开商店扫描一次并购买阵容卡。
  3. 执行升级/刷新原子循环；剩余时间不超过 15 秒时停止该循环。
  4. 关闭商店。
  5. 上阵式神。
  6. 装配御魂。
- `战`
  1. 每回目首次进入战阶段时，再执行一次升级/刷新循环。
  2. 循环出售纹章和非阵容卡。
  3. 等待战斗结束。
- `鬼`
  - 不砸式神，等待系统自动选择并结束百鬼夜行。
- `待`
  - 不执行操作，只等待状态变化。

回目数需要连续两帧发生相同变化才确认进入下一回目。`ROUND` 和 `CHESS_MODE` 连续三帧为空后会重新截图；只有阵容入口也不存在时才进入对局结束确认。等待结算页期间如果重新检测到阵容入口，会撤销误判、清零缺失帧计数并继续当前对局。

### 3.4 结算与主动退出

正常结算或主动退出后统一调用返回大厅流程：

1. 点击普通或主动退出对应的返回大厅按钮。
2. 必须等到分享页面出现。
3. 在安全区域持续点击，推动动画和弹窗。
4. 如果进入排名页，点击返回棋局大厅。
5. 检测到棋局大厅后才允许开始下一局。

## 4. 如何创建一个新阵容

下面以“新羁绊”为例。

### 第一步：确认式神目录

在 `strategy/shikigami_catalog.py` 中查找阵容需要的每个式神。可以使用：

```python
resolve_shikigami('中文名')
resolve_shikigami('费用-编号')
resolve_shikigami('romaji')
```

如果式神尚未登记，在 `SHIKIGAMI_ENTRIES` 中添加：

```python
ShikigamiEntry(费用, 编号, 'romaji', '中文名')
```

要求：

- 费用-编号不能重复。
- 罗马音不能重复。
- 中文名不能重复。
- 罗马音就是代码和图片的唯一索引，添加后不要随意改名。

### 第二步：准备图片素材

为每个式神准备：

```text
tasks/Chess/shikigami/card/card_<romaji>.png
tasks/Chess/shikigami/store/store_<romaji>.png
```

注意：

- 文件中的 `<romaji>` 必须与目录完全一致，包括大小写和下划线。
- 手牌模板用于上阵和保护阵容卡，必须提供。
- 会出现在商店中的式神必须提供商店模板，否则无法自动购买。
- 不会出现在商店中的赠送式神可以没有商店模板，但启动时会记录缺失素材警告。
- 模板应从实际 1280×720 游戏截图裁剪，尽量保留稳定的头部和服饰特征，避免价格、文字、发光边框和动态效果。

### 第三步：声明阵容

在 `strategy/lineup_strategy.py` 添加轻量配置：

```python
NEW_LINEUP_CONFIG = {
    'key': 'new_lineup',
    'display_name': '新羁绊',
    'shikigami_positions': {
        '式神甲': (1, 1, (), False),
        '式神乙': (1, 2, (), False),
        '3-6': (2, 3, (), False),
        'romaji_name': (2, 4, (), False),
    },
}

NEW_LINEUP = build_lineup_strategy(NEW_LINEUP_CONFIG)
```

式神可以用中文名、费用-编号或罗马音填写，构建后都会转换为罗马音。

站位要求：

- 位置范围为 1–12。
- 每个式神只登记一次。
- 通常每个位置只分配一个式神，避免互相覆盖。
- 阵容人数决定最终经济阶数。

每个式神还可以在站位后声明优先御魂：

```python
NEW_LINEUP_CONFIG = {
    'key': 'new_lineup',
    'display_name': '新羁绊',
    'shikigami_positions': {
        '梦山白藏主': 3,
        '式神甲': (1, 4, ('魍魉之匣', '地藏像'), '守护之印'),
    },
}
```

第一个数字是上阵权重，越小越优先；第二个数字是站位。同权重时仍按
手牌从左到右上阵。检测到魍魉之匣、地藏像或守护之印时，会优先装备
到式神甲的 4 号位。
御魂只可填写完整中文名或拼音，不再解析编号、`编号-御魂名` 或简称。
第四项单独控制守护之印，不会把守护之印视为普通御魂。
只要式神
声明了专属御魂，它就只接受列表中的御魂；通用输出/功能御魂会避开该
式神。未被阵容任何式神指定的普通御魂，继续按输出类后排、功能类前排
的通用规则装备。任一目标连续两次装备失败后会标记为御魂已满，本局
后续跳过该位置。

如果阵容会触发荒川羁绊召唤物金鱼，再声明金鱼的目标站位：

```python
NEW_LINEUP_CONFIG = {
    # ...
    'arakawa_goldfish_position': 12,
}
```

脚本在第二名荒川羁绊式神上阵后，按 `12 → 11 → 10 → 9`
的连续占位顺序逐格打开详情页；遇到首个空位即停止。详情页打开后
通过 `check_goldfish` 图片确认金鱼，再将其移动到这里配置的
位置。未填写时目标位置默认为 `12`。

### 第四步：注册阵容

在 `strategy/lineup.py` 导入策略对象，并加入 `LINEUP_REGISTRY`：

```python
from tasks.Chess.strategy.lineup_strategy import NEW_LINEUP


LINEUP_REGISTRY = {
    # 原有阵容……
    'new_lineup': {
        'display_name': '新羁绊',
        'strategy': NEW_LINEUP,
    },
}
```

注册键必须与配置中的 `key` 一致。完成后：

- `LineupBond` 会自动新增该中文选项。
- OASX 的“选择阵容羁绊”下拉框会显示“新羁绊”。
- 主程序会加载该阵容的手牌和商店素材。

### 第五步：检查配置

至少确认以下内容：

1. 每个式神都能通过中文、编号或罗马音解析。
2. 手牌素材文件全部存在。
3. 可购买式神的商店素材存在。
4. 阵容站位没有冲突。
5. 注册键与策略 `key` 一致。
6. OASX 下拉框能看到中文阵容名。
7. 实战日志能正确输出选中阵容、商店识别和上阵结果。

可使用下面的只读检查：

```powershell
python -c "from tasks.Chess.strategy.lineup import LINEUP_REGISTRY; print([(k, v['display_name'], list(v['strategy']['shikigami'])) for k, v in LINEUP_REGISTRY.items()])"
```

## 5. 修改功能时应放在哪里

| 修改内容 | 文件 |
|---|---|
| 新增阵容、调整式神站位 | `strategy/lineup_strategy.py` |
| 注册阵容和 OASX 下拉项 | `strategy/lineup.py` |
| 新增式神唯一索引 | `strategy/shikigami_catalog.py` |
| 手牌、上阵、御魂、卖卡 | `runtime/hand_operations.py` |
| 商店、购买、升级、刷新 | `runtime/economy.py` |
| 回目、模式、人数和资源 OCR | `runtime/round_state.py` |
| 整局、单局和回目流程顺序 | `script_task.py` |
| 阈值、间隔、超时、安全次数 | `runtime/settings.py` |
| 棋盘固定坐标 | `runtime/board_positions.py` |
| 图片、点击和 OCR 规则 | `c/*.json`，随后重新生成 `assets.py` |

不要直接修改自动生成的 `assets.py`，也不要把具体阵容名单重新硬编码进通用组件。
