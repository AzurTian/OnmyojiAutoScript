# This Python file uses the following encoding: utf-8
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from module.server.api_logger import ApiLoggingRoute
from module.server.log_service import (
    DEFAULT_ERROR_LIMIT,
    MAX_ERROR_LIMIT,
    MAX_ERROR_LOG_LIMIT_BYTES,
    MAX_LIMIT_BYTES,
    MAX_LIMIT_LINES,
    MAX_STREAM_LIMIT_BYTES,
    MAX_STREAM_LIMIT_LINES,
    MIN_LIMIT_BYTES,
    log_browser_service,
    LogServiceError,
)


log_app = APIRouter(
    prefix="/logs",
    tags=["logs"],
    route_class=ApiLoggingRoute,
)


class LogPosition(BaseModel):
    """日志窗口中单个位置的描述。"""

    file_name: str | None = Field(default=None, description="位置所在的日志文件名")
    offset: int | None = Field(default=None, description="位置所在的文件字节偏移量")
    line_no: int | None = Field(default=None, description="位置对应的日志行号")


class LogLine(BaseModel):
    """前端直接渲染的单行日志结构。"""

    file_name: str = Field(description="该行所属日志文件名")
    line_no: int = Field(description="该行在文件中的行号")
    offset: int = Field(description="该行在文件中的起始字节偏移量")
    byte_length: int = Field(description="该行原始字节长度, 包含行尾换行符")
    text: str = Field(description="该行可展示文本")
    line_truncated: bool = Field(description="该行展示文本是否因超过 max_line_bytes 被截断")


class LogWindowLimits(BaseModel):
    """日志窗口的限制参数回显。"""

    limit_lines: int = Field(description="本次窗口的行数上限")
    limit_bytes: int = Field(description="本次窗口的字节上限")
    max_line_bytes: int = Field(description="单行展示文本的安全截断上限")


class LogWindowResponse(BaseModel):
    """脚本日志主窗口响应。"""

    script_name: str = Field(description="标准化后的脚本名")
    window: dict[str, LogPosition | None] = Field(description="当前窗口的 from/to 首尾位置")
    older_cursor: str | None = Field(default=None, description="继续向更旧日志回翻使用的 cursor")
    live_cursor: str = Field(description="订阅实时追加日志使用的 cursor")
    has_older: bool = Field(description="是否仍有更旧日志可继续回翻")
    reached_start: bool = Field(description="是否已经到达该脚本日志起点")
    limits: LogWindowLimits = Field(description="本次生效的窗口限制")
    lines: list[LogLine] = Field(default_factory=list, description="按旧到新顺序返回的完整日志行")


class ErrorLogItem(BaseModel):
    """错误日志列表中的单个目录项。"""

    id: str = Field(description="错误目录名, 也是详情接口的 error_id")
    directory: str = Field(description="错误目录名")
    script_name: str | None = Field(default=None, description="错误所属脚本名; 旧目录没有脚本名时为 null")
    timestamp_ms: int = Field(description="错误目录中的毫秒时间戳")
    time: str = Field(description="错误时间, 带本地时区的 ISO 字符串")
    legacy: bool = Field(description="是否为旧格式纯时间戳目录")
    log_size: int = Field(description="错误目录下 log.txt 的字节数")
    image_count: int = Field(description="错误目录下 PNG 截图数量")


class ErrorLogListResponse(BaseModel):
    """错误日志列表响应。"""

    date: str | None = Field(default=None, description="本次查询的日期; 不传 date 时为 null")
    script_name: str | None = Field(default=None, description="本次查询使用的脚本名过滤条件")
    items: list[ErrorLogItem] = Field(default_factory=list, description="错误日志目录列表")
    next_cursor: str | None = Field(default=None, description="下一页分页 cursor, 没有更多数据时为 null")
    has_more: bool = Field(default=False, description="是否还有下一页")


class ErrorLogText(BaseModel):
    """错误目录中 `log.txt` 的返回内容。"""

    file_name: str = Field(description="日志文件名, 固定为 log.txt")
    content: str = Field(description="日志文本内容")
    size: int = Field(description="log.txt 原始字节数")
    limit_bytes: int = Field(description="本次读取使用的字节上限")
    truncated: bool = Field(description="日志内容是否因超过 limit_bytes 被截断")


class ErrorImageInfo(BaseModel):
    """错误目录中单张截图的元信息。"""

    name: str = Field(description="PNG 截图文件名")
    size: int = Field(description="截图文件字节数")
    modified_time: str = Field(description="截图文件修改时间")
    url: str = Field(description="读取该截图的接口 URL")


