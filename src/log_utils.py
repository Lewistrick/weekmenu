import logging

from loguru import logger


class InterceptHandler(logging.Handler):
    def emit(self, record):
        level = logger.level(record.levelname).name
        logger.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())
