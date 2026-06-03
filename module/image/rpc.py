# This Python file uses the following encoding: utf-8
from __future__ import annotations

import atexit
import multiprocessing
import pickle
import socket
import time
from typing import Any, Optional

import numpy as np
import zerorpc

from module.exception import ScriptError
from module.image.runtime import ImageRuntime
from module.logger import logger

# 当前进程自动拉起的图像服务进程，仅在 StartImageServer 场景下使用。
_IMAGE_SERVER_PROCESS: Optional[multiprocessing.Process] = None
# 按地址缓存 RPC 客户端，避免同一入口反复建立 zerorpc 连接。
_IMAGE_CLIENT_CACHE: dict[str, "ImageClient"] = {}


def _normalize_address(address: str) -> str:
    """
    统一补齐 zerorpc 所需的 tcp 协议前缀。

    Args:
        address: 配置中的原始服务地址，允许传入 `127.0.0.1:22269` 这类简写。

    Returns:
        补齐为 `tcp://host:port` 形式后的地址。
    """
    if address.startswith("tcp://"):
        return address
    return f"tcp://{address}"


def _split_host_port(address: str) -> tuple[str, int]:
    """
    从服务地址中拆出主机和端口。

    Args:
        address: 支持带或不带 `tcp://` 前缀的地址。

    Returns:
        `(host, port)` 二元组；未显式提供端口时回退到默认图像服务端口 `22269`。
    """
    addr = address.replace("tcp://", "")
    if ":" not in addr:
        return addr, 22269
    host, port = addr.rsplit(":", 1)
    return host, int(port)


