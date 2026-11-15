import logging
import os
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

LOG_PATH = os.path.join(os.path.expanduser("~"), "ambilight_studio.log")


class _RateLimitFilter(logging.Filter):
    """Блокує спам однакових помилок частіше ніж раз на 10 секунд."""
    def __init__(self, cooldown: float = 10.0):
        super().__init__()
        self.cooldown = cooldown
        self._last_seen = {}

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < logging.WARNING:
            return True
        key = (record.name, record.levelno, record.getMessage())
        now = time.monotonic()
        prev = self._last_seen.get(key, 0.0)
        if now - prev >= self.cooldown:
            self._last_seen[key] = now
            return True
        return False


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("AmbilightStudio")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        LOG_PATH, maxBytes=1_048_576, backupCount=2, encoding="utf-8"
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    handler.addFilter(_RateLimitFilter(cooldown=10.0))
    logger.addHandler(handler)

    def _sys_hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical("Необроблена помилка головного потоку", exc_info=(exc_type, exc_value, exc_tb))

    def _thread_hook(args):
        logger.critical(
            f"Падіння фонового потоку '{args.thread.name}'",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback)
        )

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook
    logger.info("=== Запуск Ambilight Studio ===")
    return logger


def get_logger(module_name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(f"AmbilightStudio.{module_name}")
