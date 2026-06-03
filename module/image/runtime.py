# This Python file uses the following encoding: utf-8
from __future__ import annotations

import os
import pickle
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np
from numpy import fromfile, uint8

from module.base.utils import is_approx_rectangle
from module.logger import logger


@dataclass(slots=True)
class ImageServerSettings:
    """图像服务运行时配置，统一描述缓存 TTL、容量和 worker 数量。"""

    frame_cache_expire_seconds: float = 3.0
    frame_cache_max_count: int = 24
    template_cache_expire_seconds: int = 3600
    template_cache_max_count: int = 200
    worker_count: int = 0
    cleanup_interval_seconds: float = 60.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ImageServerSettings":
        """
        从配置字典构造运行时设置对象。

        缺失字段会回退到默认值，便于部署配置按需覆盖少数字段。
        """
        if not data:
            return cls()
        return cls(
            frame_cache_expire_seconds=float(data.get("frame_cache_expire_seconds", 3.0)),
            frame_cache_max_count=int(data.get("frame_cache_max_count", 24)),
            template_cache_expire_seconds=int(data.get("template_cache_expire_seconds", 3600)),
            template_cache_max_count=int(data.get("template_cache_max_count", 200)),
            worker_count=int(data.get("worker_count", 0)),
            cleanup_interval_seconds=float(data.get("cleanup_interval_seconds", 60.0)),
        )


@dataclass(slots=True)
class FrameEntry:
    """单张已注册截图在服务端缓存中的条目。"""

    frame_id: str
    config_name: str
    image: np.ndarray
    created_at: float
    last_access_at: float

    @property
    def shape(self) -> tuple[int, ...]:
        """返回截图数组的形状，便于 RPC 层输出元信息。"""
        return tuple(int(v) for v in self.image.shape)


@dataclass(slots=True)
class TemplateEntry:
    """模板缓存条目，保存模板图像及其派生匹配数据。"""

    template_key: str
    file_path: str
    fingerprint: str
    image_rgb: np.ndarray
    image_gray: np.ndarray
    loaded_at: float
    last_access_at: float
    sift_kp: Any = None
    sift_des: np.ndarray | None = None

    @property
    def shape(self) -> tuple[int, ...]:
        """返回模板图像的形状，便于调试与预热接口返回。"""
        return tuple(int(v) for v in self.image_rgb.shape)


class ImageTaskScheduler:
    """图像服务内部的轻量任务调度器，负责统一提交批量匹配任务。"""

    def __init__(self, worker_count: int = 0) -> None:
        """
        Args:
            worker_count: 显式指定 worker 数量；为 0 时按 CPU 核数自动推导，且最少为 1。
        """
        self.worker_count = max(1, worker_count or (os.cpu_count() or 1))
        self._executor = ThreadPoolExecutor(
            max_workers=self.worker_count,
            thread_name_prefix="image_worker",
        )
        self._pending_lock = threading.Lock()
        self._pending = 0

    def submit(self, func: Callable[..., Any], *args, **kwargs):
        """提交一个后台匹配任务，并维护待执行计数。"""
        with self._pending_lock:
            self._pending += 1
        future = self._executor.submit(func, *args, **kwargs)
        future.add_done_callback(self._on_done)
        return future

    def stats(self) -> dict[str, int]:
        """返回当前 worker 数量与待完成任务数。"""
        with self._pending_lock:
            pending = self._pending
        return {
            "worker_count": self.worker_count,
            "pending": pending,
        }

    def shutdown(self) -> None:
        """关闭线程池，并取消尚未开始执行的后台任务。"""
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _on_done(self, _future) -> None:
        """在任务结束后回收 pending 计数，避免状态持续增长。"""
        with self._pending_lock:
            self._pending = max(0, self._pending - 1)


