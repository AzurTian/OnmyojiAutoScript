"""AutoCheckinBigGod 手动领取流程（纯 UI，不依赖 Frida）。

把"启动大神APP → 圈子 → 福利中心 → 领奖"的状态机拆出来，让 script_task.py 只负责
调度（Frida 路径 or 手动路径），导航逻辑集中在本文件。继承 PortraitUIMixin 复用竖屏
UI 原语（_init_portrait / _appear_then_click / _screenshot_safe / _launch_app_foreground /
_swipe / _cleanup_portrait），并通过 PortraitUIMixin -> BaseTask 链获得 appear/set_next_run 等。

福利中心新版 UI（2026-09 实机验证）要点：浮窗自动弹出（I_GIFT 仅兜底）；按钮领完
变粉不消失、成功只有 toast，重复点击无害（不区分颜色）。策略：每屏从上到下点一遍
（点过的 y 不重点）→ 点完上滑并清空记录 → 上滑后按钮位置不变即到底完成。所有动画
（弹窗/滚动/登录刷新）均自适应等稳定：按钮位置连续 STABLE_FRAMES 帧不变才操作，
详见下方常量注释。
"""
from typing import TYPE_CHECKING

from module.logger import logger
from module.base.timer import Timer
from module.exception import TaskEnd
from tasks.AutoCheckinBigGod.assets import AutoCheckinBigGodAssets as A
from tasks.AutoCheckinBigGod.portrait_ui import PortraitUIMixin

GL_PACKAGE = "com.netease.gl"

# 两次点击"领取"的最小间隔：等待 toast 消失、服务端处理，避免"操作太快了"被拒
CLAIM_COOLDOWN_SECONDS = 3
# 浮窗展开后连续这么久一个领取按钮都没出现 → 视为无可领取项，直接结束
EMPTY_SHEET_SECONDS = 15
# 见过按钮后持续这么久一个都匹配不到 → 才判定浮窗关闭/处理完
# （浮窗弹出动画、瞬时丢帧都会造成一两帧空白，不能只看一帧就结束）
NO_MATCH_SECONDS = 5
# 界面稳定判定：按钮 y 列表连续这么多帧完全一致（动画/滚动已结束）才开始操作。
# 帧间隔取决于截图速度（约0.3~1s），低配设备自动等更久
STABLE_FRAMES = 3
# 稳定等待的兜底上限：极端情况（如浮窗内容永远在动）超时后继续执行，防卡死
STABILIZE_MAX_SECONDS = 15
# 到底判定/位置比较时两个 y 列表视为一致的容差(px)
BOTTOM_TOLERANCE = 10
# 判断两个按钮 y 坐标是否为同一按钮的容差(px)
SAME_BUTTON_TOLERANCE = 40


