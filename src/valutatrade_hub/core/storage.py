import json
from pathlib import Path

from valutatrade_hub.core.constants import DEFAULT_RATES
from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.core.settings import SettingsLoader

_settings = SettingsLoader()


def initialize_storage() -> None:
    data_dir = _settings.get("data_dir")
    data_dir.mkdir(parents=True, exist_ok=True)
    users_file = _settings.get("users_file")
    portfolios_file = _settings.get("portfolios_file")
    rates_file = _settings.get("rates_file")
    if not users_file.exists():
        save_data(users_file, [])
    if not portfolios_file.exists():
        save_data(portfolios_file, [])
    if not rates_file.exists():
        save_data(rates_file, DEFAULT_RATES)


def load_data(filepath: Path):
    try:
        with open(filepath, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


def save_data(filepath: Path, data) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_users() -> list[User]:
    data = load_data(_settings.get("users_file")) or []
    if isinstance(data, dict):
        data = list(data.values()) if data else []
    return [User.from_dict(item) for item in data]


def save_users(users: list[User]) -> None:
    save_data(_settings.get("users_file"), [user.to_dict() for user in users])


def load_portfolios() -> list[Portfolio]:
    data = load_data(_settings.get("portfolios_file")) or []
    if isinstance(data, dict):
        data = list(data.values()) if data else []
    return [Portfolio.from_dict(item) for item in data]


def save_portfolios(portfolios: list[Portfolio]) -> None:
    save_data(
        _settings.get("portfolios_file"),
        [portfolio.to_dict() for portfolio in portfolios],
    )


def find_user_by_username(username: str) -> User | None:
    for user in load_users():
        if user.username == username:
            return user
    return None


def find_portfolio(user_id: int) -> Portfolio | None:
    for portfolio in load_portfolios():
        if portfolio.user_id == user_id:
            return portfolio
    return None


def upsert_portfolio(portfolio: Portfolio) -> None:
    portfolios = load_portfolios()
    updated = False
    for index, current in enumerate(portfolios):
        if current.user_id == portfolio.user_id:
            portfolios[index] = portfolio
            updated = True
            break
    if not updated:
        portfolios.append(portfolio)
    save_portfolios(portfolios)


def load_rates() -> dict:
    data = load_data(_settings.get("rates_file"))
    if not isinstance(data, dict) or not data:
        return dict(DEFAULT_RATES)
    return data


def save_rates(rates: dict) -> None:
    save_data(_settings.get("rates_file"), rates)
