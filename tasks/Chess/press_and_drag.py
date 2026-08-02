"""百鬼棋局专用的按住并拖动操作。"""

import time

import numpy as np

import module.device.method.scrcpy.const as scrcpy_const
from module.base.utils import (
    ensure_int,
    ensure_time,
    point2str,
    random_rectangle_point,
)
from module.device.method.minitouch import insert_swipe
from module.logger import logger


def Press_and_Drag(
    device,
    p1,
    p2,
    hold_duration=0.5,
    point_random=(-10, -10, 10, 10),
    swipe_duration=0.5,
    name='Press_and_Drag',
):
    """在起点按住后拖到终点；仅供 Chess 手牌、棋盘和御魂操作。"""
    device.handle_control_check(name)
    p1, p2 = ensure_int(p1, p2)
    action_log = 'Press_and_Drag %s -> %s' % (
        point2str(*p1),
        point2str(*p2),
    )
    method = device.config.script.device.control_method
    start = time.perf_counter()
    device._invalidate_image_batch_cache()

    if method == 'minitouch':
        _press_and_drag_minitouch(
            device,
            p1,
            p2,
            hold_duration=hold_duration,
            point_random=point_random,
        )
    elif method == 'uiautomator2':
        _press_and_drag_uiautomator2(
            device,
            p1,
            p2,
            hold_duration=hold_duration,
            point_random=point_random,
            swipe_duration=swipe_duration,
        )
    elif method == 'scrcpy':
        _press_and_drag_scrcpy(
            device,
            p1,
            p2,
            hold_duration=hold_duration,
            point_random=point_random,
        )
    else:
        logger.warning(
            f'Control method {method} cannot hold before moving; '
            'falling back to ADB swipe'
        )
        device.swipe_adb(
            p1,
            p2,
            duration=ensure_time(hold_duration + swipe_duration),
        )

    elapsed = time.perf_counter() - start
    logger.info(f'{device._format_action_duration(elapsed)}{action_log}')


def _randomized_points(p1, p2, point_random):
    p1 = np.array(p1) - random_rectangle_point(point_random)
    p2 = np.array(p2) - random_rectangle_point(point_random)
    return p1, p2


def _press_and_drag_minitouch(
    device,
    p1,
    p2,
    hold_duration,
    point_random,
):
    p1, p2 = _randomized_points(p1, p2, point_random)
    points = insert_swipe(p0=p1, p3=p2, speed=20)
    builder = device.minitouch_builder

    builder.down(*points[0]).commit().wait(int(hold_duration * 1000))
    device.minitouch_send()
    for point in points[1:]:
        builder.move(*point).commit().wait(10)
    device.minitouch_send()
    builder.move(*p2).commit().wait(140)
    builder.move(*p2).commit().wait(140)
    device.minitouch_send()
    builder.up().commit()
    device.minitouch_send()


def _press_and_drag_uiautomator2(
    device,
    p1,
    p2,
    hold_duration,
    point_random,
    swipe_duration,
):
    p1, p2 = _randomized_points(p1, p2, point_random)
    middle = (p1 + p2) // 2
    path = [
        (int(p1[0]), int(p1[1]), hold_duration),
        (int(middle[0]), int(middle[1]), swipe_duration / 2),
        (int(p2[0]), int(p2[1]), swipe_duration / 2),
        (int(p2[0]), int(p2[1]), 0),
    ]
    device._drag_along(path)


def _press_and_drag_scrcpy(
    device,
    p1,
    p2,
    hold_duration,
    point_random,
):
    device.scrcpy_ensure_running()
    with device._scrcpy_control_socket_lock:
        p1, p2 = _randomized_points(p1, p2, point_random)
        points = insert_swipe(p0=p1, p3=p2, speed=4, min_distance=2)
        device._scrcpy_control.touch(*p1, scrcpy_const.ACTION_DOWN)
        device.sleep(hold_duration)
        for point in points[1:-1]:
            device._scrcpy_control.touch(*point, scrcpy_const.ACTION_MOVE)
            device.sleep(0.002)
        device._scrcpy_control.touch(*p2, scrcpy_const.ACTION_MOVE)
        device.sleep(0.14)
        device._scrcpy_control.touch(*p2, scrcpy_const.ACTION_UP)
        device.sleep(0.05)
