# This Python file uses the following encoding: utf-8
from __future__ import annotations

import asyncio
import base64
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_ROOT = (PROJECT_ROOT / "log").resolve()
ERROR_LOG_ROOT = (LOG_ROOT / "error").resolve()

CURSOR_VERSION = 1
DEFAULT_LIMIT_LINES = 500
DEFAULT_LIMIT_BYTES = 262144
MAX_LIMIT_LINES = 2000
MAX_LIMIT_BYTES = 1048576
DEFAULT_STREAM_LIMIT_LINES = 200
DEFAULT_STREAM_LIMIT_BYTES = 131072
MAX_STREAM_LIMIT_LINES = 1000
MAX_STREAM_LIMIT_BYTES = 524288
MIN_LIMIT_BYTES = 4096
MAX_LINE_BYTES = 65536
DEFAULT_ERROR_LIMIT = 100
MAX_ERROR_LIMIT = 500
DEFAULT_ERROR_LOG_LIMIT_BYTES = 262144
MAX_ERROR_LOG_LIMIT_BYTES = 1048576
POLL_INTERVAL_SECONDS = 1.0

_LOG_FILE_RE = re.compile(r"^(?P<day>\d{4}-\d{2}-\d{2})_(?P<script>.+)\.txt$")
_ERROR_LEGACY_RE = re.compile(r"^(?P<timestamp>\d{10,})$")
_ERROR_NAMED_RE = re.compile(r"^(?P<script>.+)_(?P<timestamp>\d{10,})$")
_UNSAFE_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SYSTEM_LOG_NAMES = {"api", "server", "script", "base", "assets"}


