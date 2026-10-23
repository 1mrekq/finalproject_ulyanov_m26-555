import os
from dataclasses import dataclass, field
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_env_file() -> None:
    env_path = _project_root() / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


_load_env_file()


def _crypto_id_map() -> dict[str, str]:
    return {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
    }


@dataclass
class ParserConfig:
    """Параметры Parser Service: ключ из env, списки валют, URL, таймаут и пути."""

    EXCHANGERATE_API_KEY: str = field(
        default_factory=lambda: os.getenv("EXCHANGERATE_API_KEY", "")
    )
    COINGECKO_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL: str = "https://v6.exchangerate-api.com/v6"
    BASE_CURRENCY: str = "USD"
    FIAT_CURRENCIES: tuple[str, ...] = ("EUR", "GBP", "RUB")
    CRYPTO_CURRENCIES: tuple[str, ...] = ("BTC", "ETH", "SOL")
    CRYPTO_ID_MAP: dict[str, str] = field(default_factory=_crypto_id_map)
    RATES_FILE_PATH: str = "data/rates.json"
    HISTORY_FILE_PATH: str = "data/exchange_rates.json"
    REQUEST_TIMEOUT: int = 10
    UPDATE_INTERVAL_SECONDS: int = 300
    USER_AGENT: str = "ValutaTradeHub/0.1 (Parser Service)"
