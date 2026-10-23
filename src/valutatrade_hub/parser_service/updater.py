import logging
from dataclasses import dataclass, field

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.api_clients import (
    BaseApiClient,
    CoinGeckoClient,
    ExchangeRateApiClient,
    RateQuote,
    utc_now_iso,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage

LOGGER = logging.getLogger("valutatrade_hub.parser")

SOURCE_ALIASES = {
    "coingecko": "CoinGecko",
    "coin-gecko": "CoinGecko",
    "exchangerate": "ExchangeRate-API",
    "exchange-rate": "ExchangeRate-API",
    "exchangerate-api": "ExchangeRate-API",
}


@dataclass
class SourceResult:
    name: str
    ok: bool
    count: int = 0
    error: str | None = None


@dataclass
class UpdateResult:
    quotes: list[RateQuote] = field(default_factory=list)
    sources: list[SourceResult] = field(default_factory=list)
    last_refresh: str = ""
    written: int = 0

    @property
    def has_errors(self) -> bool:
        return any(not item.ok for item in self.sources)

    @property
    def total(self) -> int:
        return len(self.quotes)


class RatesUpdater:
    def __init__(
        self,
        clients: list[BaseApiClient] | None = None,
        storage: RatesStorage | None = None,
        config: ParserConfig | None = None,
    ):
        self.config = config or ParserConfig()
        self.storage = storage or RatesStorage(self.config)
        self.clients = clients or [
            CoinGeckoClient(self.config),
            ExchangeRateApiClient(self.config),
        ]

    def run_update(self, source: str | None = None) -> UpdateResult:
        LOGGER.info("Starting rates update...")
        selected = self._select_clients(source)
        quotes: dict[str, RateQuote] = {}
        results: list[SourceResult] = []

        for client in selected:
            LOGGER.info("Fetching from %s...", client.source_name)
            try:
                fetched = client.fetch_rates()
            except ApiRequestError as error:
                LOGGER.error(
                    "Failed to fetch from %s: %s",
                    client.source_name,
                    error.reason,
                )
                results.append(
                    SourceResult(
                        name=client.source_name,
                        ok=False,
                        error=error.reason,
                    )
                )
                continue
            quotes.update(fetched)
            LOGGER.info(
                "Fetching from %s... OK (%s rates)",
                client.source_name,
                len(fetched),
            )
            results.append(
                SourceResult(name=client.source_name, ok=True, count=len(fetched))
            )

        last_refresh = utc_now_iso()
        written = 0
        if quotes:
            LOGGER.info(
                "Writing %s rates to %s...",
                len(quotes),
                self.storage.rates_path,
            )
            written = self.storage.save_quotes(list(quotes.values()), last_refresh)
        LOGGER.info(
            "Rates update finished: %s quotes, errors=%s",
            len(quotes),
            any(not item.ok for item in results),
        )
        return UpdateResult(
            quotes=list(quotes.values()),
            sources=results,
            last_refresh=last_refresh,
            written=written,
        )

    def _select_clients(self, source: str | None) -> list[BaseApiClient]:
        if source is None or not str(source).strip():
            return list(self.clients)
        alias = SOURCE_ALIASES.get(str(source).strip().lower())
        if alias is None:
            raise ValueError(
                "Неизвестный источник. Используйте coingecko или exchangerate"
            )
        selected = [client for client in self.clients if client.source_name == alias]
        if not selected:
            raise ValueError(f"Источник '{source}' недоступен")
        return selected


def build_updater() -> RatesUpdater:
    config = ParserConfig()
    return RatesUpdater(config=config, storage=RatesStorage(config))
