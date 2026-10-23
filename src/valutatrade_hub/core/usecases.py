from datetime import datetime, timedelta

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.core.utils import (
    convert_by_rate,
    format_amount,
    format_datetime,
    generate_salt,
    hash_password,
    parse_amount,
    parse_datetime,
)
from valutatrade_hub.decorators import log_action, update_action_log
from valutatrade_hub.infra.database import DatabaseManager, extract_rate_pairs
from valutatrade_hub.infra.settings import SettingsLoader

EMPTY_RATES_MESSAGE = (
    "Локальный кеш курсов пуст. Выполните 'update-rates', чтобы загрузить данные."
)
STALE_RATES_MESSAGE = (
    "Данные курсов устарели. Выполните 'update-rates', чтобы обновить кеш."
)
_settings = SettingsLoader()
_db = DatabaseManager()


def _base_currency() -> str:
    return _settings.get("base_currency", "USD")


def _rate_ttl() -> timedelta:
    return timedelta(seconds=_settings.get("rates_ttl_seconds", 300))


@log_action("REGISTER")
def register_user(username: str, password: str) -> int:
    if not isinstance(username, str) or not username.strip():
        raise ValueError("Имя не может быть пустым")
    username = username.strip()
    update_action_log(username=username)
    if not isinstance(password, str) or len(password) < 4:
        raise ValueError("Пароль должен быть не короче 4 символов")

    def create(users: list[User]) -> int:
        if any(user.username == username for user in users):
            raise ValueError(f"Имя пользователя '{username}' уже занято")

        new_id = max((user.user_id for user in users), default=0) + 1
        salt = generate_salt()
        users.append(
            User(
                user_id=new_id,
                username=username,
                hashed_password=hash_password(password, salt),
                salt=salt,
                registration_date=datetime.now().replace(microsecond=0),
            )
        )
        return new_id

    user_id = _db.transact_users(create)
    _db.transact_portfolio(user_id, lambda portfolio: portfolio)
    update_action_log(user_id=user_id)
    return user_id


@log_action("LOGIN")
def login_user(username: str, password: str) -> User:
    name = username.strip() if isinstance(username, str) else ""
    update_action_log(username=name)
    user = _db.find_user_by_username(name)
    if user is None:
        raise ValueError(f"Пользователь '{username}' не найден")
    if not user.verify_password(password):
        raise ValueError("Неверный пароль")
    update_action_log(user_id=user.user_id)
    return user


def _require_portfolio(user: User) -> Portfolio:
    portfolio = _db.find_portfolio(user.user_id)
    if portfolio is None:
        portfolio = Portfolio(user_id=user.user_id, wallets={}, user=user)
        _db.upsert_portfolio(portfolio)
        return portfolio
    return Portfolio(user.user_id, portfolio.wallets, user=user)


def _pair_payload(rates: dict, from_code: str, to_code: str) -> dict | None:
    key = f"{from_code}_{to_code}"
    payload = extract_rate_pairs(rates).get(key)
    if isinstance(payload, dict) and "rate" in payload:
        return payload
    return None


def _is_fresh(updated_at: str) -> bool:
    try:
        updated = parse_datetime(updated_at)
    except ValueError:
        return False
    now = datetime.now(updated.tzinfo) if updated.tzinfo else datetime.now()
    return now - updated <= _rate_ttl()


def _require_fresh_rates(rates: dict) -> None:
    if not extract_rate_pairs(rates):
        raise ValueError(EMPTY_RATES_MESSAGE)
    stamp = rates.get("last_refresh")
    if not isinstance(stamp, str) or not _is_fresh(stamp):
        raise ValueError(STALE_RATES_MESSAGE)


def _usd_rate(rates: dict, currency_code: str) -> float | None:
    base = _base_currency()
    if currency_code == base:
        return 1.0
    direct = _pair_payload(rates, currency_code, base)
    if direct:
        return float(direct["rate"])
    inverse = _pair_payload(rates, base, currency_code)
    if inverse and float(inverse["rate"]) != 0:
        return 1.0 / float(inverse["rate"])
    return None


def resolve_rate(from_code: str, to_code: str) -> tuple[float, str, float]:
    from_code = get_currency(from_code).code
    to_code = get_currency(to_code).code
    rates = _db.load_rates()

    def lookup(data: dict) -> tuple[float, str, float] | None:
        if from_code == to_code:
            stamp = data.get("last_refresh") or format_datetime(datetime.now())
            return 1.0, stamp, 1.0

        direct = _pair_payload(data, from_code, to_code)
        inverse = _pair_payload(data, to_code, from_code)
        if direct:
            rate = float(direct["rate"])
            reverse = (1.0 / rate) if rate else 0.0
            return rate, direct.get("updated_at", ""), reverse
        if inverse:
            inv_rate = float(inverse["rate"])
            if not inv_rate:
                return None
            rate = 1.0 / inv_rate
            return rate, inverse.get("updated_at", ""), inv_rate

        from_usd = _usd_rate(data, from_code)
        to_usd = _usd_rate(data, to_code)
        if from_usd is None or to_usd is None or to_usd == 0:
            return None
        stamp = data.get("last_refresh") or format_datetime(datetime.now())
        return from_usd / to_usd, stamp, to_usd / from_usd

    _require_fresh_rates(rates)
    found = lookup(rates)
    if found:
        _rate, stamp, _reverse = found
        if stamp and not _is_fresh(stamp):
            raise ValueError(STALE_RATES_MESSAGE)
    if not found:
        raise ApiRequestError(f"курс {from_code}→{to_code} недоступен")
    return found