class ManualClaimMixin(PortraitUIMixin):
    """手动领取流程混入类。继承 PortraitUIMixin 复用竖屏 UI 原语与 BaseTask 能力。
    宿主需提供 _check_adb_connection（ScriptTask 已有，依赖 ADB 实现）。"""

    if TYPE_CHECKING:
        # 宿主 ScriptTask 提供的 ADB 连接检查方法（实现在 script_task.py 中）。
        # 此处仅作类型声明，让 IDE 解析 self._check_adb_connection() 调用。
        def _check_adb_connection(self) -> bool: ...

    def _run_manual_claim(self):
        """纯UI手动领取：启动app→圈子→福利中心→逐个点领取→滑动到底。
        竖屏720x1280原生操作。截图走配置方法(nemu_ipc/adb/droidcast/scrcpy均返回原生
        竖屏)，点击/滑动走 adb input(绕开 minitouch/nemu_ipc 写死的1280x720横屏缩放)，
        从而与具体截图/控制方法无关。"""

        def start_stabilize():
            """进入"等待界面稳定"状态：浮窗弹出/登录刷新/上滑滚动后调用。"""
            nonlocal stabilizing, stable_frames, last_ys, stabilize_deadline
            stabilizing = True
            stable_frames = 0
            last_ys = None
            stabilize_deadline = Timer(STABILIZE_MAX_SECONDS).start()

        logger.hr('AutoCheckinBigGod (Manual)', level=1)

        if not self._check_adb_connection():
            logger.error('未检测到ADB设备，请确保模拟器已启动并已连接ADB')
            self.set_next_run('AutoCheckinBigGod', success=False, finish=True)
            raise TaskEnd('AutoCheckinBigGod')

        # 竖屏720x1280+orientation=0：跳过 check_screen_size(会反复调dumpsys) 与 check_screen_black
        self._init_portrait()

        logger.info('启动大神APP（前台）...')
        if not self._launch_app_foreground(GL_PACKAGE):
            logger.error('无法启动大神APP，请确保模拟器中已安装大神APP')
            self.set_next_run('AutoCheckinBigGod', success=False, finish=True)
            raise TaskEnd('AutoCheckinBigGod')

        # 总超时240s，count=3 容忍低性能设备单次截图耗时过长导致的误判（参考 Timer 文档）
        timeout = Timer(240, count=3).start()
        cooldown = None          # 点击"领取"后的冷却计时
        stabilizing = False      # 等待界面稳定中（浮窗弹出/滚动/刷新动画）
        stabilize_deadline = None
        stable_frames = 0
        last_ys = None           # 上一帧按钮 y 列表（稳定判定用）
        just_swiped = False      # 刚上滑过：稳定后的第一帧用于判断列表是否到底
        sheet_opened = False     # 是否已点过礼物浮窗入口（进页面会自动弹出，这是兜底标记）
        seen_buttons = False     # 本次运行是否见到过领取按钮
        prev_ys = None           # 上滑前按钮 y 列表（用于到底判定）
        clicked_ys = []          # 本屏已点击过的按钮 y 列表（上滑时清空）
        empty_timer = None       # 浮窗展开后一直无按钮的计时
        no_match_timer = None    # 见过按钮后持续无按钮的计时（防动画/丢帧误判完成）
        in_welfare = False       # 是否处于福利中心（检测刚进入，等浮窗自动弹出动画）
        claimed_any = False
        claimed = False
        while 1:
            self._screenshot_safe()

            # 1. 启动时的重新登录弹窗（如果有的话）
            if self._appear_then_click(A.I_LOGIN_AGAIN, interval=2):
                # 点击后页面会刷新，等界面稳定再操作
                start_stabilize()
                continue
            if self._appear_then_click(A.I_X, interval=2):
                continue
            # 2. 未登录提示（圈子页或福利中心点击领取后出现）
            if self._appear_then_click(A.I_LOGIN, interval=6):
                # 登录后页面/浮窗内容会刷新，等界面稳定再操作
                start_stabilize()
                continue

            # 3. 处于福利中心界面（顶部标题）
            if self.appear(A.I_CLAIM_S):
                if not in_welfare:
                    # 刚进入福利中心：浮窗会自动从下往上弹出，等它稳定再操作。
                    # 同时重置上一轮福利中心残留的状态
                    in_welfare = True
                    just_swiped = False
                    prev_ys = None
                    clicked_ys = []
                    empty_timer = None
                    no_match_timer = None
                    start_stabilize()
                    continue

                matches = A.I_CLAIM.match_all_any(self.device.image)
                matches.sort(key=lambda m: m[2])  # 按 y 从上到下
                ys = [m[2] for m in matches]

                # 界面稳定检测：动画/滚动期间按钮位置逐帧变化，连续 STABLE_FRAMES 帧不变
                # 才开始操作（自适应设备性能；超时兜底防永远等下去）
                if stabilizing:
                    if stabilize_deadline.reached():
                        logger.warning(f'等待界面稳定超时（{STABILIZE_MAX_SECONDS}s），继续执行')
                        stabilizing = False
                    elif ys and last_ys is not None and len(ys) == len(last_ys) \
                            and all(abs(a - b) <= BOTTOM_TOLERANCE for a, b in zip(ys, last_ys)):
                        stable_frames += 1
                        last_ys = ys
                        if stable_frames >= STABLE_FRAMES:
                            logger.info('界面已稳定，开始处理')
                            stabilizing = False
                    else:
                        stable_frames = 0
                        last_ys = ys
                    if stabilizing:
                        continue

                if matches:
                    seen_buttons = True
                    empty_timer = None
                    no_match_timer = None

                    # 上滑稳定后的第一帧：按钮位置与上滑前一致 → 列表到底，结束。
                    # prev_ys 在上滑后的稳定等待期间不更新，否则等于拿滑动后的帧和
                    # 自己比较，会误判"到底"提前退出（实测踩过）
                    if just_swiped:
                        if prev_ys is not None and len(ys) == len(prev_ys) \
                                and all(abs(a - b) <= BOTTOM_TOLERANCE for a, b in zip(ys, prev_ys)):
                            logger.info('礼物列表已到底，全部领取按钮处理完毕')
                            claimed = True
                            break
                        just_swiped = False
                    prev_ys = ys

                    # 点击冷却中：只截图观察，不点击（无 sleep）
                    if cooldown is not None and not cooldown.reached():
                        continue

                    # 点一个本屏还没点过的按钮（从上到下）。
                    # 已领取的粉色按钮也会被点一遍——用户确认无害、可接受。
                    target = None
                    for m in matches:
                        y = m[2]
                        if any(abs(y - cy) < SAME_BUTTON_TOLERANCE for cy in clicked_ys):
                            continue
                        target = m
                        break

                    if target is not None:
                        _, x, y, w, h = target
                        self._tap(x + w // 2, y + h // 2, name='I_CLAIM')
                        clicked_ys.append(y)
                        claimed_any = True
                        cooldown = Timer(CLAIM_COOLDOWN_SECONDS).start()
                    else:
                        # 本屏的按钮全部点过 → 上滑加载更多（跨屏允许重复点击，不做
                        # 滑动距离补偿推算：实测滑动距离不精确，推算会误跳过新按钮）
                        logger.info('本屏领取按钮已全部点击，上滑查看更多')
                        clicked_ys = []
                        just_swiped = True
                        start_stabilize()
                        self._swipe(360, 1050, 360, 450, 400)
                    continue

                # 没有任何领取按钮
                if not sheet_opened:
                    # 浮窗还没弹出（自动弹出失败）：点悬浮图标兜底
                    if self._appear_then_click(A.I_GIFT, interval=5):
                        logger.info('浮窗未自动弹出，点悬浮图标打开')
                        sheet_opened = True
                        start_stabilize()
                        continue
                    continue
                if not seen_buttons:
                    # 浮窗已展开但一直没有按钮 → 等一段时间后视为无可领取项
                    if empty_timer is None:
                        empty_timer = Timer(EMPTY_SHEET_SECONDS).start()
                    elif empty_timer.reached():
                        logger.info('礼物浮窗内无可领取项')
                        claimed = True
                        break
                    continue
                # 见过按钮但现在没了：浮窗被关闭/页面切换等。动画或瞬时丢帧也会造成
                # 一两帧空白（实测踩过：上滑动画中一帧空白就提前结束），所以要求
                # 持续 NO_MATCH_SECONDS 都没有按钮才判定完成
                if no_match_timer is None:
                    no_match_timer = Timer(NO_MATCH_SECONDS).start()
                    continue
                if not no_match_timer.reached():
                    continue
                # 浮窗是进页面时自动打开的（sheet_opened=False）：持续无按钮可能是
                # 浮窗意外关闭，用悬浮图标兜底重开一次（防意外）
                if not sheet_opened and self._appear_then_click(A.I_GIFT, interval=5):
                    logger.info('浮窗疑似意外关闭，重新打开')
                    sheet_opened = True
                    no_match_timer = None
                    start_stabilize()
                    continue
                logger.info('福利中心持续无领取按钮，领取完成')
                claimed = True
                break

            # 不在福利中心
            in_welfare = False

            # 4. 在圈子页：进福利中心
            if self.appear(A.I_CIRCLE_CHECK):
                self._appear_then_click(A.I_WELFARE, interval=2)
                continue
            # 5. 不在圈子：进圈子
            if self._appear_then_click(A.I_CIRCLE, interval=4):
                continue
            # 超时保护
            if timeout.reached():
                break

        self._cleanup_portrait()
        if claimed:
            if claimed_any:
                logger.info('手动领取完成（有点击领取按钮）')
            else:
                logger.info('手动领取完成（无未领取项）')
            self.set_next_run('AutoCheckinBigGod', success=True, finish=True)
        else:
            logger.warning('手动领取超时未完成')
            self.set_next_run('AutoCheckinBigGod', success=False, finish=True)
        raise TaskEnd('AutoCheckinBigGod')
