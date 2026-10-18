from valutatrade_hub.core.models import CryptoCurrency, Currency, FiatCurrency
from valutatrade_hub.core.utils import normalize_currency


class CurrencyNotFoundError(LookupError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(f"Валюта с кодом '{code}' не найдена")


CURRENCIES: dict[str, Currency] = {
    "USD": FiatCurrency("US Dollar", "USD", "United States"),
    "EUR": FiatCurrency("Euro", "EUR", "Eurozone"),
    "RUB": FiatCurrency("Russian Ruble", "RUB", "Russia"),
    "BTC": CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
    "ETH": CryptoCurrency("Ethereum", "ETH", "Ethash", 3.65e11),
}


def get_currency(code: str) -> Currency:
    normalized = normalize_currency(code)
    currency = CURRENCIES.get(normalized)
    if currency is None:
        raise CurrencyNotFoundError(normalized)
    return currency
