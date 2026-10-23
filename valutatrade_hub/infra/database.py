import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Self, TypeVar

from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.infra.settings import SettingsLoader

RATE_META_KEYS = {"source", "last_refresh", "pairs"}


def extract_rate_pairs(data: dict | None) -> dict:
    if not isinstance(data, dict) or not data:
        return {}
    pairs = data.get("pairs")
    if isinstance(pairs, dict):
        return dict(pairs)
    return {
        key: value
        for key, value in data.items()
        if key not in RATE_META_KEYS and isinstance(value, dict) and "rate" in value
    }


T = TypeVar("T")


class DatabaseManager:
    """Singleton-абстракция над JSON-файлами users/portfolios/rates.

    Как и SettingsLoader, реализован через __new__: один экземпляр на процесс,
    чтобы usecases всегда читали и писали одно и то же хранилище.
    """

    _instance: Self | None = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._settings = SettingsLoader()
            cls._instance = instance
        return cls._instance

    def initialize(self) -> None:
        data_dir = self._settings.get("data_dir")
        data_dir.mkdir(parents=True, exist_ok=True)
        users_file = self._settings.get("users_file")
        portfolios_file = self._settings.get("portfolios_file")
        rates_file = self._settings.get("rates_file")
        history_file = self._settings.get("exchange_rates_file")
        if not users_file.exists():
            self._save(users_file, [])
        if not portfolios_file.exists():
            self._save(portfolios_file, [])
        if not rates_file.exists():
            self._save(rates_file, {"pairs": {}, "last_refresh": None})
        if history_file is not None and not history_file.exists():
            self._save(history_file, {"records": []})

    def load_users(self) -> list[User]:
        data = self._load(self._settings.get("users_file")) or []
        if isinstance(data, dict):
            data = list(data.values()) if data else []
        return [User.from_dict(item) for item in data]

    def save_users(self, users: list[User]) -> None:
        self._save(self._settings.get("users_file"), [user.to_dict() for user in users])

    def load_portfolios(self) -> list[Portfolio]:
        data = self._load(self._settings.get("portfolios_file")) or []
        if isinstance(data, dict):
            data = list(data.values()) if data else []
        return [Portfolio.from_dict(item) for item in data]

    def save_portfolios(self, portfolios: list[Portfolio]) -> None:
        self._save(
            self._settings.get("portfolios_file"),
            [portfolio.to_dict() for portfolio in portfolios],
        )

    def find_user_by_username(self, username: str) -> User | None:
        for user in self.load_users():
            if user.username == username:
                return user
        return None

    def find_portfolio(self, user_id: int) -> Portfolio | None:
        for portfolio in self.load_portfolios():
            if portfolio.user_id == user_id:
                return portfolio
        return None

    def upsert_portfolio(self, portfolio: Portfolio) -> None:
        portfolios = self.load_portfolios()
        updated = False
        for index, current in enumerate(portfolios):
            if current.user_id == portfolio.user_id:
                portfolios[index] = portfolio
                updated = True
                break
        if not updated:
            portfolios.append(portfolio)
        self.save_portfolios(portfolios)

    def transact_users(self, callback: Callable[[list[User]], T]) -> T:
        users = self.load_users()
        result = callback(users)
        self.save_users(users)
        return result

    def transact_portfolio(
        self,
        user_id: int,
        callback: Callable[[Portfolio], T],
        user: User | None = None,
    ) -> T:
        portfolios = self.load_portfolios()
        index = next(
            (i for i, item in enumerate(portfolios) if item.user_id == user_id),
            None,
        )
        if index is None:
            portfolio = Portfolio(user_id=user_id, wallets={}, user=user)
            portfolios.append(portfolio)
            index = len(portfolios) - 1
        else:
            current = portfolios[index]
            portfolio = Portfolio(user_id, current.wallets, user=user or current.user)
            portfolios[index] = portfolio

        result = callback(portfolio)
        self.save_portfolios(portfolios)
        return result

    def transact_rates(self, callback: Callable[[dict], T]) -> T:
        rates = self.load_rates()
        result = callback(rates)
        self.save_rates(rates)
        return result

    def load_rates(self) -> dict:
        data = self._load(self._settings.get("rates_file"))
        if not isinstance(data, dict):
            return {}
        return data

    def save_rates(self, rates: dict) -> None:
        self._save(self._settings.get("rates_file"), rates)

    def _load(self, filepath: Path):
        try:
            with open(filepath, encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            return None

    def _save(self, filepath: Path, data) -> None:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        handle, tmp_name = tempfile.mkstemp(
            dir=filepath.parent,
            prefix=f".{filepath.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(tmp_name, filepath)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