def _is_port_in_use(host: str, port: int) -> bool:
    """
    快速探测目标端口是否已有进程监听。

    该函数仅用于启动前检查和就绪轮询，不负责判断监听方一定是图像服务。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.5)
        sock.connect((host, port))
        sock.shutdown(2)
        return True
    except Exception as e:
        return False
    finally:
        sock.close()


def _build_server_settings() -> dict[str, Any]:
    """
    从部署配置中提取图像服务运行时需要的缓存与 worker 参数。

    Returns:
        传给 `ImageRuntime` 的 settings 字典，字段名与运行时配置结构保持一致。
    """
    from module.server.setting import State

    deploy_config = State.deploy_config
    return {
        "frame_cache_expire_seconds": float(deploy_config.ImageFrameCacheExpireSeconds),
        "frame_cache_max_count": int(deploy_config.ImageFrameCacheMaxCount),
        "template_cache_expire_seconds": int(deploy_config.ImageTemplateCacheExpireSeconds),
        "template_cache_max_count": int(deploy_config.ImageTemplateCacheMaxCount),
        "worker_count": int(deploy_config.ImageServerWorkerCount),
    }


def ensure_image_server_started() -> bool:
    """
    在需要由当前入口托管图像服务时，确保服务进程已经启动。

    Returns:
        启动成功或检测到目标端口已被监听时返回 `True`；
        若配置中禁用了自动拉起，返回 `False`。
    """
    from module.server.setting import State

    deploy_config = State.deploy_config
    if not deploy_config.StartImageServer:
        return False

    if deploy_config.ImageServerPort:
        port = int(deploy_config.ImageServerPort)
    else:
        _, port = _split_host_port(str(deploy_config.ImageClientAddress))
    host = "0.0.0.0"

    if _is_port_in_use("127.0.0.1", port):
        logger.info(f"Image server already running on port {port}")
        return True

    global _IMAGE_SERVER_PROCESS
    if _IMAGE_SERVER_PROCESS is not None and _IMAGE_SERVER_PROCESS.is_alive():
        logger.info("Image server process already started")
        return True

    _IMAGE_SERVER_PROCESS = multiprocessing.Process(
        target=run_image_server,
        args=(host, port, _build_server_settings()),
        name="image_server",
        daemon=True,
    )
    _IMAGE_SERVER_PROCESS.start()
    logger.info(f"Start image server on {host}:{port}")
    for _ in range(50):
        if _is_port_in_use("127.0.0.1", port):
            return True
        time.sleep(0.1)
    logger.error(f"Image server is not ready on port {port}")
    return False


def ensure_image_server_ready() -> bool:
    """
    确保当前运行入口能够连通配置中的图像服务。

    当 `StartImageServer` 为真时，会先尝试自动拉起服务；随后统一通过
    `get_image_client(refresh=True)` 做一次连接探测，失败时直接抛出 `ScriptError`，
    不保留本地识别回退路径。
    """
    from module.server.setting import State

    deploy_config = State.deploy_config
    if deploy_config.StartImageServer:
        ensure_image_server_started()

    address = deploy_config.ImageClientAddress or "127.0.0.1:22269"
    try:
        get_image_client(address=address, refresh=True)
        logger.info(f"Image server ready: {address}")
        return True
    except Exception as exc:
        raise ScriptError(f"Image server connection failed: {address}") from exc


def shutdown_image_server(timeout: float = 2.0) -> bool:
    """
    关闭由当前进程托管的图像服务，并清理本地客户端缓存。

    Args:
        timeout: 等待子进程正常退出的秒数，超时后会升级为强制 kill。

    Returns:
        实际执行了关闭流程并完成回收时返回 `True`；若当前没有托管中的服务进程则返回 `False`。
    """
    global _IMAGE_SERVER_PROCESS

    process = _IMAGE_SERVER_PROCESS
    if process is None:
        return False

    if not process.is_alive():
        _IMAGE_SERVER_PROCESS = None
        return False

    logger.info("Stopping image server process")
    try:
        process.terminate()
        process.join(timeout=timeout)
        if process.is_alive():
            logger.warning("Image server process did not exit in time, force killing")
            process.kill()
            process.join(timeout=1.0)
        logger.info("Image server process stopped")
        return True
    except Exception as exc:
        logger.exception(exc)
        return False
    finally:
        _IMAGE_SERVER_PROCESS = None
        _IMAGE_CLIENT_CACHE.clear()


def run_image_server(host: str, port: int, settings: dict[str, Any] | None = None) -> None:
    """
    以 zerorpc 服务形式启动图像运行时主循环。

    Args:
        host: 服务绑定地址。
        port: 服务监听端口。
        settings: 传给 `ImageRuntime` 的缓存与调度配置；为空时使用运行时默认值。
    """
    runtime = ImageRuntime(settings=settings)
    server = zerorpc.Server(runtime)
    try:
        server.bind(f"tcp://{host}:{port}")
        server.run()
    finally:
        runtime.shutdown()


class ImageClient:
    """图像服务 RPC 客户端，封装帧注册、模板准备和各类匹配调用。"""

    def __init__(self, address: str) -> None:
        """
        建立到指定图像服务地址的 zerorpc 连接，并在初始化阶段完成一次 `ping` 验证。

        Args:
            address: 图像服务地址，允许传入带或不带 `tcp://` 前缀的字符串。
        """
        self.address = _normalize_address(address)
        self.client = zerorpc.Client(timeout=10)
        try:
            self.client.connect(self.address)
            self.client.ping()
        except Exception as exc:
            raise ScriptError(f"Image server connection failed: {self.address}") from exc

    def ping(self) -> bool:
        """探测远程图像服务是否在线。"""
        return bool(self.client.ping())

    def get_server_info(self) -> dict[str, Any]:
        """获取服务端当前缓存与调度器状态快照。"""
        return self.client.get_server_info()

    def register_frame(self, image: np.ndarray, config_name: str) -> dict[str, Any]:
        """
        向服务端注册一张截图帧，并返回可复用的 `frame_id`。

        Args:
            image: 当前截图的 numpy 数组。客户端会在本地序列化后上传一次。
            config_name: 当前脚本配置名；服务端用它删除同配置旧截图帧。
        """
        payload = pickle.dumps(image, protocol=4)
        return self.client.register_frame(payload, config_name)

    def get_frame_info(self, frame_id: str) -> dict[str, Any]:
        """
        查询某个已注册帧的元信息。

        Args:
            frame_id: 由 `register_frame()` 返回的服务端帧引用。
        """
        return self.client.get_frame_info(frame_id)

    def prepare_template(self, template_path: str, include_sift: bool = False) -> dict[str, Any]:
        """
        触发服务端预加载模板，并按需准备 SIFT 特征。

        Args:
            template_path: 模板文件绝对路径。
            include_sift: 为真时会额外准备 SIFT 描述子，适合后续 SIFT/FLANN 匹配预热。
        """
        return self.client.prepare_template(template_path, include_sift)

    @staticmethod
    def _encode_image_payload(image: np.ndarray | None, frame_id: str | None) -> bytes | None:
        """
        统一处理“直接上传图片”与“复用已注册 frame_id”两种调用方式。

        当提供 `frame_id` 时，本次请求不再重复上传整张图片；只有在没有 `frame_id`
        且显式传入 `image` 时，才会序列化图片数据。
        """
        if frame_id is not None or image is None:
            return None
        return pickle.dumps(image, protocol=4)

    def match_rule(
        self,
        rule_data: dict[str, Any],
        image: np.ndarray | None = None,
        frame_id: str | None = None,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        """
        执行单个图像规则匹配。

        Args:
            rule_data: 由规则对象导出的服务端匹配描述。
            image: 直接上传的截图；当 `frame_id` 可用时通常不再传入。
            frame_id: 已在服务端注册过的截图引用，优先级高于 `image`。
            threshold: 可选的临时阈值覆盖值；为空时沿用规则自身阈值。
        """
        payload = self._encode_image_payload(image=image, frame_id=frame_id)
        return self.client.match_rule(rule_data, frame_id, payload, threshold)

    def match_rule_with_brightness_window(
        self,
        rule_data: dict[str, Any],
        image: np.ndarray | None = None,
        frame_id: str | None = None,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        """
        执行带亮度窗口约束的单规则模板匹配。

        该接口仅适用于普通模板匹配，会在命中后额外校验源区域和模板区域的平均亮度范围。
        """
        payload = self._encode_image_payload(image=image, frame_id=frame_id)
        return self.client.match_rule_with_brightness_window(rule_data, frame_id, payload, threshold)

    def match_many(
        self,
        rules_data: list[dict[str, Any]],
        image: np.ndarray | None = None,
        frame_id: str | None = None,
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        在同一张截图上批量匹配多个规则。

        适用于 `RuleGif`、`ImageGrid` 这类需要在同帧内判断多个候选模板的场景。
        """
        payload = self._encode_image_payload(image=image, frame_id=frame_id)
        return self.client.match_many(rules_data, frame_id, payload, threshold)

    def match_all(
        self,
        rule_data: dict[str, Any],
        image: np.ndarray | None = None,
        frame_id: str | None = None,
        threshold: float | None = None,
        roi: list[int] | None = None,
    ) -> dict[str, Any]:
        """
        返回某个模板规则在当前截图中的全部匹配结果。

        Args:
            roi: 可选的搜索区域覆盖值；提供后由服务端在该区域内枚举所有命中。
        """
        payload = self._encode_image_payload(image=image, frame_id=frame_id)
        return self.client.match_all(rule_data, frame_id, payload, threshold, roi)

    def match_all_any(
        self,
        rule_data: dict[str, Any],
        image: np.ndarray | None = None,
        frame_id: str | None = None,
        threshold: float | None = None,
        roi: list[int] | None = None,
        nms_threshold: float = 0.3,
    ) -> dict[str, Any]:
        """
        返回去重后的全部匹配结果。

        Args:
            nms_threshold: NMS 去重阈值，用于移除高度重叠的冗余框。
        """
        payload = self._encode_image_payload(image=image, frame_id=frame_id)
        return self.client.match_all_any(rule_data, frame_id, payload, threshold, roi, nms_threshold)

    def match_all_any_many(
        self,
        rules_data: list[dict[str, Any]],
        image: np.ndarray | None = None,
        frame_id: str | None = None,
        threshold: float | None = None,
        nms_threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        """
        在同一帧上对多个规则执行“全量匹配 + NMS 去重”。

        该接口适合一次性拿到多组模板的非冗余命中列表。
        """
        payload = self._encode_image_payload(image=image, frame_id=frame_id)
        return self.client.match_all_any_many(rules_data, frame_id, payload, threshold, nms_threshold)

    def match_dynamic_template(
        self,
        template: np.ndarray,
        image: np.ndarray | None = None,
        frame_id: str | None = None,
        roi_back: list[int] | None = None,
        threshold: float = 0.75,
        name: str = "RuleAnimate",
    ) -> dict[str, Any]:
        """
        以运行时生成的模板执行动态模板匹配。

        Args:
            template: 由上一帧或其他实时流程生成的小模板。
            image: 当前待匹配截图；若已提供 `frame_id` 则无需重复上传。
            frame_id: 当前截图在服务端的缓存引用。
            roi_back: 在当前截图上的搜索区域；为空时默认搜索整张图。
            threshold: 动态模板匹配阈值。
            name: 用于日志输出的匹配名称。
        """
        template_payload = pickle.dumps(template, protocol=4)
        image_payload = self._encode_image_payload(image=image, frame_id=frame_id)
        return self.client.match_dynamic_template(template_payload, frame_id, image_payload, roi_back, threshold, name)


def get_image_client(address: str | None = None, refresh: bool = False) -> ImageClient:
    """
    获取指定地址的图像服务客户端，并按地址缓存连接实例。

    Args:
        address: 目标图像服务地址；为空时回落到部署配置中的 `ImageClientAddress`。
        refresh: 为真时强制重建该地址对应的客户端连接，常用于服务重启后的重连。
    """
    from module.server.setting import State

    resolved_address = address or State.deploy_config.ImageClientAddress or "127.0.0.1:22269"
    if refresh or resolved_address not in _IMAGE_CLIENT_CACHE:
        _IMAGE_CLIENT_CACHE[resolved_address] = ImageClient(resolved_address)
    return _IMAGE_CLIENT_CACHE[resolved_address]


atexit.register(shutdown_image_server)
