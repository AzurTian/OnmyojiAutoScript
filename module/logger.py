# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import sys

import logging
import os
import re
import shutil
from datetime import datetime, timedelta, date
from io import TextIOBase
from pathlib import Path
from rich.console import Console, ConsoleOptions, ConsoleRenderable, NewLine, RenderResult
from rich.highlighter import NullHighlighter
from rich.logging import RichHandler
from rich.rule import Rule
from typing import Callable, List


def cleanup_logs(log_dir: str = "./log", keep_days: int = 7):
    """删除 log_dir 下所有早于 keep_days 的文件夹和文件"""
    log_path = Path(log_dir)
    if not log_path.exists():
        return  # 目录都没有，直接退出
    keep_days_ago_ts = (datetime.now() - timedelta(days=keep_days)).timestamp()
    for name in os.listdir(log_path):
        full_path = os.path.join(log_path, name)
        # 忽略软链接，仅处理文件和目录
        if not os.path.exists(full_path):
            continue
        if os.path.isfile(full_path):
            # 处理 log 根目录下超过keep_days的文件
            try:
                if os.path.getmtime(full_path) < keep_days_ago_ts:
                    os.remove(full_path)
            except OSError as e:
                logger.error(f"delete file '{full_path}' error: {e}")
        elif os.path.isdir(full_path):
            # 检查是否为 error 目录
            if name != 'error':
                continue
            for error_dir_name in os.listdir(full_path):
                error_dir_path = os.path.join(full_path, error_dir_name)
                if not os.path.isdir(error_dir_path):
                    continue
                # 处理 log/error 根目录下超过keep_days的文件夹
                try:
                    if os.path.getmtime(error_dir_path) < keep_days_ago_ts:
                        # 递归删除整个目录及其内容
                        shutil.rmtree(error_dir_path)
                except OSError as e:
                    logger.error(f"delete dir '{error_dir_path}' error: {e}")


def empty_function(*args, **kwargs):
    pass


# Ensure running in Alas root folder
os.chdir(os.path.join(os.path.dirname(__file__), '../'))
# cnocr will set root logger in cnocr.utils
# Delete logging.basicConfig to avoid logging the same message twice.
logging.basicConfig = empty_function
logging.raiseExceptions = True  # Set True if wanna see encode errors on console

# Remove HTTP keywords (GET, POST etc.)
# RichHandler.KEYWORDS = []


# def show_handlers(handlers):
#     # 获取并打印日志记录器中处理器的信息
#     for handler in logger.handlers:
#         # 获取处理器的类名
#         handler_class = handler.__class__.__name__
#         print(f"Handler class: {handler_class}")
#
#         # 获取处理器的级别
#         handler_level = logging.getLevelName(handler.level)
#         print(f"Handler level: {handler_level}")
#
#         # 获取处理器的格式化器
#         formatter = handler.formatter
#         if formatter is not None:
#             formatter_class = formatter.__class__.__name__
#             print(f"Formatter class: {formatter_class}")
#
#         # 其他处理器的属性和方法，根据需要进行获取和打印
#         print()  # 打印空行，用于分隔处理器的信息


