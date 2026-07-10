"""Bridge Python's logging module to loguru."""

import logging

from loguru import logger


class InterceptHandler(logging.Handler):
    """Forward stdlib log records to loguru with preserved depth and exceptions."""

    def emit(self, record: logging.LogRecord) -> None:
        """Emit one logging record through loguru."""
        level = logger.level(record.levelname).name
        logger.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())
