import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from valutatrade_hub.infra.settings import SettingsLoader

_LOGGER_NAME = "valutatrade_hub.actions"
_PARSER_LOGGER_NAME = "valutatrade_hub.parser"
_configured = False
_parser_configured = False


class JsonLogFormatter(logging.Formatter):
    """Одна JSON-строка на событие: time, level, logger, message."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


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
    handler.setFormatter(_build_formatter(settings.get("log_format")))
    logger.setLevel(_resolve_level(settings.get("log_level", "INFO")))
    logger.addHandler(handler)
    logger.propagate = False
    _configured = True

    return logger


def setup_parser_logging() -> logging.Logger:
    global _parser_configured
    logger = logging.getLogger(_PARSER_LOGGER_NAME)
    if _parser_configured:
        return logger

    settings = SettingsLoader()
    path = settings.get("parser_log_file")
    path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        path,
        maxBytes=int(settings.get("log_max_bytes", 1_048_576)),
        backupCount=int(settings.get("log_backup_count", 5)),
        encoding="utf-8",
    )
    handler.setFormatter(_build_formatter(settings.get("log_format")))
    logger.setLevel(_resolve_level(settings.get("log_level", "INFO")))
    logger.addHandler(handler)
    logger.propagate = False
    _parser_configured = True
    return logger


def _build_formatter(log_format) -> logging.Formatter:
    value = str(log_format or "text").strip().lower()
    if value in {"json", "jsonl"}:
        return JsonLogFormatter()
    if value in {"text", "string", "str"}:
        return logging.Formatter("%(levelname)s %(message)s")
    return logging.Formatter(str(log_format))


def _resolve_level(name: str) -> int:
    level = logging.getLevelName(str(name).upper())
    if isinstance(level, int):
        return level
    return logging.INFO
