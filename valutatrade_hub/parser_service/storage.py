import json
import os
import tempfile
from pathlib import Path

from valutatrade_hub.infra.database import extract_rate_pairs
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.api_clients import RateQuote
from valutatrade_hub.parser_service.config import ParserConfig


def last_refresh_of(data: dict | None) -> str | None:
    if not isinstance(data, dict):
        return None
    stamp = data.get("last_refresh")
    return stamp if isinstance(stamp, str) and stamp else None


def _is_newer(incoming, current) -> bool:
    if not incoming:
        return False
    if not current:
        return True
    return str(incoming) >= str(current)


class RatesStorage:
    """Атомарная запись кэша rates.json и истории exchange_rates.json."""

    def __init__(
        self,
        config: ParserConfig | None = None,
        settings: SettingsLoader | None = None,
    ):
        self.config = config or ParserConfig()
        self.settings = settings or SettingsLoader()
        root = Path(self.settings.get("data_dir")).resolve().parent
        self.rates_path = self._resolve_path(
            self.settings.get("rates_file"),
            self.config.RATES_FILE_PATH,
            root,
        )
        self.history_path = self._resolve_path(
            self.settings.get("exchange_rates_file"),
            self.config.HISTORY_FILE_PATH,
            root,
        )

    def load_cache(self) -> dict:
        return self._load_json(self.rates_path) or {}

    def save_quotes(self, quotes: list[RateQuote], last_refresh: str) -> int:
        if not quotes:
            return 0
        current = extract_rate_pairs(self.load_cache())
        written = 0
        for quote in quotes:
            incoming = quote.to_cache_entry()
            existing = current.get(quote.pair)
            if isinstance(existing, dict) and not _is_newer(
                incoming.get("updated_at"), existing.get("updated_at")
            ):
                continue
            current[quote.pair] = incoming
            written += 1
        payload = {"pairs": current, "last_refresh": last_refresh}
        self._atomic_write(self.rates_path, payload)
        self._append_history([quote.to_history_record() for quote in quotes])
        return written

    def _append_history(self, records: list[dict]) -> None:
        data = self._load_json(self.history_path)
        if isinstance(data, list):
            existing = data
        elif isinstance(data, dict) and isinstance(data.get("records"), list):
            existing = data["records"]
        else:
            existing = []
        known = {item.get("id") for item in existing if isinstance(item, dict)}
        for record in records:
            record_id = record.get("id")
            if record_id in known:
                continue
            existing.append(record)
            known.add(record_id)
        self._atomic_write(self.history_path, {"records": existing})

    def _resolve_path(self, configured, fallback: str, root: Path) -> Path:
        if isinstance(configured, Path):
            return configured
        path = Path(configured or fallback)
        if not path.is_absolute():
            path = root / path
        return path

    def _load_json(self, path: Path):
        try:
            with path.open(encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            return None

    def _atomic_write(self, path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, tmp_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
