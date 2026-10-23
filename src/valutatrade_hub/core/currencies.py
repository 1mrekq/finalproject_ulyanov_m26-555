from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError
from valutatrade_hub.core.utils import normalize_currency


class Currency(ABC):
    def __init__(self, name: str, code: str):
        self.name = name
        self.code = code

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Название валюты должно быть непустой строкой")
        self._name = value.strip()

    @property
    def code(self) -> str:
        return self._code

    @code.setter
    def code(self, value: str) -> None:
        self._code = normalize_currency(value)

    @abstractmethod
    def get_display_info(self) -> str:
        pass


class FiatCurrency(Currency):
    def __init__(self, name: str, code: str, issuing_country: str):
        super().__init__(name, code)
        self.issuing_country = issuing_country

    @property
    def issuing_country(self) -> str:
        return self._issuing_country

    @issuing_country.setter
    def issuing_country(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Страна эмиссии должна быть непустой строкой")
        self._issuing_country = value.strip()

    def get_display_info(self) -> str:
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    def __init__(self, name: str, code: str, algorithm: str, market_cap: float):
        super().__init__(name, code)
        self.algorithm = algorithm
        self.market_cap = market_cap

    @property
    def algorithm(self) -> str:
        return self._algorithm

    @algorithm.setter
    def algorithm(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Алгоритм должен быть непустой строкой")
        self._algorithm = value.strip()

    @property
    def market_cap(self) -> float:
        return self._market_cap

    @market_cap.setter
    def market_cap(self, value: float) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("Рыночная капитализация должна быть числом")
        if value < 0:
            raise ValueError("Рыночная капитализация не может быть отрицательной")
        self._market_cap = float(value)

    def get_display_info(self) -> str:
        mcap = f"{self.market_cap:.2e}".replace("e+", "e")
        return (
            f"[CRYPTO] {self.code} — {self.name} (Algo: {self.algorithm}, MCAP: {mcap})"
        )


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
    try:
        normalized = normalize_currency(code)
    except ValueError:
        shown = code.strip() if isinstance(code, str) else code
        raise CurrencyNotFoundError(str(shown)) from None
    currency = CURRENCIES.get(normalized)
    if currency is None:
        raise CurrencyNotFoundError(normalized)
    return currency