# Logger init
logger_debug = False
logger = logging.getLogger('oas')
logger.setLevel(logging.DEBUG if logger_debug else logging.INFO)
file_formatter = logging.Formatter(
    fmt='%(asctime)s.%(msecs)03d | %(filename)20s:%(lineno)04d | %(levelname)8s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
console_formatter = logging.Formatter(
    fmt='%(asctime)s.%(msecs)03d │ %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
flutter_formatter = logging.Formatter(
    fmt='| %(asctime)s.%(msecs)03d | %(message)08s', datefmt='%H:%M:%S')


# ======================================================================================================================
#            Set console logger
# ======================================================================================================================
console_hdlr = RichHandler(
    console=Console(
        width=120
    ),
    show_path=False,
    show_time=False,
    rich_tracebacks=True,
    tracebacks_show_locals=True,
    tracebacks_extra_lines=3,
    tracebacks_width=160
)
console_hdlr.setFormatter(console_formatter)
logger.addHandler(console_hdlr)


# ======================================================================================================================
#            Set file
# ======================================================================================================================
_UNSAFE_LOG_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def normalize_log_name(name: str) -> str:
    """标准化日志文件中的脚本名。

    Args:
        name: 脚本配置名或外部传入的日志名。

    Returns:
        去掉运行时后缀并移除路径危险字符后的日志名。
    """
    name = str(name or "").strip()
    if '_' in name:
        name = name.split('_', 1)[0]
    name = _UNSAFE_LOG_NAME_RE.sub("_", name).replace("..", "_").strip(" .")
    return name or "script"


class RichFileHandler(RichHandler):
    """支持跨天自动轮转的 Rich 文件日志处理器。

    Args:
        script_name: 当前 handler 绑定的脚本名, 用于生成 `log/YYYY-MM-DD_<script>.txt`。
        log_date: 当前 handler 绑定的日志日期; 写入前会和当天日期比较。
        log_file: 当前日志文件路径字符串, 会同步到 `logger.log_file`。
        file: 当前 Rich Console 正在写入的文件对象。
        *args: 传给 RichHandler 的位置参数。
        **kwargs: 传给 RichHandler 的关键字参数。
    """

    def __init__(self, *args, script_name: str = "", log_date: date = None, log_file: str = "", file=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.script_name = normalize_log_name(script_name)
        self.log_date = log_date or date.today()
        self.log_file = log_file
        self._file = file
        self._last_saved_content: str | None = None

    def emit(self, record: logging.LogRecord) -> None:
        """写入日志记录, 写入前检查是否需要跨天切换文件。

        Args:
            record: Python logging 生成的日志记录。
        """
        self._rotate_if_needed()
        content = self._record_content(record)
        if self._is_duplicate_content(content):
            return
        super().emit(record)
        self._last_saved_content = content

    def close(self) -> None:
        """关闭 handler 并释放当前日志文件句柄。"""
        self._close_file()
        super().close()

    def _rotate_if_needed(self) -> None:
        """当本地日期变化时切换到当天脚本日志文件。"""
        today = date.today()
        if today == self.log_date:
            return

        log_path = Path("./log")
        log_path.mkdir(parents=True, exist_ok=True)
        log_file = f'./log/{today}_{self.script_name}.txt'
        new_file = open(log_file, mode='a', encoding='utf-8')
        old_file = self._file
        self.console.file = new_file
        self._file = new_file
        self.log_date = today
        self.log_file = log_file
        logger.log_file = log_file
        self._last_saved_content = None

        try:
            if old_file is not None:
                old_file.flush()
                old_file.close()
        except Exception:
            pass

    def _close_file(self) -> None:
        """刷新并关闭当前 handler 持有的文件对象。"""
        if self._file is None:
            return
        try:
            self._file.flush()
            self._file.close()
        except Exception:
            pass
        self._file = None

    def _record_content(self, record: logging.LogRecord) -> str:
        """提取用于文件日志去重的正文内容。

        Args:
            record: Python logging 生成的日志记录。

        Returns:
            不包含时间戳、源码位置和级别的日志正文; 异常日志会把 traceback 纳入比较,
            避免不同异常现场因为同一条 message 被误删。
        """
        content = f"{record.levelname}|{record.getMessage()}"
        if record.exc_info and self.formatter is not None:
            content = f"{content}\n{self.formatter.formatException(record.exc_info)}"
        return content

    def _is_duplicate_content(self, content: str) -> bool:
        """判断当前日志正文是否与上一条已保存日志重复。

        Args:
            content: 当前准备写入文件的日志正文。

        Returns:
            True 表示该日志与上一条已保存日志相同, 本次不再写入文件。
        """
        return content == self._last_saved_content

    def save_print_content(self, content: str) -> bool:
        """记录 Rich print 输出并判断是否需要保存。

        Args:
            content: 通过 `logger.print()` 写入文件前提取出的展示文本。

        Returns:
            True 表示内容不是上一条已保存内容, 调用方应继续写入文件。
        """
        # print 输出没有 logging record, 这里按最终展示文本做连续去重。
        if self._is_duplicate_content(content):
            return False
        self._last_saved_content = content
        return True


# Add file logger
pyw_name = os.path.splitext(os.path.basename(sys.argv[0]))[0]


def set_file_logger(name=pyw_name, *, do_cleanup=False):
    """设置当前进程的脚本文件日志。

    Args:
        name: 脚本配置名, 会用于生成 `log/YYYY-MM-DD_<name>.txt`。
        do_cleanup: 是否在设置文件日志后清理过期日志和错误目录。
    """
    name = normalize_log_name(name)
    today = date.today()
    log_file = f'./log/{today}_{name}.txt'
    try:
        file = open(log_file, mode='a', encoding='utf-8')
    except FileNotFoundError:
        os.mkdir('./log')
        file = open(log_file, mode='a', encoding='utf-8')

    file_console = Console(
        file=file,
        no_color=True,
        highlight=False,
        width=160,
    ) 

    hdlr = RichFileHandler(
        console=file_console,
        show_path=False,
        show_time=False,
        show_level=False,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        tracebacks_extra_lines=3,
        tracebacks_width=160,
        highlighter=NullHighlighter(),
        script_name=name,
        log_date=today,
        log_file=log_file,
        file=file,
    )
    hdlr.setFormatter(file_formatter)

    for h in list(logger.handlers):
        if isinstance(h, (logging.FileHandler, RichFileHandler)):
            logger.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass
    logger.addHandler(hdlr)
    logger.log_file = log_file

    # ---------- 可选：清理旧文件 ----------
    if do_cleanup:
        cleanup_logs()
        logger.info("Log cleanup finished")


# ======================================================================================================================
#            Set flutter
# ======================================================================================================================
class FlutterHandler(RichHandler):
    # Rename
    pass


class FlutterConsole(Console):
    """
    Force full feature console
    but not working lol :(
    """

    @property
    def options(self) -> ConsoleOptions:
        return ConsoleOptions(
            max_height=self.size.height,
            size=self.size,
            legacy_windows=False,
            min_width=1,
            max_width=self.width,
            encoding='utf-8',
            is_terminal=False,
        )


class FlutterLogStream(TextIOBase):
    def __init__(self, *args, func: Callable[[ConsoleRenderable], None] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._func = func

    def write(self, msg: str) -> int:
        if isinstance(msg, bytes):
            msg = msg.decode("utf-8")
        self._func(msg)
        return len(msg)


def set_func_logger(func):
    stream = FlutterLogStream(func=func)
    stream_console = Console(
        file=stream,
        force_terminal=False,
        force_interactive=False,
        no_color=True,
        highlight=False,
        width=80,
    )
    hdlr = FlutterHandler(
        console=stream_console,
        show_path=False,
        show_time=False,
        show_level=True,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        tracebacks_extra_lines=3,
        highlighter=NullHighlighter(),
    )
    hdlr.setFormatter(flutter_formatter)
    logger.addHandler(hdlr)

# ======================================================================================================================
#            Set print format
# ======================================================================================================================


def _get_renderables(
        self: Console, *objects, sep=" ", end="\n", justify=None, emoji=None, markup=None, highlight=None,
) -> List[ConsoleRenderable]:
    """
    Refer to rich.console.Console.print()
    """
    if not objects:
        objects = (NewLine(),)

    render_hooks = self._render_hooks[:]
    with self:
        renderables = self._collect_renderables(
            objects,
            sep,
            end,
            justify=justify,
            emoji=emoji,
            markup=markup,
            highlight=highlight,
        )
        for hook in render_hooks:
            renderables = hook.process_renderables(renderables)
    return renderables


def print(*objects: ConsoleRenderable, **kwargs):
    for hdlr in logger.handlers:
        if isinstance(hdlr, FlutterHandler):
            for renderable in _get_renderables(hdlr.console, *objects, **kwargs):
                hdlr.console.file._func(str(renderable))
        elif isinstance(hdlr, RichHandler):
            if isinstance(hdlr, RichFileHandler):
                hdlr._rotate_if_needed()
                content = "".join(str(renderable) for renderable in _get_renderables(hdlr.console, *objects, **kwargs))
                if not hdlr.save_print_content(content):
                    continue
            hdlr.console.print(*objects)


class GuiRule(Rule):
    def __rich_console__(
            self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        options.max_width = 80
        return super().__rich_console__(console, options)

    def __str__(self):
        total_width = 80
        cell_len = len(self.title) + 2
        aside_len = (total_width - cell_len) // 2
        left = self.characters * aside_len
        right = self.characters * (total_width - cell_len - aside_len)
        if self.title:
            space = ' '
        else:
            space = self.characters
        return f"{left}{space}{self.title}{space}{right}\n"

    def __repr__(self):
        return self.__str__()


def rule(title="", *, characters="─", style="rule.line", end="\n", align="center"):
    rule = GuiRule(title=title, characters=characters,
                   style=style, end=end)
    print(rule)


def hr(title, level=3):
    title = str(title).upper()
    if level == 1:
        logger.rule(title, characters='═')
        logger.info(title)
    if level == 2:
        logger.rule(title, characters='─')
        logger.info(title)
    if level == 3:
        logger.info(f"[bold]<<< {title} >>>[/bold]", extra={"markup": True})
    if level == 0:
        logger.rule(characters='═')
        logger.rule(title, characters='─')
        logger.rule(characters='═')


def attr(name, text):
    logger.info('[%s] %s' % (str(name), str(text)))


def attr_align(name, text, front='', align=22):
    name = str(name).rjust(align)
    if front:
        name = front + name[len(front):]
    logger.info('%s: %s' % (name, str(text)))


def show():
    logger.info('INFO')
    logger.warning('WARNING')
    logger.debug('DEBUG')
    logger.error('ERROR')
    logger.critical('CRITICAL')
    logger.hr('hr0', 0)
    logger.hr('hr1', 1)
    logger.hr('hr2', 2)
    logger.hr('hr3', 3)
    logger.info(r'Brace { [ ( ) ] }')
    logger.info(r'True, False, None')
    logger.info(r'E:/path\\to/alas/alas.exe, /root/alas/, ./relative/path/log.txt')
    logger.info('Tests very long strings. Tests very long strings. Tests very long strings. Tests very long strings. Tests very long strings.')
    local_var1 = 'This is local variable'
    # Line before exception
    raise Exception("Exception")
    # Line below exception


def error_convert(func):
    def error_wrapper(msg, *args, **kwargs):
        if isinstance(msg, Exception):
            msg = f'{type(msg).__name__}: {msg}'
        return func(msg, *args, **kwargs)

    return error_wrapper


logger.error = error_convert(logger.error)
logger.hr = hr
logger.attr = attr
logger.attr_align = attr_align
logger.set_file_logger = set_file_logger
logger.set_func_logger = set_func_logger
logger.rule = rule
logger.print = print
logger.log_file: str

logger.set_file_logger()
logger.hr('Start', level=0)