class LogServiceError(Exception):
    """日志浏览服务的业务异常。

    Args:
        status_code: 转换成 HTTP 响应时使用的状态码。
        code: 给前端判断错误类型使用的稳定错误码。
        message: 面向调用方的错误说明。
    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        """保存日志服务异常的 HTTP 映射信息。

        Args:
            status_code: 要返回给 HTTP 层的状态码。
            code: 稳定错误码, 前端可据此做分支处理。
            message: 错误说明文本。
        """
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(frozen=True)
class LogFileInfo:
    """单个脚本日志文件的索引信息。

    Attributes:
        day: 日志文件名中的日期。
        script_name: 已标准化后的脚本名。
        file_name: 日志文件名, 格式为 `YYYY-MM-DD_<script>.txt`。
        path: 日志文件的绝对路径。
        size: 扫描时读取到的文件字节数。
    """

    day: date
    script_name: str
    file_name: str
    path: Path
    size: int


@dataclass(frozen=True)
class Cursor:
    """日志游标解码后的结构。

    Attributes:
        script_name: 游标所属的标准化脚本名。
        direction: 游标用途, `older` 用于向更旧日志回翻, `live` 用于实时追加。
        file_name: 游标指向的日志文件名。
        offset: 游标指向的文件字节偏移量。
        line_no: 游标指向位置对应的下一行行号。
    """

    script_name: str
    direction: str
    file_name: str
    offset: int
    line_no: int


@dataclass
class ReverseFileReadResult:
    """单个文件反向读取的结果。

    Attributes:
        lines: 已按旧到新顺序整理好的日志行。
        used_bytes: 本次窗口累计使用的原始字节数。
        reached_start: 是否已经读到当前文件开头。
    """

    lines: list[dict[str, Any]]
    used_bytes: int
    reached_start: bool


@dataclass
class LiveState:
    """SSE 实时 tail 当前所在的位置。

    Attributes:
        script_name: 正在订阅的标准化脚本名。
        file_name: 当前 tail 的日志文件名。
        path: 当前 tail 的日志文件绝对路径。
        offset: 下次读取时的文件字节偏移量。
        line_no: 下次读取时的起始行号。
    """

    script_name: str
    file_name: str
    path: Path
    offset: int
    line_no: int


@dataclass(frozen=True)
class ErrorLogInfo:
    """错误日志目录的索引信息。

    Attributes:
        id: 错误目录名, 也是接口使用的 `error_id`。
        path: 错误目录的绝对路径。
        script_name: 新格式目录中的脚本名; 旧格式目录没有脚本名时为 None。
        timestamp_ms: 目录名中的毫秒时间戳。
        legacy: 是否为旧格式纯时间戳目录。
    """

    id: str
    path: Path
    script_name: str | None
    timestamp_ms: int
    legacy: bool


def normalize_script_name(script_name: str) -> str:
    """标准化脚本名, 用于日志文件名、cursor 校验和错误目录命名。

    Args:
        script_name: 调用方传入的脚本配置名或日志脚本名。

    Returns:
        去掉运行时后缀并清理危险字符后的脚本名。
    """
    name = str(script_name or "").strip()
    if "_" in name:
        name = name.split("_", 1)[0]
    return sanitize_path_name(name)


def sanitize_path_name(name: str) -> str:
    """清理可进入路径片段的名称。

    Args:
        name: 原始名称, 可能来自配置名、URL 参数或目录名。

    Returns:
        不包含路径分隔符、Windows 非法字符和 `..` 的安全名称。
    """
    sanitized = _UNSAFE_NAME_RE.sub("_", str(name or "").strip())
    sanitized = sanitized.replace("..", "_").strip(" .")
    return sanitized or "script"


def ensure_child_path(root: Path, path: Path) -> Path:
    """确保目标路径位于指定根目录内。

    Args:
        root: 允许访问的根目录。
        path: 需要校验的目标路径。

    Returns:
        解析后的目标绝对路径。

    Raises:
        LogServiceError: 当目标路径逃逸出根目录时抛出。
    """
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise LogServiceError(400, "LOG_PATH_INVALID", "Path is outside log directory") from exc
    return resolved_path


def build_error_log_dir_name(script_name: str, timestamp_ms: int) -> str:
    """生成新的错误日志目录名。

    Args:
        script_name: 当前脚本配置名。
        timestamp_ms: 错误产生时的毫秒时间戳。

    Returns:
        `<script_name>_<timestamp_ms>` 格式的安全目录名。
    """
    return f"{normalize_script_name(script_name)}_{int(timestamp_ms)}"


class LogBrowserService:
    """脚本日志浏览服务。

    该服务只依赖本地 `log/` 目录, 提供脚本日志最新窗口、向上回翻、SSE 实时追加、
    错误日志列表、错误详情和错误截图路径解析能力。
    """

    def list_log_files(self, script_name: str) -> list[LogFileInfo]:
        """扫描指定脚本的全部日志文件。

        Args:
            script_name: 脚本配置名或日志脚本名, 会先统一标准化。

        Returns:
            按日期从新到旧排序的日志文件索引列表。
        """
        normalized = normalize_script_name(script_name)
        files: list[LogFileInfo] = []
        if not LOG_ROOT.exists():
            return files

        for path in LOG_ROOT.iterdir():
            if not path.is_file():
                continue
            matched = _LOG_FILE_RE.match(path.name)
            if not matched:
                continue
            try:
                day = date.fromisoformat(matched.group("day"))
            except ValueError:
                continue
            file_script = normalize_script_name(matched.group("script"))
            if file_script in _SYSTEM_LOG_NAMES:
                continue
            if file_script != normalized:
                continue
            files.append(
                LogFileInfo(
                    day=day,
                    script_name=file_script,
                    file_name=path.name,
                    path=path.resolve(),
                    size=path.stat().st_size,
                )
            )

        return sorted(files, key=lambda item: (item.day, item.file_name), reverse=True)

    def read_window(
        self,
        script_name: str,
        cursor: str | None = None,
        limit_lines: int = DEFAULT_LIMIT_LINES,
        limit_bytes: int = DEFAULT_LIMIT_BYTES,
    ) -> dict[str, Any]:
        """读取脚本日志窗口。

        无 cursor 时从最新日志文件末尾向前读取; 有 `older_cursor` 时从 cursor 指定位置
        继续向更旧内容读取。跨天文件切换由服务端自动完成。

        Args:
            script_name: 目标脚本名。
            cursor: 上一次响应返回的 `older_cursor`; 不传表示打开最新窗口。
            limit_lines: 本次最多返回的日志行数。
            limit_bytes: 本次最多累计的日志原始字节数, 按从后向前的窗口计算。

        Returns:
            可直接返回给前端的日志窗口响应字典。

        Raises:
            LogServiceError: 当 limit 越界、cursor 非法或 cursor 指向文件已不可用时抛出。
        """
        normalized = normalize_script_name(script_name)
        self._validate_limits(limit_lines, limit_bytes, MAX_LIMIT_LINES, MAX_LIMIT_BYTES)

        files = self.list_log_files(normalized)
        live_cursor = self._build_latest_live_cursor(normalized, files)
        if not files:
            return self._empty_window(normalized, live_cursor, limit_lines, limit_bytes)

        if cursor:
            decoded = self.decode_cursor(cursor, normalized, "older", require_existing_file=True)
            file_index = self._find_file_index(files, decoded.file_name)
            if file_index is None:
                raise LogServiceError(409, "LOG_CURSOR_STALE", "Cursor file is no longer available")
            end_offset = decoded.offset
        else:
            file_index = 0
            end_offset = files[0].path.stat().st_size

        chunks: list[list[dict[str, Any]]] = []
        used_bytes = 0
        index = file_index
        first_file = True

        while index < len(files) and sum(len(chunk) for chunk in chunks) < limit_lines:
            info = files[index]
            file_size = info.path.stat().st_size
            current_end = min(end_offset, file_size) if first_file else file_size
            if current_end < 0:
                current_end = 0
            if end_offset > file_size and first_file:
                raise LogServiceError(409, "LOG_CURSOR_STALE", "Cursor offset is beyond current file size")

            remaining_lines = limit_lines - sum(len(chunk) for chunk in chunks)
            remaining_bytes = max(limit_bytes - used_bytes, 0)
            if remaining_lines <= 0:
                break
            if remaining_bytes <= 0 and chunks:
                break

            result = self._read_reverse_file(
                info,
                current_end,
                remaining_lines,
                remaining_bytes,
                MAX_LINE_BYTES,
            )
            if result.lines:
                chunks.append(result.lines)
                used_bytes += result.used_bytes
                if used_bytes >= limit_bytes:
                    break

            if not result.reached_start:
                break

            index += 1
            first_file = False
            end_offset = 0

        lines = [line for chunk in reversed(chunks) for line in chunk]
        has_older = self._has_older(files, lines)
        older_cursor = self._build_older_cursor(normalized, lines) if lines else None

        return {
            "script_name": normalized,
            "window": self._build_window(lines),
            "older_cursor": older_cursor,
            "live_cursor": live_cursor,
            "has_older": has_older,
            "reached_start": not has_older,
            "limits": {
                "limit_lines": limit_lines,
                "limit_bytes": limit_bytes,
                "max_line_bytes": MAX_LINE_BYTES,
            },
            "lines": lines,
        }

    async def stream_events(
        self,
        script_name: str,
        cursor: str | None = None,
        limit_lines: int = DEFAULT_STREAM_LIMIT_LINES,
        limit_bytes: int = DEFAULT_STREAM_LIMIT_BYTES,
    ):
        """生成脚本实时日志 SSE 事件。

        Args:
            script_name: 目标脚本名。
            cursor: `live_cursor`, 不传时从当前最新完整行之后开始订阅。
            limit_lines: 单个 `append` 事件最多包含的日志行数。
            limit_bytes: 单个 `append` 事件最多累计的日志原始字节数。

        Yields:
            已编码好的 SSE 文本, 事件类型包括 `ready`、`append`、`rotate`、
            `heartbeat` 和 `error`。
        """
        normalized = normalize_script_name(script_name)
        try:
            self._validate_limits(limit_lines, limit_bytes, MAX_STREAM_LIMIT_LINES, MAX_STREAM_LIMIT_BYTES)
            state = self._build_live_state(normalized, cursor)
        except LogServiceError as exc:
            yield self.encode_sse("error", {"code": exc.code, "message": exc.message})
            return

        yield self.encode_sse(
            "ready",
            {
                "script_name": normalized,
                "file_name": state.file_name,
                "exists": state.path.exists(),
                "cursor": self.encode_cursor(normalized, "live", state.file_name, state.offset, state.line_no),
            },
        )
        if not state.path.exists():
            yield self.encode_sse("heartbeat", self._heartbeat_payload(state))

        while True:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            try:
                append = self._read_live_append(state, limit_lines, limit_bytes, MAX_LINE_BYTES)
                if append["lines"]:
                    state.offset = append["next_offset"]
                    state.line_no = append["next_line_no"]
                    yield self.encode_sse(
                        "append",
                        {
                            "script_name": normalized,
                            "file_name": state.file_name,
                            "next_cursor": self.encode_cursor(
                                normalized,
                                "live",
                                state.file_name,
                                state.offset,
                                state.line_no,
                            ),
                            "lines": append["lines"],
                        },
                    )

                # 当前 tail 的文件不是今天的文件且旧文件已经没有完整新行时, 切到当天文件。
                today_file_name = self._today_file_name(normalized)
                old_file_complete = not state.path.exists() or state.offset >= self._complete_line_offset(state.path)
                if state.file_name != today_file_name and old_file_complete:
                    new_path = (LOG_ROOT / today_file_name).resolve()
                    state = LiveState(
                        script_name=normalized,
                        file_name=today_file_name,
                        path=new_path,
                        offset=0,
                        line_no=1,
                    )
                    yield self.encode_sse(
                        "rotate",
                        {
                            "script_name": normalized,
                            "from_file": append["file_name"],
                            "to_file": today_file_name,
                            "cursor": self.encode_cursor(normalized, "live", today_file_name, 0, 1),
                        },
                    )
                    if not state.path.exists():
                        yield self.encode_sse("heartbeat", self._heartbeat_payload(state))
                    continue

                if not state.path.exists():
                    yield self.encode_sse("heartbeat", self._heartbeat_payload(state))
            except LogServiceError as exc:
                yield self.encode_sse("error", {"code": exc.code, "message": exc.message})
                return

    def encode_cursor(self, script_name: str, direction: str, file_name: str, offset: int, line_no: int) -> str:
        """编码日志 cursor。

        Args:
            script_name: cursor 绑定的脚本名。
            direction: cursor 用途, 只能由调用方按接口语义传入 `older` 或 `live`。
            file_name: cursor 指向的日志文件名。
            offset: cursor 指向的文件字节偏移量。
            line_no: cursor 指向位置对应的下一行行号。

        Returns:
            URL-safe base64 字符串, 可直接作为查询参数传给前端。
        """
        payload = {
            "v": CURSOR_VERSION,
            "script_name": normalize_script_name(script_name),
            "direction": direction,
            "file_name": file_name,
            "offset": int(offset),
            "line_no": int(line_no),
        }
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    def decode_cursor(
        self,
        cursor: str,
        script_name: str,
        direction: str,
        *,
        require_existing_file: bool,
    ) -> Cursor:
        """解码并校验日志 cursor。

        Args:
            cursor: 前端回传的 URL-safe cursor 字符串。
            script_name: 当前请求路径中的脚本名。
            direction: 当前接口期望的 cursor 用途。
            require_existing_file: 是否要求 cursor 指向的日志文件当前必须存在。

        Returns:
            解码后的 cursor 结构。

        Raises:
            LogServiceError: 当 cursor 格式、版本、脚本名、方向、路径或行边界非法时抛出。
        """
        try:
            padding = "=" * (-len(cursor) % 4)
            payload = json.loads(base64.urlsafe_b64decode((cursor + padding).encode("ascii")).decode("utf-8"))
        except Exception as exc:
            raise LogServiceError(400, "LOG_CURSOR_INVALID", "Cursor is not valid") from exc

        if payload.get("v") != CURSOR_VERSION:
            raise LogServiceError(400, "LOG_CURSOR_VERSION", "Cursor version is not supported")
        normalized = normalize_script_name(script_name)
        if normalize_script_name(payload.get("script_name", "")) != normalized:
            raise LogServiceError(400, "LOG_CURSOR_SCRIPT_MISMATCH", "Cursor script does not match request")
        if payload.get("direction") != direction:
            raise LogServiceError(400, "LOG_CURSOR_DIRECTION", "Cursor direction does not match endpoint")

        file_name = str(payload.get("file_name", ""))
        if Path(file_name).name != file_name:
            raise LogServiceError(400, "LOG_CURSOR_INVALID", "Cursor file name is not valid")
        matched = _LOG_FILE_RE.match(file_name)
        if not matched or normalize_script_name(matched.group("script")) != normalized:
            raise LogServiceError(400, "LOG_CURSOR_INVALID", "Cursor file name does not match script")

        try:
            offset = int(payload.get("offset"))
            line_no = int(payload.get("line_no"))
        except (TypeError, ValueError) as exc:
            raise LogServiceError(400, "LOG_CURSOR_INVALID", "Cursor offset or line number is not valid") from exc
        if offset < 0 or line_no < 1:
            raise LogServiceError(400, "LOG_CURSOR_INVALID", "Cursor offset or line number is not valid")

        path = ensure_child_path(LOG_ROOT, LOG_ROOT / file_name)
        if path.exists():
            if offset > path.stat().st_size:
                raise LogServiceError(409, "LOG_CURSOR_STALE", "Cursor offset is beyond current file size")
            if not self._is_line_boundary(path, offset):
                raise LogServiceError(409, "LOG_CURSOR_STALE", "Cursor no longer points to a line boundary")
        else:
            if require_existing_file:
                raise LogServiceError(409, "LOG_CURSOR_STALE", "Cursor file is no longer available")

        return Cursor(
            script_name=normalized,
            direction=direction,
            file_name=file_name,
            offset=offset,
            line_no=line_no,
        )

    def list_error_logs(
        self,
        date_text: str | None = None,
        script_name: str | None = None,
        limit: int = DEFAULT_ERROR_LIMIT,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """分页查询错误日志目录列表。

        Args:
            date_text: 目标日期, 格式为 `YYYY-MM-DD`; 不传时返回全部日期的错误日志。
            script_name: 可选脚本名过滤条件, 不传时返回全部脚本的错误日志。
            limit: 本页最多返回的错误目录数量。
            cursor: 上一次列表响应返回的分页 cursor。

        Returns:
            错误日志列表响应字典。

        Raises:
            LogServiceError: 当日期、limit 或 cursor 非法时抛出。
        """
        if limit < 1 or limit > MAX_ERROR_LIMIT:
            raise LogServiceError(422, "LOG_LIMIT_INVALID", f"limit must be in 1..{MAX_ERROR_LIMIT}")

        target_date = self._parse_error_date(date_text) if date_text else None
        normalized_script = normalize_script_name(script_name) if script_name else None
        offset = self._decode_error_cursor(cursor) if cursor else 0
        items = [
            info for info in self._scan_error_logs()
            if (target_date is None or self._error_log_date(info) == target_date)
            and (normalized_script is None or info.script_name == normalized_script)
        ]
        items.sort(key=lambda item: (item.timestamp_ms, item.id), reverse=True)

        page = items[offset:offset + limit]
        next_offset = offset + len(page)
        has_more = next_offset < len(items)
        return {
            "date": target_date.isoformat() if target_date is not None else None,
            "script_name": normalized_script,
            "items": [self._error_log_item(info) for info in page],
            "next_cursor": self._encode_error_cursor(next_offset) if has_more else None,
            "has_more": has_more,
        }

    def get_error_detail(self, error_id: str, log_limit_bytes: int = DEFAULT_ERROR_LOG_LIMIT_BYTES) -> dict[str, Any]:
        """读取单个错误日志目录详情。

        Args:
            error_id: 错误目录名, 支持新格式 `<script_name>_<timestamp_ms>` 和旧格式 `<timestamp_ms>`。
            log_limit_bytes: `log.txt` 最多返回的字节数。

        Returns:
            错误元信息、脱敏日志内容和截图元信息列表。

        Raises:
            LogServiceError: 当目录不存在、目录名非法或字节上限越界时抛出。
        """
        if log_limit_bytes < 1 or log_limit_bytes > MAX_ERROR_LOG_LIMIT_BYTES:
            raise LogServiceError(
                422,
                "LOG_LIMIT_INVALID",
                f"log_limit_bytes must be in 1..{MAX_ERROR_LOG_LIMIT_BYTES}",
            )
        info = self._get_error_info(error_id)
        log_payload = self._read_error_text(info.path / "log.txt", log_limit_bytes)
        images = [self._image_item(info, path) for path in sorted(info.path.glob("*.png"), key=lambda item: item.name)]
        return {
            "id": info.id,
            "directory": info.id,
            "script_name": info.script_name,
            "timestamp_ms": info.timestamp_ms,
            "time": self._timestamp_to_iso(info.timestamp_ms),
            "legacy": info.legacy,
            "log": log_payload,
            "images": images,
        }

    def get_error_image_path(self, error_id: str, image_name: str) -> Path:
        """解析并校验错误截图路径。

        Args:
            error_id: 错误目录名。
            image_name: 目标 PNG 截图文件名。

        Returns:
            截图文件的绝对路径。

        Raises:
            LogServiceError: 当目录、图片名或路径边界非法时抛出。
        """
        info = self._get_error_info(error_id)
        if Path(image_name).name != image_name or not image_name.lower().endswith(".png"):
            raise LogServiceError(400, "LOG_IMAGE_INVALID", "Image name is not valid")
        image_path = ensure_child_path(info.path, info.path / image_name)
        if not image_path.exists() or not image_path.is_file():
            raise LogServiceError(404, "LOG_IMAGE_NOT_FOUND", "Image does not exist")
        return image_path

    def encode_sse(self, event: str, payload: dict[str, Any]) -> str:
        """把事件名和载荷编码成 SSE 文本。

        Args:
            event: SSE 事件名。
            payload: 事件 JSON 载荷。

        Returns:
            符合 `text/event-stream` 格式的字符串。
        """
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        return f"event: {event}\ndata: {data}\n\n"

    def _read_reverse_file(
        self,
        info: LogFileInfo,
        end_offset: int,
        limit_lines: int,
        limit_bytes: int,
        max_line_bytes: int,
    ) -> ReverseFileReadResult:
        """从单个日志文件指定 offset 向前读取完整日志行。

        Args:
            info: 当前日志文件索引信息。
            end_offset: 本次窗口读取的结束偏移量, 不包含该位置之后的内容。
            limit_lines: 本文件最多读取的行数。
            limit_bytes: 本文件最多累计的日志原始字节数。
            max_line_bytes: 单行展示文本的安全截断上限。

        Returns:
            当前文件内的反向读取结果。
        """
        if end_offset <= 0:
            return ReverseFileReadResult(lines=[], used_bytes=0, reached_start=True)

        with info.path.open("rb") as file:
            file.seek(0)
            data = file.read(end_offset)
        data = self._drop_trailing_partial_line(data)

        spans = self._line_spans(data)
        selected_reversed: list[dict[str, Any]] = []
        used_bytes = 0
        reached_start = False

        for index in range(len(spans) - 1, -1, -1):
            start, end = spans[index]
            raw = data[start:end]
            raw_length = len(raw)
            if len(selected_reversed) >= limit_lines:
                break
            if used_bytes + raw_length > limit_bytes and selected_reversed:
                break

            selected_reversed.append(
                self._build_line_item(
                    file_name=info.file_name,
                    line_no=index + 1,
                    offset=start,
                    raw=raw,
                    max_line_bytes=max_line_bytes,
                )
            )
            used_bytes += raw_length

        lines = list(reversed(selected_reversed))
        if not lines:
            reached_start = True
        elif lines[0]["offset"] == 0:
            reached_start = True
        return ReverseFileReadResult(lines=lines, used_bytes=used_bytes, reached_start=reached_start)

    def _read_live_append(
        self,
        state: LiveState,
        limit_lines: int,
        limit_bytes: int,
        max_line_bytes: int,
    ) -> dict[str, Any]:
        """读取实时订阅位置之后新增的完整日志行。

        Args:
            state: 当前 SSE tail 状态。
            limit_lines: 单次最多返回的新增行数。
            limit_bytes: 单次最多累计的新增日志原始字节数。
            max_line_bytes: 单行展示文本的安全截断上限。

        Returns:
            包含新增行、下一次 offset 和下一行行号的字典。

        Raises:
            LogServiceError: 当日志文件被截断或清理导致 cursor 失效时抛出。
        """
        if not state.path.exists():
            return {
                "file_name": state.file_name,
                "lines": [],
                "next_offset": state.offset,
                "next_line_no": state.line_no,
            }
        size = state.path.stat().st_size
        if size < state.offset:
            raise LogServiceError(409, "LOG_CURSOR_STALE", "Log file was truncated or cleaned")

        with state.path.open("rb") as file:
            file.seek(state.offset)
            data = file.read()

        newline_index = data.rfind(b"\n")
        if newline_index < 0:
            return {
                "file_name": state.file_name,
                "lines": [],
                "next_offset": state.offset,
                "next_line_no": state.line_no,
            }

        complete = data[:newline_index + 1]
        spans = self._line_spans(complete)
        lines: list[dict[str, Any]] = []
        used_bytes = 0
        next_offset = state.offset
        next_line_no = state.line_no

        for index, (start, end) in enumerate(spans):
            raw = complete[start:end]
            raw_length = len(raw)
            if len(lines) >= limit_lines:
                break
            if used_bytes + raw_length > limit_bytes and lines:
                break

            offset = state.offset + start
            lines.append(
                self._build_line_item(
                    file_name=state.file_name,
                    line_no=state.line_no + index,
                    offset=offset,
                    raw=raw,
                    max_line_bytes=max_line_bytes,
                )
            )
            used_bytes += raw_length
            next_offset = state.offset + end
            next_line_no = state.line_no + index + 1

        return {
            "file_name": state.file_name,
            "lines": lines,
            "next_offset": next_offset,
            "next_line_no": next_line_no,
        }

    @staticmethod
    def _line_spans(data: bytes) -> list[tuple[int, int]]:
        """计算二进制内容中的日志行区间。

        Args:
            data: 已经确认可参与切行的二进制内容。

        Returns:
            每一行的 `[start, end)` 字节区间, `end` 包含换行符位置之后的偏移。
        """
        spans: list[tuple[int, int]] = []
        start = 0
        while start < len(data):
            newline = data.find(b"\n", start)
            if newline < 0:
                spans.append((start, len(data)))
                break
            end = newline + 1
            spans.append((start, end))
            start = end
        return spans

    @staticmethod
    def _drop_trailing_partial_line(data: bytes) -> bytes:
        """丢弃尾部未写完整的半行。

        Args:
            data: 从日志文件读取出的二进制内容。

        Returns:
            截断到最后一个完整换行后的二进制内容。
        """
        if not data or data.endswith(b"\n"):
            return data
        newline = data.rfind(b"\n")
        if newline < 0:
            return b""
        return data[:newline + 1]

    def _build_line_item(
        self,
        *,
        file_name: str,
        line_no: int,
        offset: int,
        raw: bytes,
        max_line_bytes: int,
    ) -> dict[str, Any]:
        """构造前端可展示的单行日志结构。

        Args:
            file_name: 日志文件名。
            line_no: 当前行号。
            offset: 当前行在文件中的起始字节偏移量。
            raw: 当前行原始字节, 可包含行尾换行符。
            max_line_bytes: 单行文本超过该字节数时只截断展示文本。

        Returns:
            包含行号、offset、原始长度、展示文本和截断标记的字典。
        """
        text_bytes = raw.rstrip(b"\r\n")
        line_truncated = len(text_bytes) > max_line_bytes
        if line_truncated:
            text_bytes = text_bytes[:max_line_bytes]
        text = text_bytes.decode("utf-8", errors="ignore")
        return {
            "file_name": file_name,
            "line_no": line_no,
            "offset": offset,
            "byte_length": len(raw),
            "text": self._format_client_log_text(text),
            "line_truncated": line_truncated,
        }

    def _build_live_state(self, script_name: str, cursor: str | None) -> LiveState:
        """构造实时订阅初始状态。

        Args:
            script_name: 已标准化脚本名。
            cursor: 可选 `live_cursor`; 不传时从当前最新完整行之后开始。

        Returns:
            SSE tail 初始状态。
        """
        if cursor:
            decoded = self.decode_cursor(cursor, script_name, "live", require_existing_file=False)
            path = ensure_child_path(LOG_ROOT, LOG_ROOT / decoded.file_name)
            if not path.exists():
                today_name = self._today_file_name(script_name)
                if decoded.file_name != today_name or decoded.offset != 0:
                    raise LogServiceError(409, "LOG_CURSOR_STALE", "Cursor file is no longer available")
            return LiveState(
                script_name=script_name,
                file_name=decoded.file_name,
                path=path,
                offset=decoded.offset,
                line_no=decoded.line_no,
            )

        file_name = self._today_file_name(script_name)
        path = ensure_child_path(LOG_ROOT, LOG_ROOT / file_name)
        if path.exists():
            offset = self._complete_line_offset(path)
            line_no = self._line_no_after_offset(path, offset)
        else:
            offset = 0
            line_no = 1
        return LiveState(script_name=script_name, file_name=file_name, path=path, offset=offset, line_no=line_no)

    def _build_latest_live_cursor(self, script_name: str, files: list[LogFileInfo]) -> str:
        """根据最新日志文件生成实时订阅 cursor。

        Args:
            script_name: 已标准化脚本名。
            files: 当前脚本按新到旧排序的日志文件列表。

        Returns:
            指向最新完整行之后的 `live_cursor`。
        """
        if files:
            latest = files[0]
            offset = self._complete_line_offset(latest.path)
            line_no = self._line_no_after_offset(latest.path, offset)
            return self.encode_cursor(script_name, "live", latest.file_name, offset, line_no)

        return self.encode_cursor(script_name, "live", self._today_file_name(script_name), 0, 1)

    def _build_older_cursor(self, script_name: str, lines: list[dict[str, Any]]) -> str:
        """根据当前窗口最旧行生成下一次历史回翻 cursor。

        Args:
            script_name: 已标准化脚本名。
            lines: 当前窗口返回给前端的日志行。

        Returns:
            指向当前窗口最旧行起点的 `older_cursor`。
        """
        oldest = lines[0]
        return self.encode_cursor(
            script_name,
            "older",
            str(oldest["file_name"]),
            int(oldest["offset"]),
            int(oldest["line_no"]),
        )

    @staticmethod
    def _build_window(lines: list[dict[str, Any]]) -> dict[str, Any]:
        """构造当前日志窗口的首尾位置信息。

        Args:
            lines: 当前窗口返回的日志行。

        Returns:
            `from` / `to` 结构, 无日志时两端均为 None。
        """
        if not lines:
            return {"from": None, "to": None}

        def position(line: dict[str, Any]) -> dict[str, Any]:
            """提取一行日志用于窗口首尾展示的位置字段。"""
            return {
                "file_name": line["file_name"],
                "offset": line["offset"],
                "line_no": line["line_no"],
            }

        return {"from": position(lines[0]), "to": position(lines[-1])}

    def _has_older(self, files: list[LogFileInfo], lines: list[dict[str, Any]]) -> bool:
        """判断当前窗口前面是否还有更旧日志。

        Args:
            files: 当前脚本按新到旧排序的日志文件列表。
            lines: 当前窗口返回的日志行。

        Returns:
            True 表示前端还可以继续使用 `older_cursor` 回翻。
        """
        if not lines:
            return False
        oldest = lines[0]
        if int(oldest["offset"]) > 0:
            return True
        file_index = self._find_file_index(files, str(oldest["file_name"]))
        return file_index is not None and file_index < len(files) - 1

    @staticmethod
    def _find_file_index(files: list[LogFileInfo], file_name: str) -> int | None:
        """查找日志文件在已排序列表中的位置。

        Args:
            files: 当前脚本按新到旧排序的日志文件列表。
            file_name: 目标日志文件名。

        Returns:
            文件下标; 未找到时返回 None。
        """
        for index, info in enumerate(files):
            if info.file_name == file_name:
                return index
        return None

    @staticmethod
    def _line_no_after_offset(path: Path, offset: int) -> int:
        """计算指定 offset 之后下一行的行号。

        Args:
            path: 日志文件路径。
            offset: 文件字节偏移量。

        Returns:
            从 1 开始的下一行行号。
        """
        if offset <= 0 or not path.exists():
            return 1
        with path.open("rb") as file:
            data = file.read(offset)
        if not data:
            return 1
        return data.count(b"\n") + (1 if data.endswith(b"\n") else 2)

    @staticmethod
    def _complete_line_offset(path: Path) -> int:
        """获取文件中最后一个完整日志行之后的 offset。

        Args:
            path: 日志文件路径。

        Returns:
            如果文件尾部是半行, 返回最后一个换行符之后的位置; 否则返回文件大小。
        """
        if not path.exists():
            return 0
        data = path.read_bytes()
        if not data:
            return 0
        if data.endswith(b"\n"):
            return len(data)
        newline = data.rfind(b"\n")
        return 0 if newline < 0 else newline + 1

    @staticmethod
    def _is_line_boundary(path: Path, offset: int) -> bool:
        """判断 offset 是否位于日志行边界。

        Args:
            path: 日志文件路径。
            offset: 待校验的字节偏移量。

        Returns:
            True 表示 offset 为文件起点或前一个字节是换行符。
        """
        if offset <= 0:
            return True
        size = path.stat().st_size
        if offset > size:
            return False
        with path.open("rb") as file:
            file.seek(offset - 1)
            return file.read(1) == b"\n"

    @staticmethod
    def _today_file_name(script_name: str) -> str:
        """生成当天脚本日志文件名。

        Args:
            script_name: 脚本名。

        Returns:
            `YYYY-MM-DD_<script>.txt` 格式文件名。
        """
        return f"{date.today().isoformat()}_{normalize_script_name(script_name)}.txt"

    @staticmethod
    def _empty_window(
        script_name: str,
        live_cursor: str,
        limit_lines: int,
        limit_bytes: int,
    ) -> dict[str, Any]:
        """构造无日志文件时的空窗口响应。

        Args:
            script_name: 已标准化脚本名。
            live_cursor: 指向当天空文件起点的实时 cursor。
            limit_lines: 本次请求的行数上限。
            limit_bytes: 本次请求的字节上限。

        Returns:
            HTTP 200 使用的空窗口响应字典。
        """
        return {
            "script_name": script_name,
            "window": {"from": None, "to": None},
            "older_cursor": None,
            "live_cursor": live_cursor,
            "has_older": False,
            "reached_start": True,
            "limits": {
                "limit_lines": limit_lines,
                "limit_bytes": limit_bytes,
                "max_line_bytes": MAX_LINE_BYTES,
            },
            "lines": [],
        }

    @staticmethod
    def _validate_limits(limit_lines: int, limit_bytes: int, max_lines: int, max_bytes: int) -> None:
        """校验日志窗口大小限制。

        Args:
            limit_lines: 请求的行数上限。
            limit_bytes: 请求的字节上限。
            max_lines: 当前接口允许的最大行数。
            max_bytes: 当前接口允许的最大字节数。

        Raises:
            LogServiceError: 当任一限制越界时抛出。
        """
        if limit_lines < 1 or limit_lines > max_lines:
            raise LogServiceError(422, "LOG_LIMIT_INVALID", f"limit_lines must be in 1..{max_lines}")
        if limit_bytes < MIN_LIMIT_BYTES or limit_bytes > max_bytes:
            raise LogServiceError(422, "LOG_LIMIT_INVALID", f"limit_bytes must be in {MIN_LIMIT_BYTES}..{max_bytes}")

    def _heartbeat_payload(self, state: LiveState) -> dict[str, Any]:
        """构造 SSE heartbeat 事件载荷。

        Args:
            state: 当前 SSE tail 状态。

        Returns:
            包含脚本名、文件名、cursor 和当前时间的事件载荷。
        """
        return {
            "script_name": state.script_name,
            "file_name": state.file_name,
            "cursor": self.encode_cursor(
                state.script_name,
                "live",
                state.file_name,
                state.offset,
                state.line_no,
            ),
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        }

    @staticmethod
    def _parse_error_date(date_text: str | None) -> date:
        """解析错误日志查询日期。

        Args:
            date_text: `YYYY-MM-DD` 格式日期; 仅在调用方明确传入时使用。

        Returns:
            目标日期。

        Raises:
            LogServiceError: 当日期格式非法时抛出。
        """
        if not date_text:
            raise LogServiceError(422, "LOG_DATE_INVALID", "Invalid date format, expected YYYY-MM-DD")
        try:
            return date.fromisoformat(date_text)
        except ValueError as exc:
            raise LogServiceError(422, "LOG_DATE_INVALID", "Invalid date format, expected YYYY-MM-DD") from exc

    def _scan_error_logs(self) -> list[ErrorLogInfo]:
        """扫描全部可识别的错误日志目录。

        Returns:
            新格式和旧格式错误目录的索引列表。
        """
        if not ERROR_LOG_ROOT.exists():
            return []

        items: list[ErrorLogInfo] = []
        for path in ERROR_LOG_ROOT.iterdir():
            if not path.is_dir():
                continue
            info = self._parse_error_dir(path)
            if info is not None:
                items.append(info)
        return items

    def _parse_error_dir(self, path: Path) -> ErrorLogInfo | None:
        """解析单个错误日志目录名。

        Args:
            path: 错误日志目录路径。

        Returns:
            可识别时返回目录信息; 不符合新旧格式时返回 None。
        """
        name = path.name
        legacy = _ERROR_LEGACY_RE.match(name)
        if legacy:
            return ErrorLogInfo(
                id=name,
                path=path.resolve(),
                script_name=None,
                timestamp_ms=int(legacy.group("timestamp")),
                legacy=True,
            )

        matched = _ERROR_NAMED_RE.match(name)
        if not matched:
            return None
        return ErrorLogInfo(
            id=name,
            path=path.resolve(),
            script_name=normalize_script_name(matched.group("script")),
            timestamp_ms=int(matched.group("timestamp")),
            legacy=False,
        )

    def _get_error_info(self, error_id: str) -> ErrorLogInfo:
        """按 error_id 定位错误日志目录。

        Args:
            error_id: 错误目录名。

        Returns:
            错误目录信息。

        Raises:
            LogServiceError: 当目录名非法、越界或不存在时抛出。
        """
        if Path(error_id).name != error_id:
            raise LogServiceError(400, "LOG_ERROR_ID_INVALID", "Error id is not valid")
        path = ensure_child_path(ERROR_LOG_ROOT, ERROR_LOG_ROOT / error_id)
        if not path.exists() or not path.is_dir():
            raise LogServiceError(404, "LOG_ERROR_NOT_FOUND", "Error log does not exist")
        info = self._parse_error_dir(path)
        if info is None:
            raise LogServiceError(404, "LOG_ERROR_NOT_FOUND", "Error log does not exist")
        return info

    def _error_log_item(self, info: ErrorLogInfo) -> dict[str, Any]:
        """构造错误日志列表项。

        Args:
            info: 错误目录索引信息。

        Returns:
            列表接口返回的单个错误项。
        """
        log_path = info.path / "log.txt"
        images = list(info.path.glob("*.png"))
        return {
            "id": info.id,
            "directory": info.id,
            "script_name": info.script_name,
            "timestamp_ms": info.timestamp_ms,
            "time": self._timestamp_to_iso(info.timestamp_ms),
            "legacy": info.legacy,
            "log_size": log_path.stat().st_size if log_path.exists() else 0,
            "image_count": len(images),
        }

    @staticmethod
    def _error_log_date(info: ErrorLogInfo) -> date:
        """根据错误时间戳计算本地日期。

        Args:
            info: 错误目录索引信息。

        Returns:
            错误发生的本地日期。
        """
        return datetime.fromtimestamp(info.timestamp_ms / 1000).date()

    @staticmethod
    def _timestamp_to_iso(timestamp_ms: int) -> str:
        """把毫秒时间戳转换为本地 ISO 时间字符串。

        Args:
            timestamp_ms: 毫秒时间戳。

        Returns:
            带本地时区的 ISO 时间字符串。
        """
        return datetime.fromtimestamp(timestamp_ms / 1000).astimezone().isoformat(timespec="milliseconds")

    @staticmethod
    def _read_error_text(path: Path, limit_bytes: int) -> dict[str, Any]:
        """按字节上限读取错误日志文本。

        Args:
            path: `log.txt` 路径。
            limit_bytes: 最大读取字节数。

        Returns:
            日志文件名、内容、原始大小、限制值和截断标记。
        """
        if not path.exists() or not path.is_file():
            return {
                "file_name": "log.txt",
                "content": "",
                "size": 0,
                "limit_bytes": limit_bytes,
                "truncated": False,
            }
        size = path.stat().st_size
        with path.open("rb") as file:
            data = file.read(limit_bytes + 1)
        truncated = len(data) > limit_bytes
        if truncated:
            data = data[:limit_bytes]
        return {
            "file_name": "log.txt",
            "content": data.decode("utf-8", errors="ignore"),
            "size": size,
            "limit_bytes": limit_bytes,
            "truncated": truncated,
        }

    @staticmethod
    def _image_item(info: ErrorLogInfo, path: Path) -> dict[str, Any]:
        """构造错误截图元信息。

        Args:
            info: 所属错误目录信息。
            path: PNG 截图路径。

        Returns:
            图片名称、大小、修改时间和读取 URL。
        """
        stat = path.stat()
        return {
            "name": path.name,
            "size": stat.st_size,
            "modified_time": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).astimezone().isoformat(),
            "url": f"/logs/errors/{quote(info.id)}/images/{quote(path.name)}",
        }

    @staticmethod
    def _encode_error_cursor(offset: int) -> str:
        """编码错误日志列表分页 cursor。

        Args:
            offset: 下一页在过滤后列表中的起始下标。

        Returns:
            URL-safe base64 分页 cursor。
        """
        data = json.dumps(
            {"v": CURSOR_VERSION, "type": "error", "offset": int(offset)},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_error_cursor(cursor: str) -> int:
        """解码错误日志列表分页 cursor。

        Args:
            cursor: 前端回传的错误日志分页 cursor。

        Returns:
            下一页起始下标。

        Raises:
            LogServiceError: 当 cursor 格式或 offset 非法时抛出。
        """
        try:
            padding = "=" * (-len(cursor) % 4)
            payload = json.loads(base64.urlsafe_b64decode((cursor + padding).encode("ascii")).decode("utf-8"))
        except Exception as exc:
            raise LogServiceError(400, "LOG_CURSOR_INVALID", "Cursor is not valid") from exc
        if payload.get("v") != CURSOR_VERSION or payload.get("type") != "error":
            raise LogServiceError(400, "LOG_CURSOR_INVALID", "Cursor is not valid")
        try:
            offset = int(payload.get("offset"))
        except (TypeError, ValueError) as exc:
            raise LogServiceError(400, "LOG_CURSOR_INVALID", "Cursor offset is not valid") from exc
        if offset < 0:
            raise LogServiceError(400, "LOG_CURSOR_INVALID", "Cursor offset is not valid")
        return offset

    @staticmethod
    def _format_client_log_text(text: str) -> str:
        """格式化普通日志给前端展示。

        Args:
            text: 原始日志展示文本, 可以是单行日志或多行日志内容。

        Returns:
            逐行去掉源码位置, 并将 `YYYY-MM-DD HH:MM:SS.mmm` 转成 `MM-DD HH:MM:SS.mmm`。
            无法匹配的行原样返回。
        """
        lines = text.splitlines(True)
        if len(lines) > 1:
            return "".join(LogBrowserService._format_client_log_text(line) for line in lines)
        if " | " not in text:
            return text

        line_end = ""
        line = text
        if line.endswith("\r\n"):
            line, line_end = line[:-2], "\r\n"
        elif line.endswith("\n"):
            line, line_end = line[:-1], "\n"

        parts = line.split(" | ", 3)
        if len(parts) < 4:
            return text

        head, source, level, message = parts
        if not re.match(r"^\d{4}-\d{2}-\d{2} ", head):
            return text
        if not re.match(r"^\s*[^:]+:\d+$", source):
            return text

        return f"{head[5:]} | {level} | {message}{line_end}"


log_browser_service = LogBrowserService()
