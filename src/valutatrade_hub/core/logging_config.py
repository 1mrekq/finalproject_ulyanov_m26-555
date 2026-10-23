from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from valutatrade_hub.core.settings import SettingsLoader

_LOGGER_NAME = "valutatrade_hub.actions"
_configured = False


def setup_logging() -> logging.Logger:
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    if _configured:
        return logger

    settings = SettingsLoader()
    path = settings.get("log_file")
    path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        path,
        maxBytes=int(settings.get("log_max_bytes", 1_048_576)),
        backupCount=int(settings.get("log_backup_count", 5)),
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(settings.get("log_format")))
    logger.setLevel(_resolve_level(settings.get("log_level", "INFO")))
    logger.addHandler(handler)
    logger.propagate = False
    _configured = True

    return logger


def _resolve_level(name: str) -> int:
    level = logging.getLevelName(str(name).upper())
    if isinstance(level, int):
        return level
        
    return logging.INFO
