import logging
import time

from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.updater import RatesUpdater, build_updater

LOGGER = logging.getLogger("valutatrade_hub.parser")


class RateScheduler:
    """Периодически вызывает RatesUpdater.run_update() в текущем потоке."""

    def __init__(
        self,
        updater: RatesUpdater | None = None,
        interval_seconds: int | None = None,
        config: ParserConfig | None = None,
    ):
        self.config = config or ParserConfig()
        self.updater = updater or build_updater()
        self.interval_seconds = int(
            interval_seconds or self.config.UPDATE_INTERVAL_SECONDS
        )

    def run(self, cycles: int | None = None) -> None:
        LOGGER.info("Scheduler started: interval=%ss", self.interval_seconds)
        completed = 0
        try:
            while cycles is None or completed < cycles:
                try:
                    self.updater.run_update()
                except Exception:
                    LOGGER.exception("Scheduled rates update failed")
                completed += 1
                if cycles is not None and completed >= cycles:
                    break
                time.sleep(self.interval_seconds)
        except KeyboardInterrupt:
            LOGGER.info("Scheduler interrupted")
        LOGGER.info("Scheduler stopped")
