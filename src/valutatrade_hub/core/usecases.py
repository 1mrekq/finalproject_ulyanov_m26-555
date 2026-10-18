from datetime import datetime

from valutatrade_hub.core.constants import BASE_CURRENCY, RATE_TTL, STUB_RATES
from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.core.storage import (
    find_portfolio,
    find_user_by_username,
    load_rates,
    load_users,
    save_rates,
    save_users,
    upsert_portfolio,
)
from valutatrade_hub.core.utils import (
    format_amount,
    format_datetime,
    generate_salt,
    hash_password,
    normalize_currency,
    parse_amount,
    parse_datetime,
)

META_KEYS = {"source", "last_refresh"}


def register_user(username: str, password: str) -> int:
    if not isinstance(username, str) or not username.strip():
        raise ValueError("Имя не может быть пустым")
    username = username.strip()
    if not isinstance(password, str) or len(password) < 4:
        raise ValueError("Пароль должен быть не короче 4 символов")

    users = load_users()
    if any(user.username == username for user in users):
        raise ValueError(f"Имя пользователя '{username}' уже занято")

    user_id = max((user.user_id for user in users), default=0) + 1
    salt = generate_salt()
    user = User(
        user_id=user_id,
        username=username,
        hashed_password=hash_password(password, salt),
        salt=salt,
        registration_date=datetime.now().replace(microsecond=0),
    )
    users.append(user)
    save_users(users)
    upsert_portfolio(Portfolio(user_id=user_id, wallets={}))
    return user_id


def login_user(username: str, password: str) -> User:
    user = find_user_by_username(username.strip() if isinstance(username, str) else "")
    if user is None:
        raise ValueError(f"Пользователь '{username}' не найден")
    if not user.verify_password(password):
        raise ValueError("Неверный пароль")
    return user


def _require_portfolio(user: User) -> Portfolio:
    portfolio = find_portfolio(user.user_id)
    if portfolio is None:
        portfolio = Portfolio(user_id=user.user_id, wallets={}, user=user)
        upsert_portfolio(portfolio)
        return portfolio
    return Portfolio(user.user_id, portfolio.wallets, user=user)


def _pair_payload(rates: dict, from_code: str, to_code: str) -> dict | None:
    key = f"{from_code}_{to_code}"
    payload = rates.get(key)
    if isinstance(payload, dict) and "rate" in payload:
        return payload
    return None


def _is_fresh(updated_at: str) -> bool:
    try:
        updated = parse_datetime(updated_at)
    except ValueError:
        return False
    return datetime.now() - updated <= RATE_TTL


def _refresh_rates_from_stub(rates: dict) -> dict:
    now = format_datetime(datetime.now())
    updated = dict(rates)
    for pair, rate in STUB_RATES.items():
        updated[pair] = {"rate": rate, "updated_at": now}
    updated["source"] = "ParserServiceStub"
    updated["last_refresh"] = now
    save_rates(updated)
    return updated


def _usd_rate(rates: dict, currency_code: str) -> float | None:
    if currency_code == BASE_CURRENCY:
        return 1.0
    direct = _pair_payload(rates, currency_code, BASE_CURRENCY)
    if direct:
        return float(direct["rate"])
    inverse = _pair_payload(rates, BASE_CURRENCY, currency_code)
    if inverse and float(inverse["rate"]) != 0:
        return 1.0 / float(inverse["rate"])
    return STUB_RATES.get(f"{currency_code}_{BASE_CURRENCY}")


def resolve_rate(from_code: str, to_code: str) -> tuple[float, str, float]:
    from_code = normalize_currency(from_code)
    to_code = normalize_currency(to_code)
    rates = load_rates()

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

    found = lookup(rates)
    needs_refresh = True
    if found:
        _rate, stamp, _reverse = found
        needs_refresh = not stamp or not _is_fresh(stamp)

    if needs_refresh:
        rates = _refresh_rates_from_stub(rates)
        found = lookup(rates)

    if not found:
        raise ValueError(
            f"Курс {from_code}→{to_code} недоступен. Повторите попытку позже."
        )
    return found


