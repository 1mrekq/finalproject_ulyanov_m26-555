import hashlib
import re
import secrets
from datetime import datetime

from valutatrade_hub.core.constants import CRYPTO_CODES

_CURRENCY_CODE = re.compile(r"[A-Z0-9]{2,5}")


def generate_salt() -> str:
    return secrets.token_hex(8)


def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{password}{salt}".encode("utf-8")).hexdigest()


def normalize_currency(currency_code: str) -> str:
    if not isinstance(currency_code, str) or not currency_code.strip():
        raise ValueError("Код валюты должен быть непустой строкой")
    if " " in currency_code.strip():
        raise ValueError("Код валюты должен содержать 2–5 символов без пробелов")
    normalized = currency_code.strip().upper()
    if not _CURRENCY_CODE.fullmatch(normalized):
        raise ValueError("Код валюты должен содержать 2–5 символов без пробелов")
    return normalized


def convert_by_rate(amount: float, rate: float) -> float:
    return float(amount) * float(rate)


def parse_amount(value) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise ValueError("'amount' должен быть положительным числом") from None
    if isinstance(value, bool) or amount <= 0:
        raise ValueError("'amount' должен быть положительным числом")
    return amount


def is_positive_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def format_amount(currency_code: str, amount: float) -> str:
    decimals = 4 if currency_code in CRYPTO_CODES else 2
    return f"{amount:.{decimals}f}"


def parse_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise ValueError("Некорректная дата")


def format_datetime(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()
