from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

_DEFAULTS: dict[str, Any] = {
    "data_dir": "data",
    "users_file": "data/users.json",
    "portfolios_file": "data/portfolios.json",
    "rates_file": "data/rates.json",
    "rates_ttl_seconds": 300,
    "base_currency": "USD",
    "log_file": "logs/actions.log",
    "log_level": "INFO",
    "log_max_bytes": 1_048_576,
    "log_backup_count": 5,
    "log_format": "%(levelname)s %(message)s",
}

_PATH_KEYS = {
    "data_dir",
    "users_file",
    "portfolios_file",
    "rates_file",
    "log_file",
}


class SettingsLoader:
    _instance: SettingsLoader | None = None

    def __new__(cls) -> SettingsLoader:
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._root = Path(__file__).resolve().parents[3]
            instance._config: dict[str, Any] = {}
            instance.reload()
            cls._instance = instance
        return cls._instance

    def reload(self) -> None:
        raw = dict(_DEFAULTS)
        pyproject = self._root / "pyproject.toml"
        if pyproject.exists():
            with pyproject.open("rb") as file:
                document = tomllib.load(file)
            section = document.get("tool", {}).get("valutatrade", {})
            if isinstance(section, dict):
                raw.update(section)
        self._config = {
            key: self._normalize(key, value) for key, value in raw.items()
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def _normalize(self, key: str, value: Any) -> Any:
        if key in _PATH_KEYS:
            path = Path(value)
            if not path.is_absolute():
                path = self._root / path
            return path
        if key in {"rates_ttl_seconds", "log_max_bytes", "log_backup_count"}:
            return int(value)
        if key == "base_currency":
            return str(value).upper()
        if key == "log_level":
            return str(value).upper()
        return value