class ImageRuntime:
    """图像服务运行时主体，统一管理缓存、调度器和各类匹配 RPC。"""

    def __init__(self, settings: dict[str, Any] | ImageServerSettings | None = None) -> None:
        """
        Args:
            settings: 允许传入字典或 `ImageServerSettings`；为空时使用默认缓存与调度配置。
        """
        if isinstance(settings, ImageServerSettings):
            self.settings = settings
        else:
            self.settings = ImageServerSettings.from_dict(settings)

        self._lock = threading.RLock()
        # 短生命周期截图缓存：按 frame_id 复用同一张截图的多次匹配请求。
        self._frames: dict[str, FrameEntry] = {}
        # 每个脚本配置当前有效的截图帧；新截图注册时会替换同配置旧帧。
        self._config_frames: dict[str, str] = {}
        # 长生命周期模板缓存：按文件指纹复用模板图与派生数据。
        self._templates: dict[str, TemplateEntry] = {}
        self._scheduler = ImageTaskScheduler(self.settings.worker_count)
        self._sift = None
        # 运行时诊断统计，仅用于调试缓存命中、失效和淘汰情况。
        self._cache_stats = {
            "frame_hits": 0,
            "frame_misses": 0,
            "frame_evictions": 0,
            "frame_replacements": 0,
            "template_hits": 0,
            "template_misses": 0,
            "template_evictions": 0,
            "template_expired": 0,
        }
        self._stop_event = threading.Event()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            name="image_cache_cleanup",
            daemon=True,
        )
        self._cleanup_thread.start()
        logger.info(
            "Image runtime initialized "
            f"(frame_ttl={self.settings.frame_cache_expire_seconds}s, "
            f"frame_max={self.settings.frame_cache_max_count}, "
            f"template_ttl={self.settings.template_cache_expire_seconds}s, "
            f"template_max={self.settings.template_cache_max_count}, "
            f"workers={self._scheduler.worker_count})"
        )

    def ping(self) -> bool:
        """供 RPC 客户端做健康检查的轻量探针。"""
        return True

    def get_server_info(self) -> dict[str, Any]:
        """返回当前缓存配置、缓存计数、调度器状态和命中统计。"""
        with self._lock:
            frame_count = len(self._frames)
            frame_config_count = len(self._config_frames)
            template_count = len(self._templates)
            cache_stats = dict(self._cache_stats)
        return {
            "frame_cache_expire_seconds": self.settings.frame_cache_expire_seconds,
            "frame_cache_max_count": self.settings.frame_cache_max_count,
            "frame_cache_count": frame_count,
            "frame_config_count": frame_config_count,
            "template_cache_expire_seconds": self.settings.template_cache_expire_seconds,
            "template_cache_max_count": self.settings.template_cache_max_count,
            "template_cache_count": template_count,
            "scheduler": self._scheduler.stats(),
            "cache_stats": cache_stats,
        }

    def register_frame(self, image_bytes: bytes, config_name: str = "unknown") -> dict[str, Any]:
        """
        注册一张截图到帧缓存，并返回服务端生成的 `frame_id`。

        Args:
            image_bytes: 客户端序列化后的 numpy 数组字节流。
            config_name: 截图所属脚本配置名；同配置新帧会替换旧帧。
        """
        image = pickle.loads(image_bytes)
        if not isinstance(image, np.ndarray):
            raise TypeError("register_frame expects numpy.ndarray payload")

        config_name = self._normalize_config_name(config_name)
        frame_id = uuid.uuid4().hex
        now = time.time()
        entry = FrameEntry(
            frame_id=frame_id,
            config_name=config_name,
            image=image,
            created_at=now,
            last_access_at=now,
        )
        with self._lock:
            old_frame_id = self._config_frames.get(config_name)
            if old_frame_id is not None and old_frame_id != frame_id:
                if self._delete_frame(old_frame_id):
                    self._cache_stats["frame_replacements"] += 1
            self._frames[frame_id] = entry
            self._config_frames[config_name] = frame_id
            self._cleanup_frames(now, reason="register")
        logger.debug(f"Register frame {frame_id} config={config_name} shape={entry.shape}")
        return {
            "frame_id": frame_id,
            "config_name": config_name,
            "shape": list(entry.shape),
        }

    def get_frame_info(self, frame_id: str) -> dict[str, Any]:
        """查询指定截图帧的缓存元信息，并刷新其最近访问时间。"""
        entry = self._get_frame_entry(frame_id)
        return {
            "frame_id": entry.frame_id,
            "config_name": entry.config_name,
            "shape": list(entry.shape),
            "created_at": entry.created_at,
            "last_access_at": entry.last_access_at,
        }

    def prepare_template(self, template_path: str, include_sift: bool = False) -> dict[str, Any]:
        """
        预加载模板缓存，并按需准备 SIFT 特征。

        Args:
            template_path: 模板文件绝对路径。
            include_sift: 为真时立即计算 SIFT keypoints/descriptor，减少首次匹配开销。
        """
        entry = self._get_template_entry(template_path)
        sift_ready = False
        descriptor_shape = None
        if include_sift:
            entry = self._ensure_template_sift(entry)
            sift_ready = True
            if entry.sift_des is not None:
                descriptor_shape = list(entry.sift_des.shape)
        return {
            "template_key": entry.template_key,
            "file_path": entry.file_path,
            "fingerprint": entry.fingerprint,
            "shape": list(entry.shape),
            "sift_ready": sift_ready,
            "descriptor_shape": descriptor_shape,
        }

    def match_rule(
        self,
        rule_data: dict[str, Any],
        frame_id: str | None = None,
        image_bytes: bytes | None = None,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        """
        执行单个规则匹配。

        Args:
            rule_data: 规则描述字典，至少包含方法、模板路径、阈值和 ROI 信息。
            frame_id: 已注册截图的引用；提供后优先从帧缓存取图。
            image_bytes: 直接上传的截图字节流；仅在没有 `frame_id` 时使用。
            threshold: 对规则默认阈值的临时覆盖值。
        """
        image = self._resolve_image(frame_id=frame_id, image_bytes=image_bytes)
        return self._match_rule_payload(image=image, rule_data=rule_data, threshold=threshold)

    def match_rule_with_brightness_window(
        self,
        rule_data: dict[str, Any],
        frame_id: str | None = None,
        image_bytes: bytes | None = None,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        """
        执行带亮度窗口约束的模板匹配。

        该接口仅支持普通模板匹配，会在模板命中后再比较源区域与模板区域的平均亮度。
        """
        image = self._resolve_image(frame_id=frame_id, image_bytes=image_bytes)
        rule = self._normalize_rule(rule_data=rule_data, threshold=threshold)
        if rule["method"] != "Template matching":
            raise ValueError("match_rule_with_brightness_window only supports Template matching")
        entry = self._get_template_entry(rule["file"])
        matched, score, roi_front = self._template_match_image(
            image=image,
            template=entry.image_rgb,
            roi_back=rule["roi_back"],
            threshold=rule["threshold"],
            log_name=rule["name"],
        )
        if not matched or roi_front is None:
            return {
                "matched": False,
                "score": score,
                "roi_front": None,
            }

        x, y, w, h = roi_front
        region = image[y:y + h, x:x + w]
        brightness_src = self._mean_brightness(region)
        brightness_template = self._mean_brightness(entry.image_rgb)
        lower = brightness_template * rule["threshold"]
        upper = brightness_template * (2 - rule["threshold"])
        brightness_matched = lower <= brightness_src <= upper
        return {
            "matched": brightness_matched,
            "score": score,
            "roi_front": roi_front if brightness_matched else None,
        }

    def match_many(
        self,
        rules_data: list[dict[str, Any]],
        frame_id: str | None = None,
        image_bytes: bytes | None = None,
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        在同一张截图上并发执行多个单规则匹配。

        该接口会复用同一个输入图像，并交给调度器统一提交后台任务。
        """
        image = self._resolve_image(frame_id=frame_id, image_bytes=image_bytes)
        futures = [
            self._scheduler.submit(
                self._match_rule_payload,
                image,
                rule_data,
                threshold,
            )
            for rule_data in rules_data
        ]
        return [future.result() for future in futures]

    def match_all(
        self,
        rule_data: dict[str, Any],
        frame_id: str | None = None,
        image_bytes: bytes | None = None,
        threshold: float | None = None,
        roi: list[int] | None = None,
    ) -> dict[str, Any]:
        """
        返回某个模板规则在当前截图上的全部命中结果。

        Args:
            roi: 搜索区域覆盖值；为空时沿用规则中已有的 `roi_back`。
        """
        image = self._resolve_image(frame_id=frame_id, image_bytes=image_bytes)
        rule = self._normalize_rule(rule_data=rule_data, threshold=threshold, roi=roi)
        matches = self._match_all_template(image=image, rule=rule)
        return {"matches": [list(item) for item in matches]}

    def match_all_any(
        self,
        rule_data: dict[str, Any],
        frame_id: str | None = None,
        image_bytes: bytes | None = None,
        threshold: float | None = None,
        roi: list[int] | None = None,
        nms_threshold: float = 0.3,
    ) -> dict[str, Any]:
        """
        返回经 NMS 去重后的全部命中结果。

        Args:
            nms_threshold: 非极大值抑制阈值，用于过滤高度重叠的冗余匹配框。
        """
        image = self._resolve_image(frame_id=frame_id, image_bytes=image_bytes)
        rule = self._normalize_rule(rule_data=rule_data, threshold=threshold, roi=roi)
        matches = self._match_all_any_template(image=image, rule=rule, nms_threshold=nms_threshold)
        return {"matches": [list(item) for item in matches]}

    def match_all_any_many(
        self,
        rules_data: list[dict[str, Any]],
        frame_id: str | None = None,
        image_bytes: bytes | None = None,
        threshold: float | None = None,
        nms_threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        """在同一帧上并发执行多组“全量匹配 + NMS 去重”请求。"""
        image = self._resolve_image(frame_id=frame_id, image_bytes=image_bytes)
        futures = [
            self._scheduler.submit(
                self._match_all_any_payload,
                image,
                rule_data,
                threshold,
                nms_threshold,
            )
            for rule_data in rules_data
        ]
        return [future.result() for future in futures]

    def match_dynamic_template(
        self,
        template_bytes: bytes,
        frame_id: str | None = None,
        image_bytes: bytes | None = None,
        roi_back: list[int] | None = None,
        threshold: float = 0.75,
        name: str = "RuleAnimate",
    ) -> dict[str, Any]:
        """
        使用动态生成的小模板在当前截图上执行一次匹配。

        Args:
            template_bytes: 序列化后的模板数组，通常来自上一帧局部区域。
            frame_id: 当前截图的服务端引用；存在时优先复用。
            image_bytes: 未注册截图时直接上传的图像字节流。
            roi_back: 在当前截图上的搜索区域；为空时默认搜索整张图。
            threshold: 动态模板匹配阈值。
            name: 用于日志中的匹配名称。
        """
        image = self._resolve_image(frame_id=frame_id, image_bytes=image_bytes)
        template = pickle.loads(template_bytes)
        if not isinstance(template, np.ndarray):
            raise TypeError("match_dynamic_template expects numpy.ndarray template")
        roi = list(roi_back) if roi_back is not None else [0, 0, image.shape[1], image.shape[0]]
        matched, score, roi_front = self._template_match_image(
            image=image,
            template=template,
            roi_back=roi,
            threshold=float(threshold),
            log_name=name,
        )
        return {
            "matched": matched,
            "score": score,
            "roi_front": roi_front,
        }

    def shutdown(self) -> bool:
        """停止后台清理与调度器，供服务退出阶段调用。"""
        self._stop_event.set()
        self._scheduler.shutdown()
        return True

    def _cleanup_loop(self) -> None:
        """按固定间隔后台清理过期截图帧和模板缓存。"""
        while not self._stop_event.wait(self.settings.cleanup_interval_seconds):
            now = time.time()
            with self._lock:
                self._cleanup_frames(now, reason="timer")
                self._cleanup_templates(now, reason="timer")

    @staticmethod
    def _normalize_config_name(config_name: str | None) -> str:
        """规整脚本配置名，避免空配置名导致帧索引不可复用。"""
        normalized = str(config_name or "").strip()
        return normalized or "unknown"

    def _delete_frame(self, frame_id: str) -> bool:
        """删除指定截图帧，并同步维护 config_name 到当前 frame_id 的索引。"""
        entry = self._frames.pop(frame_id, None)
        if entry is None:
            return False

        if self._config_frames.get(entry.config_name) == frame_id:
            self._config_frames.pop(entry.config_name, None)
        self._cache_stats["frame_evictions"] += 1
        return True

    def _get_frame_entry(self, frame_id: str) -> FrameEntry:
        """
        从帧缓存中取出指定截图，并维护命中统计与最近访问时间。

        当帧已过期或不存在时会抛出 `KeyError`，由上层决定如何处理无效 `frame_id`。
        """
        now = time.time()
        with self._lock:
            self._cleanup_frames(now, reason="lookup")
            entry = self._frames.get(frame_id)
            if entry is None:
                self._cache_stats["frame_misses"] += 1
                raise KeyError(f"Unknown frame id: {frame_id}")
            entry.last_access_at = now
            self._cache_stats["frame_hits"] += 1
            return entry

    def _get_template_entry(self, template_path: str) -> TemplateEntry:
        """
        按模板路径和文件指纹获取模板缓存条目。

        若缓存未命中，会重新加载模板图像并生成新的缓存键，确保模板文件更新后不会复用旧内容。
        """
        normalized_path = str(Path(template_path).resolve())
        fingerprint = self._build_template_fingerprint(normalized_path)
        template_key = f"{normalized_path}|{fingerprint}"
        now = time.time()

        with self._lock:
            self._cleanup_templates(now, reason="lookup")
            entry = self._templates.get(template_key)
            if entry is not None:
                entry.last_access_at = now
                self._cache_stats["template_hits"] += 1
                return entry

        self._cache_stats["template_misses"] += 1
        image_rgb = self._load_template_image(normalized_path)
        image_gray = self._to_gray(image_rgb)
        entry = TemplateEntry(
            template_key=template_key,
            file_path=normalized_path,
            fingerprint=fingerprint,
            image_rgb=image_rgb,
            image_gray=image_gray,
            loaded_at=now,
            last_access_at=now,
        )

        with self._lock:
            self._templates[template_key] = entry
            self._cleanup_templates(now, reason="register")
        logger.debug(f"Load template {normalized_path} fingerprint={fingerprint}")
        return entry

    def _resolve_image(self, frame_id: str | None, image_bytes: bytes | None) -> np.ndarray:
        """
        统一解析一次匹配请求使用的输入图像。

        `frame_id` 与 `image_bytes` 二选一：优先复用已注册截图，只有在没有 `frame_id`
        时才会反序列化请求中直接上传的图像数据。
        """
        if frame_id:
            return self._get_frame_entry(frame_id).image
        if image_bytes is None:
            raise ValueError("Either frame_id or image_bytes must be provided")
        image = pickle.loads(image_bytes)
        if not isinstance(image, np.ndarray):
            raise TypeError("image payload must be numpy.ndarray")
        return image

    def _normalize_rule(
        self,
        rule_data: dict[str, Any],
        threshold: float | None = None,
        roi: list[int] | None = None,
    ) -> dict[str, Any]:
        """
        将 RPC 传入的规则描述规整为运行时统一使用的内部结构。

        Args:
            threshold: 可选的阈值覆盖值；为空时沿用 `rule_data` 中的阈值。
            roi: 可选的搜索区域覆盖值；为空时沿用 `rule_data` 中的 `roi_back`。
        """
        active_threshold = float(rule_data.get("threshold", 0.0) if threshold is None else threshold)
        roi_front = [int(v) for v in rule_data.get("roi_front", [0, 0, 0, 0])]
        roi_back = [int(v) for v in (roi if roi is not None else rule_data.get("roi_back", [0, 0, 0, 0]))]
        scale_range = rule_data.get("scale_range")
        if scale_range is not None:
            scale_range = tuple(float(v) for v in scale_range)
        return {
            "name": str(rule_data.get("name", "RuleImage")),
            "file": str(rule_data.get("file", "")),
            "method": str(rule_data.get("method", "Template matching")),
            "threshold": active_threshold,
            "roi_front": roi_front,
            "roi_back": roi_back,
            "scale_range": scale_range,
            "scale_step": float(rule_data.get("scale_step", 0.1)),
        }

    def _match_rule_payload(
        self,
        image: np.ndarray,
        rule_data: dict[str, Any],
        threshold: float | None = None,
    ) -> dict[str, Any]:
        """执行单规则匹配并把结果转换为可直接返回给 RPC 层的字典。"""
        rule = self._normalize_rule(rule_data=rule_data, threshold=threshold)
        matched, score, roi_front = self._match_rule(image=image, rule=rule)
        return {
            "matched": matched,
            "score": score,
            "roi_front": roi_front,
        }

    def _match_all_any_payload(
        self,
        image: np.ndarray,
        rule_data: dict[str, Any],
        threshold: float | None = None,
        nms_threshold: float = 0.3,
    ) -> dict[str, Any]:
        """执行单规则“全量匹配 + NMS 去重”并包装 RPC 返回值。"""
        rule = self._normalize_rule(rule_data=rule_data, threshold=threshold)
        matches = self._match_all_any_template(image=image, rule=rule, nms_threshold=nms_threshold)
        return {"matches": [list(item) for item in matches]}

    def _match_rule(self, image: np.ndarray, rule: dict[str, Any]) -> tuple[bool, float, list[int] | None]:
        """按规则声明的 method 分派到具体匹配实现。"""
        method = rule["method"]
        if method == "Template matching":
            template = self._get_template_entry(rule["file"]).image_rgb
            return self._template_match_image(
                image=image,
                template=template,
                roi_back=rule["roi_back"],
                threshold=rule["threshold"],
                log_name=rule["name"],
            )
        if method == "Multi-scale template matching":
            template = self._get_template_entry(rule["file"]).image_rgb
            return self._multi_scale_template_match(
                image=image,
                template=template,
                roi_back=rule["roi_back"],
                threshold=rule["threshold"],
                scale_range=rule["scale_range"],
                scale_step=rule["scale_step"],
                log_name=rule["name"],
            )
        if method == "Sift Flann":
            entry = self._ensure_template_sift(self._get_template_entry(rule["file"]))
            return self._sift_match(
                image=image,
                template_entry=entry,
                roi_front=rule["roi_front"],
                roi_back=rule["roi_back"],
                log_name=rule["name"],
            )
        raise ValueError(f"unknown method {method}")

    @staticmethod
    def _crop(image: np.ndarray, roi: list[int]) -> np.ndarray:
        """按 `[x, y, w, h]` 形式的 ROI 从图像中裁出子区域。"""
        x, y, w, h = [int(v) for v in roi]
        return image[y:y + h, x:x + w]

    @staticmethod
    def _template_image_invalid(mat: np.ndarray) -> bool:
        """检查模板图是否为空或尺寸非法，避免参与 OpenCV 匹配。"""
        return mat is None or mat.shape[0] == 0 or mat.shape[1] == 0

    @staticmethod
    def _mean_brightness(image: np.ndarray) -> float:
        """计算图像区域的平均亮度，用于亮度窗口匹配。"""
        if image.size == 0:
            return 0.0
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return float(gray.mean())

    def _template_match_image(
        self,
        image: np.ndarray,
        template: np.ndarray,
        roi_back: list[int],
        threshold: float,
        log_name: str,
    ) -> tuple[bool, float, list[int] | None]:
        """
        执行普通模板匹配，并在命中时回传前景 ROI。

        `roi_back` 表示在原图上的搜索区域，命中结果会被换算回原图坐标系。
        """
        source = self._crop(image, roi_back)
        if self._template_image_invalid(template):
            logger.error(f"Template image is invalid: {None if template is None else template.shape}")
            return True, 1.0, [int(v) for v in roi_back]
        if source.shape[0] < template.shape[0] or source.shape[1] < template.shape[1]:
            return False, -1.0, None
        result = cv2.matchTemplate(source, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        roi_front = None
        matched = max_val > threshold
        if matched:
            roi_front = [
                int(max_loc[0] + roi_back[0]),
                int(max_loc[1] + roi_back[1]),
                int(template.shape[1]),
                int(template.shape[0]),
            ]
        logger.debug(f"{log_name} template score={max_val:.5f}")
        return matched, float(max_val), roi_front

    def _multi_scale_template_match(
        self,
        image: np.ndarray,
        template: np.ndarray,
        roi_back: list[int],
        threshold: float,
        scale_range: tuple[float, ...] | None,
        scale_step: float,
        log_name: str,
    ) -> tuple[bool, float, list[int] | None]:
        """
        在给定缩放范围内搜索最优模板匹配结果。

        缩放步长与范围来自规则配置，最终返回最佳得分对应的位置与尺寸。
        """
        source = self._crop(image, roi_back)
        if self._template_image_invalid(template):
            logger.error(f"Template image is invalid: {None if template is None else template.shape}")
            return True, 1.0, [int(v) for v in roi_back]

        min_scale, max_scale, step = self._get_multi_scale_range(scale_range, scale_step)
        best_val = -1.0
        best_loc = None
        best_shape = None
        current_scale = min_scale
        while current_scale <= max_scale + 1e-8:
            scaled_w = max(1, int(template.shape[1] * current_scale))
            scaled_h = max(1, int(template.shape[0] * current_scale))
            if scaled_w > source.shape[1] or scaled_h > source.shape[0]:
                current_scale += step
                continue
            scaled_template = cv2.resize(template, (scaled_w, scaled_h), interpolation=cv2.INTER_LINEAR)
            result = cv2.matchTemplate(source, scaled_template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val > best_val:
                best_val = max_val
                best_loc = max_loc
                best_shape = (scaled_w, scaled_h)
            current_scale += step

        roi_front = None
        matched = best_loc is not None and best_shape is not None and best_val > threshold
        if matched:
            roi_front = [
                int(best_loc[0] + roi_back[0]),
                int(best_loc[1] + roi_back[1]),
                int(best_shape[0]),
                int(best_shape[1]),
            ]
        logger.debug(f"{log_name} multi-scale score={best_val:.5f}")
        return matched, float(best_val), roi_front

    @staticmethod
    def _get_multi_scale_range(
        scale_range: tuple[float, ...] | None,
        scale_step: float,
    ) -> tuple[float, float, float]:
        """把多尺度配置规整为 `(min_scale, max_scale, step)` 三元组。"""
        if scale_range is None:
            min_scale, max_scale = 0.6, 1.2
            step = 0.1
        elif len(scale_range) == 3:
            min_scale, max_scale, step = scale_range
        else:
            min_scale, max_scale = scale_range
            step = scale_step
        if min_scale > max_scale:
            min_scale, max_scale = max_scale, min_scale
        if step <= 0:
            step = 0.1
        return float(min_scale), float(max_scale), float(step)

    def _sift_match(
        self,
        image: np.ndarray,
        template_entry: TemplateEntry,
        roi_front: list[int],
        roi_back: list[int],
        log_name: str,
    ) -> tuple[bool, float, list[int] | None]:
        """
        执行 SIFT/FLANN 特征匹配，并在命中时返回估算出的前景区域。

        `roi_front` 提供模板原始尺寸，用于透视变换后恢复目标区域大小。
        """
        source = self._crop(image, roi_back)
        kp, des = self._get_sift().detectAndCompute(source, None)
        if des is None or template_entry.sift_des is None or kp is None:
            return False, 0.0, None

        index_params = dict(algorithm=1, trees=5)
        search_params = dict(checks=50)
        flann = cv2.FlannBasedMatcher(index_params, search_params)
        try:
            matches = flann.knnMatch(template_entry.sift_des, des, k=2)
        except cv2.error:
            return False, 0.0, None

        good = []
        for pair in matches:
            if len(pair) < 2:
                continue
            first, second = pair
            if first.distance < 0.6 * second.distance:
                good.append(first)
        if len(good) < 10:
            logger.debug(f"{log_name} sift good_matches={len(good)}")
            return False, float(len(good)), None

        src_pts = np.float32([template_entry.sift_kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        matrix, _mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if matrix is None:
            return False, float(len(good)), None

        width, height = int(roi_front[2]), int(roi_front[3])
        points = np.float32([[0, 0], [0, height - 1], [width - 1, height - 1], [width - 1, 0]]).reshape(-1, 1, 2)
        transformed = np.int32(cv2.perspectiveTransform(points, matrix))
        if not is_approx_rectangle(np.array([pos[0] for pos in transformed])):
            return False, float(len(good)), None

        result_roi = [
            int(transformed[0, 0, 0] + roi_back[0]),
            int(transformed[0, 0, 1] + roi_back[1]),
            width,
            height,
        ]
        logger.debug(f"{log_name} sift good_matches={len(good)}")
        return True, float(len(good)), result_roi

    def _get_sift(self):
        """延迟创建全局复用的 SIFT 实例，避免重复初始化。"""
        if self._sift is None:
            self._sift = cv2.SIFT_create()
        return self._sift

    def _match_all_template(self, image: np.ndarray, rule: dict[str, Any]) -> list[tuple[float, int, int, int, int]]:
        """
        返回普通模板匹配的全部命中列表。

        返回项格式为 `(score, x, y, w, h)`，坐标始终换算到原图坐标系。
        """
        if rule["method"] != "Template matching":
            raise ValueError(f"unknown method {rule['method']}")
        template = self._get_template_entry(rule["file"]).image_rgb
        source = self._crop(image, rule["roi_back"])
        if self._template_image_invalid(template):
            logger.error(f"Template image is invalid: {None if template is None else template.shape}")
            return []
        if source.shape[0] < template.shape[0] or source.shape[1] < template.shape[1]:
            return []
        results = cv2.matchTemplate(source, template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(results >= rule["threshold"])
        matches = []
        for point in zip(*locations[::-1]):
            score = float(results[point[1], point[0]])
            x = int(rule["roi_back"][0] + point[0])
            y = int(rule["roi_back"][1] + point[1])
            matches.append((score, x, y, int(template.shape[1]), int(template.shape[0])))
        return matches

    def _match_all_any_template(
        self,
        image: np.ndarray,
        rule: dict[str, Any],
        nms_threshold: float,
    ) -> list[tuple[float, int, int, int, int]]:
        """对全量模板匹配结果执行 NMS 去重，保留非冗余命中框。"""
        matches = self._match_all_template(image=image, rule=rule)
        if not matches:
            return []
        scores = np.array([match[0] for match in matches])
        boxes = np.array([[match[1], match[2], match[3], match[4]] for match in matches])
        indices = cv2.dnn.NMSBoxes(
            boxes.tolist(),
            scores.tolist(),
            score_threshold=rule["threshold"],
            nms_threshold=float(nms_threshold),
        )
        if len(indices) == 0:
            return []
        flat_indices = np.array(indices).reshape(-1).tolist()
        return [matches[index] for index in flat_indices]

    def _cleanup_frames(self, now: float, reason: str) -> None:
        """
        清理过期或超量的截图帧缓存。

        先按 TTL 淘汰失效帧，再在容量超限时按最近最少访问顺序继续回收。
        """
        expire_before = now - self.settings.frame_cache_expire_seconds
        expired = [
            frame_id
            for frame_id, entry in self._frames.items()
            if entry.last_access_at < expire_before
        ]
        for frame_id in expired:
            self._delete_frame(frame_id)
        if expired:
            logger.debug(f"Evict {len(expired)} expired frames ({reason})")

        overflow = len(self._frames) - self.settings.frame_cache_max_count
        if overflow > 0:
            sorted_entries = sorted(
                self._frames.values(),
                key=lambda item: item.last_access_at,
            )
            for entry in sorted_entries[:overflow]:
                self._delete_frame(entry.frame_id)
            logger.debug(f"Evict {overflow} overflow frames ({reason})")

    def _cleanup_templates(self, now: float, reason: str) -> None:
        """
        清理过期或超量的模板缓存。

        模板缓存除了淘汰计数外，还会单独记录“因超时过期而失效”的统计。
        """
        expire_before = now - self.settings.template_cache_expire_seconds
        expired = [
            template_key
            for template_key, entry in self._templates.items()
            if entry.last_access_at < expire_before
        ]
        for template_key in expired:
            self._templates.pop(template_key, None)
            self._cache_stats["template_expired"] += 1
            self._cache_stats["template_evictions"] += 1
        if expired:
            logger.debug(f"Evict {len(expired)} expired templates ({reason})")

        overflow = len(self._templates) - self.settings.template_cache_max_count
        if overflow > 0:
            sorted_entries = sorted(
                self._templates.values(),
                key=lambda item: item.last_access_at,
            )
            for entry in sorted_entries[:overflow]:
                self._templates.pop(entry.template_key, None)
                self._cache_stats["template_evictions"] += 1
            logger.debug(f"Evict {overflow} overflow templates ({reason})")

    def _ensure_template_sift(self, entry: TemplateEntry) -> TemplateEntry:
        """确保模板条目已经准备好 SIFT keypoints 和 descriptor。"""
        if entry.sift_kp is not None or entry.sift_des is not None:
            return entry
        if self._sift is None:
            self._sift = cv2.SIFT_create()
        kp, des = self._sift.detectAndCompute(entry.image_rgb, None)
        entry.sift_kp = kp
        entry.sift_des = des
        logger.debug(
            f"Prepare template sift {entry.file_path} "
            f"descriptor_shape={None if des is None else des.shape}"
        )
        return entry

    @staticmethod
    def _build_template_fingerprint(template_path: str) -> str:
        """基于修改时间和文件大小生成模板指纹，用于缓存失效判断。"""
        stat = os.stat(template_path)
        return f"{int(stat.st_mtime_ns)}:{int(stat.st_size)}"

    @staticmethod
    def _to_gray(image_rgb: np.ndarray) -> np.ndarray:
        """将模板图转换为灰度图，便于后续需要灰度特征的匹配流程复用。"""
        if image_rgb.ndim == 2:
            return image_rgb
        return cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)

    @staticmethod
    def _load_template_image(template_path: str) -> np.ndarray:
        """
        从磁盘读取模板文件，并统一转换为 RGB 排列。

        该方法同时兼容灰度图和彩色图，读取失败时直接抛出 `FileNotFoundError`。
        """
        image = cv2.imdecode(fromfile(template_path, dtype=uint8), -1)
        if image is None:
            raise FileNotFoundError(f"Template not found or unreadable: {template_path}")
        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