def rates_to_usd_map() -> dict[str, float]:
    rates = _db.load_rates()
    _require_fresh_rates(rates)
    base = _base_currency()
    converted = {base: 1.0}
    for key, payload in extract_rate_pairs(rates).items():
        if not isinstance(payload, dict) or "rate" not in payload or "_" not in key:
            continue
        source, target = key.split("_", 1)
        if target == base:
            converted[source] = float(payload["rate"])
        elif source == base and float(payload["rate"]) != 0:
            converted[target] = 1.0 / float(payload["rate"])
    return converted


def show_portfolio(user: User, base_currency: str | None = None) -> str:
    base = get_currency(base_currency or _base_currency()).code
    portfolio = _require_portfolio(user)
    usd_rates = rates_to_usd_map()
    if base not in usd_rates:
        raise CurrencyNotFoundError(base)

    header = f"Портфель пользователя '{user.username}' (база: {base}):"
    if not portfolio.wallets:
        return f"{header}\nПортфель пуст."

    rows = []
    total = 0.0
    for code, wallet in portfolio.wallets.items():
        if code not in usd_rates:
            raise ApiRequestError(f"не удалось получить курс для {code}→{base}")
        value = wallet.balance * usd_rates[code] / usd_rates[base]
        total += value
        rows.append(
            (
                code,
                format_amount(code, wallet.balance),
                f"{value:.2f}",
            )
        )

    lines = [header]
    balance_width = max(len(balance) for _, balance, _ in rows)
    for code, balance, value in rows:
        lines.append(f"- {code}: {balance:>{balance_width}}  → {value} {base}")
    lines.append("---------------------------------")
    lines.append(f"ИТОГО: {total:,.2f} {base}")
    return "\n".join(lines)


def _quote_or_error(currency_code: str) -> float:
    base = _base_currency()
    try:
        rate, _stamp, _reverse = resolve_rate(currency_code, base)
        return rate
    except ApiRequestError as error:
        raise ApiRequestError(
            f"не удалось получить курс для {currency_code}→{base}"
        ) from error


@log_action("BUY", verbose=True)
def buy(user: User, currency_code: str, amount) -> str:
    update_action_log(
        username=user.username,
        user_id=user.user_id,
        currency_code=currency_code,
        amount=amount,
    )
    currency = get_currency(currency_code)
    code = currency.code
    qty = parse_amount(amount)
    update_action_log(currency_code=code, amount=qty)
    rate = _quote_or_error(code)
    cost = convert_by_rate(qty, rate)
    base = _base_currency()
    update_action_log(rate=rate, base=base)

    def apply(portfolio: Portfolio) -> tuple[float, float, bool]:
        if code != base:
            portfolio.get_or_create_wallet(base).withdraw(cost)
        created = portfolio.get_wallet(code) is None
        wallet = portfolio.get_or_create_wallet(code)
        before = wallet.balance
        wallet.deposit(qty)
        return before, wallet.balance, created

    before, after, created = _db.transact_portfolio(user.user_id, apply, user=user)
    update_action_log(wallet_before=before, wallet_after=after)

    created_line = f"Кошелёк {code} создан автоматически.\n" if created else ""
    return (
        f"Покупка выполнена: {format_amount(code, qty)} {code} "
        f"({currency.name}) по курсу {rate:.2f} {base}/{code}\n"
        f"{created_line}"
        f"Изменения в портфеле:\n"
        f"- {code}: было {format_amount(code, before)} → "
        f"стало {format_amount(code, after)}\n"
        f"Оценочная стоимость покупки: {cost:,.2f} {base}"
    )


@log_action("SELL", verbose=True)
def sell(user: User, currency_code: str, amount) -> str:
    update_action_log(
        username=user.username,
        user_id=user.user_id,
        currency_code=currency_code,
        amount=amount,
    )
    currency = get_currency(currency_code)
    code = currency.code
    qty = parse_amount(amount)
    update_action_log(currency_code=code, amount=qty)
    rate = _quote_or_error(code)
    revenue = convert_by_rate(qty, rate)
    base = _base_currency()

    def apply(portfolio: Portfolio) -> tuple[float, float]:
        wallet = portfolio.get_wallet(code)
        if wallet is None:
            raise InsufficientFundsError(
                available=format_amount(code, 0),
                required=format_amount(code, qty),
                code=code,
            )
        before = wallet.balance
        wallet.withdraw(qty)
        if code != base:
            portfolio.get_or_create_wallet(base).deposit(revenue)
        return before, wallet.balance

    before, after = _db.transact_portfolio(user.user_id, apply, user=user)
    update_action_log(rate=rate, base=base, wallet_before=before, wallet_after=after)

    return (
        f"Продажа выполнена: {format_amount(code, qty)} {code} "
        f"({currency.name}) по курсу {rate:.2f} {base}/{code}\n"
        f"Изменения в портфеле:\n"
        f"- {code}: было {format_amount(code, before)} → "
        f"стало {format_amount(code, after)}\n"
        f"Оценочная выручка: {revenue:,.2f} {base}"
    )


def get_rate(from_code: str, to_code: str) -> str:
    source = get_currency(from_code).code
    target = get_currency(to_code).code
    rate, stamp, reverse = resolve_rate(source, target)
    try:
        shown = parse_datetime(stamp).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        shown = stamp
    forward = f"{rate:.8f}".rstrip("0").rstrip(".")
    reverse_shown = (
        f"{reverse:.8f}".rstrip("0").rstrip(".") if reverse < 1 else f"{reverse:.2f}"
    )
    return (
        f"Курс {source}→{target}: {forward} (обновлено: {shown})\n"
        f"Обратный курс {target}→{source}: {reverse_shown}"
    )