class ErrorDetailResponse(BaseModel):
    """错误日志详情响应。"""

    id: str = Field(description="错误目录名, 也是 error_id")
    directory: str = Field(description="错误目录名")
    script_name: str | None = Field(default=None, description="错误所属脚本名; 旧目录没有脚本名时为 null")
    timestamp_ms: int = Field(description="错误目录中的毫秒时间戳")
    time: str = Field(description="错误时间, 带本地时区的 ISO 字符串")
    legacy: bool = Field(description="是否为旧格式纯时间戳目录")
    log: ErrorLogText = Field(description="错误目录下 log.txt 的内容")
    images: list[ErrorImageInfo] = Field(default_factory=list, description="错误目录下的 PNG 截图元信息")


def _raise_log_error(exc: LogServiceError) -> None:
    """把服务层异常转换成 HTTPException。

    Args:
        exc: 日志服务抛出的业务异常。
    """
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc


@log_app.get("/errors", response_model=ErrorLogListResponse)
async def get_error_logs(
    date_text: str | None = Query(default=None, alias="date", description="目标日期, 格式为 YYYY-MM-DD, 不传则不过滤日期"),
    script_name: str | None = Query(default=None, description="可选脚本名过滤条件"),
    limit: int = Query(default=DEFAULT_ERROR_LIMIT, ge=1, le=MAX_ERROR_LIMIT, description="单页最多返回的错误目录数量"),
    cursor: str | None = Query(default=None, description="上一页返回的分页 cursor"),
):
    """查询错误日志列表。

    不传 `date` 时, 返回对应脚本名的全部错误日志列表。
    """
    try:
        return log_browser_service.list_error_logs(
            date_text=date_text,
            script_name=script_name,
            limit=limit,
            cursor=cursor,
        )
    except LogServiceError as exc:
        _raise_log_error(exc)


@log_app.get("/errors/{error_id}", response_model=ErrorDetailResponse)
async def get_error_log_detail(
    error_id: str = Path(description="错误目录名, 支持 <script_name>_<timestamp_ms> 和旧格式 <timestamp_ms>"),
    log_limit_bytes: int = Query(
        default=262144,
        ge=1,
        le=MAX_ERROR_LOG_LIMIT_BYTES,
        description="log.txt 最多返回的字节数",
    ),
):
    """查询单个错误目录的详情。"""
    try:
        return log_browser_service.get_error_detail(error_id, log_limit_bytes=log_limit_bytes)
    except LogServiceError as exc:
        _raise_log_error(exc)


@log_app.get("/errors/{error_id}/images/{image_name}")
async def get_error_log_image(
    error_id: str = Path(description="错误目录名"),
    image_name: str = Path(description="错误目录下的 PNG 截图文件名"),
):
    """读取单张错误截图。"""
    try:
        image_path = log_browser_service.get_error_image_path(error_id, image_name)
    except LogServiceError as exc:
        _raise_log_error(exc)
    return FileResponse(str(image_path), media_type="image/png")


@log_app.get("/{script_name}", response_model=LogWindowResponse)
async def get_log_window(
    script_name: str = Path(description="脚本配置名或日志脚本名"),
    cursor: str | None = Query(default=None, description="上一页返回的 older_cursor; 不传表示打开最新窗口"),
    limit_lines: int = Query(default=500, ge=1, le=MAX_LIMIT_LINES, description="本次最多返回的日志行数"),
    limit_bytes: int = Query(default=262144, ge=MIN_LIMIT_BYTES, le=MAX_LIMIT_BYTES, description="本次最多返回的日志字节数"),
):
    """读取脚本日志的最新窗口或更旧窗口。"""
    try:
        return log_browser_service.read_window(
            script_name=script_name,
            cursor=cursor,
            limit_lines=limit_lines,
            limit_bytes=limit_bytes,
        )
    except LogServiceError as exc:
        _raise_log_error(exc)


@log_app.get("/{script_name}/stream")
async def get_log_stream(
    script_name: str = Path(description="脚本配置名或日志脚本名"),
    cursor: str | None = Query(default=None, description="上一窗口返回的 live_cursor; 不传表示从当前最新位置开始订阅"),
    limit_lines: int = Query(default=200, ge=1, le=MAX_STREAM_LIMIT_LINES, description="单个 append 事件最多返回的行数"),
    limit_bytes: int = Query(default=131072, ge=MIN_LIMIT_BYTES, le=MAX_STREAM_LIMIT_BYTES, description="单个 append 事件最多返回的字节数"),
):
    """订阅脚本最新日志的 SSE 流。"""
    async def event_stream():
        """把日志服务生成的 SSE 字符串转交给 StreamingResponse。"""
        async for event in log_browser_service.stream_events(
            script_name=script_name,
            cursor=cursor,
            limit_lines=limit_lines,
            limit_bytes=limit_bytes,
        ):
            yield event

    response = StreamingResponse(event_stream(), media_type="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Connection"] = "keep-alive"
    response.headers["X-Accel-Buffering"] = "no"
    return response
