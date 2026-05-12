# This Python file uses the following encoding: utf-8

from datetime import datetime

from module.logger import logger

SERVER_UPDATE_BLOCK_START_HOUR = 7
SERVER_UPDATE_BLOCK_END_HOUR = 9
SERVER_UPDATE_RESUME_HOUR = 9
SERVER_UPDATE_RESUME_MINUTE = 15


def is_server_update_window(now: datetime | None = None) -> bool:
    if now is None:
        now = datetime.now()
    return SERVER_UPDATE_BLOCK_START_HOUR <= now.hour < SERVER_UPDATE_BLOCK_END_HOUR


def build_server_update_delay_target(now: datetime | None = None) -> datetime:
    if now is None:
        now = datetime.now()
    return now.replace(
        hour=SERVER_UPDATE_RESUME_HOUR,
        minute=SERVER_UPDATE_RESUME_MINUTE,
        second=0,
        microsecond=0,
    )


def delay_pending_tasks_for_server_update(config, reason: str) -> datetime:
    delay_target = build_server_update_delay_target()
    logger.info(
        f'Detect possible server update because {reason}, '
        f'delay pending tasks until {delay_target.strftime("%Y-%m-%d %H:%M:%S")}'
    )
    logger.warning('Delay pending tasks')

    config.update_scheduler()
    delayed = set()
    for pending_task in getattr(config, 'pending_task', []):
        command = pending_task.command
        if command in delayed:
            continue
        config.task_delay(task=command, server=False, target=delay_target)
        delayed.add(command)

    config.task_delay(task='Restart', success=True, server=True)
    return delay_target
