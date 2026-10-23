import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import ParserConfig


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def parse_api_timestamp(value: str | None) -> str:
    if not value:
        return utc_now_iso()
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return utc_now_iso()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (
        parsed.astimezone(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


@dataclass
class RateQuote:
    from_currency: str
    to_currency: str
    rate: float
    timestamp: str
    source: str
    meta: dict = field(default_factory=dict)

    @property
    def pair(self) -> str:
        return f"{self.from_currency}_{self.to_currency}"

    @property
    def record_id(self) -> str:
        return f"{self.from_currency}_{self.to_currency}_{self.timestamp}"

    def to_history_record(self) -> dict:
        return {
            "id": self.record_id,
            "from_currency": self.from_currency,
            "to_currency": self.to_currency,
            "rate": self.rate,
            "timestamp": self.timestamp,
            "source": self.source,
            "meta": self.meta,
        }

    def to_cache_entry(self) -> dict:
        return {
            "rate": self.rate,
            "updated_at": self.timestamp,
            "source": self.source,
        }


class BaseApiClient(ABC):
    source_name: str

    @abstractmethod
    def fetch_rates(self) -> dict[str, RateQuote]:
        """Возвращает пары вида BTC_USD -> RateQuote."""


class CoinGeckoClient(BaseApiClient):
    source_name = "CoinGecko"

    def __init__(self, config: ParserConfig | None = None):
        self.config = config or ParserConfig()

    def fetch_rates(self) -> dict[str, RateQuote]:
        id_to_code = {
            coin_id: code
            for code, coin_id in self.config.CRYPTO_ID_MAP.items()
            if code in self.config.CRYPTO_CURRENCIES
        }
        if not id_to_code:
            raise ApiRequestError("не задан список криптовалют для CoinGecko")

        params = {
            "ids": ",".join(id_to_code),
            "vs_currencies": self.config.BASE_CURRENCY.lower(),
        }
        payload, status_code, elapsed_ms, etag = _get_json(
            self.config.COINGECKO_URL,
            timeout=self.config.REQUEST_TIMEOUT,
            params=params,
            headers={
                "User-Agent": self.config.USER_AGENT,
                "Accept": "application/json",
            },
            source=self.source_name,
        )
        if not isinstance(payload, dict):
            raise ApiRequestError("CoinGecko вернул неожиданный формат ответа")

        timestamp = utc_now_iso()
        quotes: dict[str, RateQuote] = {}
        vs = self.config.BASE_CURRENCY.lower()
        base = self.config.BASE_CURRENCY.upper()
        for coin_id, code in id_to_code.items():
            item = payload.get(coin_id)
            if not isinstance(item, dict) or vs not in item:
                continue
            try:
                rate = float(item[vs])
            except (TypeError, ValueError) as error:
                raise ApiRequestError(
                    f"CoinGecko вернул нечисловой курс для {code}"
                ) from error
            if rate <= 0:
                continue
            quote = RateQuote(
                from_currency=code,
                to_currency=base,
                rate=rate,
                timestamp=timestamp,
                source=self.source_name,
                meta={
                    "raw_id": coin_id,
                    "request_ms": elapsed_ms,
                    "status_code": status_code,
                    "etag": etag,
                },
            )
            quotes[quote.pair] = quote
        if not quotes:
            raise ApiRequestError("CoinGecko не вернул курсы по запрошенным валютам")
        return quotes


class ExchangeRateApiClient(BaseApiClient):
    source_name = "ExchangeRate-API"

    def __init__(self, config: ParserConfig | None = None):
        self.config = config or ParserConfig()

    def fetch_rates(self) -> dict[str, RateQuote]:
        api_key = (self.config.EXCHANGERATE_API_KEY or "").strip()
        if not api_key:
            raise ApiRequestError(
                "не задан EXCHANGERATE_API_KEY (переменная окружения или файл .env)"
            )

        base = self.config.BASE_CURRENCY.upper()
        url = f"{self.config.EXCHANGERATE_API_URL.rstrip('/')}/{api_key}/latest/{base}"
        payload, status_code, elapsed_ms, etag = _get_json(
            url,
            timeout=self.config.REQUEST_TIMEOUT,
            headers={
                "User-Agent": self.config.USER_AGENT,
                "Accept": "application/json",
            },
            source=self.source_name,
        )
        if not isinstance(payload, dict):
            raise ApiRequestError("ExchangeRate-API вернул неожиданный формат ответа")
        if payload.get("result") != "success":
            error_type = payload.get("error-type") or payload.get("result") or "unknown"
            raise ApiRequestError(f"ExchangeRate-API отклонил запрос: {error_type}")

        rates = payload.get("conversion_rates")
        if not isinstance(rates, dict):
            rates = payload.get("rates")
        if not isinstance(rates, dict):
            raise ApiRequestError("ExchangeRate-API не вернул словарь rates")

        timestamp = parse_api_timestamp(payload.get("time_last_update_utc"))
        quotes: dict[str, RateQuote] = {}
        for code in self.config.FIAT_CURRENCIES:
            if code == base:
                continue
            raw = rates.get(code)
            if raw is None:
                continue
            try:
                usd_per_foreign = float(raw)
            except (TypeError, ValueError) as error:
                raise ApiRequestError(
                    f"ExchangeRate-API вернул нечисловой курс для {code}"
                ) from error
            if usd_per_foreign == 0:
                continue
            # API отдаёт сколько единиц CODE за 1 USD; Core хранит CODE_USD.
            rate = 1.0 / usd_per_foreign
            quote = RateQuote(
                from_currency=code,
                to_currency=base,
                rate=rate,
                timestamp=timestamp,
                source=self.source_name,
                meta={
                    "raw_id": code,
                    "request_ms": elapsed_ms,
                    "status_code": status_code,
                    "etag": etag,
                    "api_base": payload.get("base_code", base),
                    "api_rate": usd_per_foreign,
                },
            )
            quotes[quote.pair] = quote
        if not quotes:
            raise ApiRequestError(
                "ExchangeRate-API не вернул курсы по запрошенным валютам"
            )
        return quotes


def _get_json(
    url: str,
    *,
    timeout: int,
    source: str,
    params: dict | None = None,
    headers: dict | None = None,
) -> tuple[object, int, int, str | None]:
    started = time.perf_counter()
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.exceptions.Timeout as error:
        raise ApiRequestError(f"{source}: превышен таймаут запроса") from error
    except requests.exceptions.RequestException as error:
        raise ApiRequestError("Network error") from error

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    status = response.status_code
    if status == 429:
        raise ApiRequestError(
            f"{source}: 429 Too Many Requests, лимит запросов исчерпан"
        )
    if status in {401, 403}:
        raise ApiRequestError(f"{source}: неверный ключ или доступ запрещён ({status})")
    if status >= 400:
        raise ApiRequestError(f"{source}: HTTP {status}")

    try:
        payload = response.json()
    except ValueError as error:
        raise ApiRequestError(f"{source}: ответ не является JSON") from error
    return payload, status, elapsed_ms, response.headers.get("ETag")