def rates_to_usd_map() -> dict[str, float]:
    rates = load_rates()
    converted = {BASE_CURRENCY: 1.0}
    for key, payload in rates.items():
        if key in META_KEYS or not isinstance(payload, dict) or "rate" not in payload:
            continue
        if "_" not in key:
            continue
        source, target = key.split("_", 1)
        if target == BASE_CURRENCY:
            converted[source] = float(payload["rate"])
        elif source == BASE_CURRENCY and float(payload["rate"]) != 0:
            converted[target] = 1.0 / float(payload["rate"])
    for pair, rate in STUB_RATES.items():
        source, target = pair.split("_", 1)
        if target == BASE_CURRENCY:
            converted.setdefault(source, rate)
    return converted


def show_portfolio(user: User, base_currency: str = BASE_CURRENCY) -> str:
    base = normalize_currency(base_currency)
    portfolio = _require_portfolio(user)
    usd_rates = rates_to_usd_map()
    if base not in usd_rates:
        raise ValueError(f"Неизвестная базовая валюта '{base}'")

    header = f"Портфель пользователя '{user.username}' (база: {base}):"
    if not portfolio.wallets:
        return f"{header}\nПортфель пуст."

    rows = []
    total = 0.0
    for code, wallet in portfolio.wallets.items():
        if code not in usd_rates:
            raise ValueError(f"Не удалось получить курс для {code}→{base}")
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
    try:
        rate, _stamp, _reverse = resolve_rate(currency_code, BASE_CURRENCY)
        return rate
    except ValueError:
        raise ValueError(
            f"Не удалось получить курс для {currency_code}→{BASE_CURRENCY}"
        ) from None


def buy(user: User, currency_code: str, amount) -> str:
    code = normalize_currency(currency_code)
    qty = parse_amount(amount)
    portfolio = _require_portfolio(user)
    rate = _quote_or_error(code)
    cost = qty * rate

    usd_wallet = portfolio.get_or_create_wallet(BASE_CURRENCY)
    if code != BASE_CURRENCY:
        available = usd_wallet.balance
        if cost > available:
            available_text = format_amount(BASE_CURRENCY, available)
            raise ValueError(
                f"Недостаточно средств: доступно {available_text} "
                f"{BASE_CURRENCY}, требуется {cost:.2f} {BASE_CURRENCY}"
            )
        usd_wallet.withdraw(cost)

    wallet = portfolio.get_or_create_wallet(code)
    before = wallet.balance
    wallet.deposit(qty)
    upsert_portfolio(portfolio)

    return (
        f"Покупка выполнена: {format_amount(code, qty)} {code} "
        f"по курсу {rate:.2f} {BASE_CURRENCY}/{code}\n"
        f"Изменения в портфеле:\n"
        f"- {code}: было {format_amount(code, before)} → "
        f"стало {format_amount(code, wallet.balance)}\n"
        f"Оценочная стоимость покупки: {cost:,.2f} {BASE_CURRENCY}"
    )


def sell(user: User, currency_code: str, amount) -> str:
    code = normalize_currency(currency_code)
    qty = parse_amount(amount)
    portfolio = _require_portfolio(user)
    wallet = portfolio.get_wallet(code)
    if wallet is None:
        raise ValueError(
            f"У вас нет кошелька '{code}'. Добавьте валюту: "
            "она создаётся автоматически при первой покупке."
        )
    if qty > wallet.balance:
        raise ValueError(
            f"Недостаточно средств: доступно {format_amount(code, wallet.balance)} "
            f"{code}, требуется {format_amount(code, qty)} {code}"
        )

    rate = _quote_or_error(code)
    revenue = qty * rate
    before = wallet.balance
    wallet.withdraw(qty)
    if code != BASE_CURRENCY:
        usd_wallet = portfolio.get_or_create_wallet(BASE_CURRENCY)
        usd_wallet.deposit(revenue)
    upsert_portfolio(portfolio)

    return (
        f"Продажа выполнена: {format_amount(code, qty)} {code} "
        f"по курсу {rate:.2f} {BASE_CURRENCY}/{code}\n"
        f"Изменения в портфеле:\n"
        f"- {code}: было {format_amount(code, before)} → "
        f"стало {format_amount(code, wallet.balance)}\n"
        f"Оценочная выручка: {revenue:,.2f} {BASE_CURRENCY}"
    )


def get_rate(from_code: str, to_code: str) -> str:
    source = normalize_currency(from_code)
    target = normalize_currency(to_code)
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
