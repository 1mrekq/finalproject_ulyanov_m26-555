from valutatrade_hub.core.exceptions import CurrencyNotFoundError
from valutatrade_hub.core.models import CryptoCurrency, Currency, FiatCurrency
from valutatrade_hub.core.utils import normalize_currency

CURRENCIES: dict[str, Currency] = {
    "USD": FiatCurrency("US Dollar", "USD", "United States"),
    "EUR": FiatCurrency("Euro", "EUR", "Eurozone"),
    "RUB": FiatCurrency("Russian Ruble", "RUB", "Russia"),
    "BTC": CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
    "ETH": CryptoCurrency("Ethereum", "ETH", "Ethash", 3.65e11),
}


def supported_codes() -> list[str]:
    return sorted(CURRENCIES)


def get_currency(code: str) -> Currency:
    normalized = normalize_currency(code)
    currency = CURRENCIES.get(normalized)
    if currency is None:
        raise CurrencyNotFoundError(normalized)
    return currency
