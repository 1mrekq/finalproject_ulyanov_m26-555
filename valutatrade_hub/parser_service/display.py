from prettytable import PrettyTable

from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import (
    RatesStorage,
    extract_rate_pairs,
    last_refresh_of,
)


class EmptyRatesCacheError(ValueError):
    def __init__(self) -> None:
        super().__init__(
            "Локальный кеш курсов пуст. "
            "Выполните 'update-rates', чтобы загрузить данные."
        )


class CachedRateNotFoundError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(f"Курс для '{code}' не найден в кеше.")


def format_show_rates(
    currency: str | None = None,
    top: int | None = None,
    base: str | None = None,
    storage: RatesStorage | None = None,
    config: ParserConfig | None = None,
) -> str:
    config = config or ParserConfig()
    storage = storage or RatesStorage(config)
    cache = storage.load_cache()
    pairs = extract_rate_pairs(cache)
    if not pairs:
        raise EmptyRatesCacheError()

    usd_map = _usd_map(pairs, config.BASE_CURRENCY)
    display_base = (base or config.BASE_CURRENCY).strip().upper()
    if display_base not in usd_map:
        raise CachedRateNotFoundError(display_base)

    rows: list[tuple[str, float]] = []
    for pair, payload in pairs.items():
        if not isinstance(payload, dict) or "rate" not in payload:
            continue
        if "_" not in pair:
            continue
        from_code, _to_code = pair.split("_", 1)
        usd_rate = usd_map.get(from_code)
        if usd_rate is None:
            continue
        converted = usd_rate / usd_map[display_base]
        rows.append((f"{from_code}_{display_base}", converted))

    if currency:
        code = currency.strip().upper()
        rows = [item for item in rows if item[0].startswith(f"{code}_")]
        if not rows:
            raise CachedRateNotFoundError(code)

    if top is not None:
        crypto = set(config.CRYPTO_CURRENCIES)
        crypto_rows = [item for item in rows if item[0].split("_", 1)[0] in crypto]
        crypto_rows.sort(key=lambda item: item[1], reverse=True)
        rows = crypto_rows[:top]
    else:
        rows.sort(key=lambda item: item[0])

    stamp = last_refresh_of(cache) or "unknown"
    table = PrettyTable()
    table.field_names = ["Пара", "Курс"]
    table.align["Пара"] = "l"
    table.align["Курс"] = "r"
    for pair, rate in rows:
        table.add_row([pair, _format_rate(rate)])
    return f"Rates from cache (updated at {stamp}):\n{table}"


def _usd_map(pairs: dict, base: str) -> dict[str, float]:
    converted = {base: 1.0}
    for key, payload in pairs.items():
        if not isinstance(payload, dict) or "rate" not in payload or "_" not in key:
            continue
        try:
            rate = float(payload["rate"])
        except (TypeError, ValueError):
            continue
        source, target = key.split("_", 1)
        if target == base:
            converted[source] = rate
        elif source == base and rate != 0:
            converted[target] = 1.0 / rate
    return converted


def _format_rate(value: float) -> str:
    text = f"{value:.8f}".rstrip("0").rstrip(".")
    return text if text else "0"
