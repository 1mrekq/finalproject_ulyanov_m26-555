"""Декоратор трассировки доменных операций buy/sell/register/login."""

from __future__ import annotations

import functools
import logging
from contextvars import ContextVar
from datetime import datetime
from typing import Any

from valutatrade_hub.core.utils import format_amount
from valutatrade_hub.logging_config import setup_logging

_LOG_FIELDS: ContextVar[dict[str, Any] | None] = ContextVar(
    "action_log_fields", default=None
)
_HIDDEN = {"password", "hashed_password", "salt"}
_IDENTITY_ACTIONS = {"REGISTER", "LOGIN"}


def update_action_log(**fields: Any) -> None:
    """Дополняет запись текущего вызова. Вне декоратора вызов игнорируется."""
    current = _LOG_FIELDS.get()
    if current is None:
        return
    for key, value in fields.items():
        if key not in _HIDDEN and value is not None:
            current[key] = value


def log_action(action: str, *, verbose: bool = False):
    """Пишет итог операции в журнал и пробрасывает исключение дальше.

    Поля приходят из update_action_log внутри функции. verbose добавляет
    контекст кошелька «было→стало», если известны оба баланса.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            token = _LOG_FIELDS.set({})
            try:
                result = func(*args, **kwargs)
            except Exception as error:
                _write(action, verbose, error=error)
                raise
            else:
                _write(action, verbose)
                return result
            finally:
                _LOG_FIELDS.reset(token)

        return wrapper

    return decorator


def _write(action: str, verbose: bool, error: Exception | None = None) -> None:
    logger = setup_logging()
    fields = dict(_LOG_FIELDS.get() or {})
    logger.info(_format_message(action, fields, verbose=verbose, error=error))
    if logger.isEnabledFor(logging.DEBUG):
        visible = {key: value for key, value in fields.items() if key not in _HIDDEN}
        logger.debug("fields %s", visible)
        if error is not None:
            logger.debug("action failed", exc_info=error)


def _format_message(action, fields, *, verbose: bool, error: Exception | None) -> str:
    timestamp = datetime.now().replace(microsecond=0).isoformat()
    parts = [timestamp, action]
    username = fields.get("username")
    user_id = fields.get("user_id")
    if username:
        parts.append(f"user={_quote(username)}")
    elif user_id is not None:
        parts.append(f"user_id={user_id}")
    if action in _IDENTITY_ACTIONS and username and user_id is not None:
        parts.append(f"user_id={user_id}")
    currency = fields.get("currency_code")
    if isinstance(currency, str) and currency.strip():
        parts.append(f"currency={_quote(currency.strip().upper())}")
    if "amount" in fields:
        parts.append(f"amount={_format_amount(fields)}")
    if "rate" in fields:
        parts.append(f"rate={float(fields['rate']):.2f}")
    if fields.get("base"):
        parts.append(f"base={_quote(fields['base'])}")
    if verbose:
        wallet = _wallet_transition(fields)
        if wallet is not None:
            parts.append(f"wallet={_quote(wallet)}")
    parts.append("result=ERROR" if error is not None else "result=OK")
    if error is not None:
        parts.append(f"error_type={_quote(type(error).__name__)}")
        parts.append(f"error_message={_quote(error)}")
    return " ".join(parts)


def _format_amount(fields: dict[str, Any]) -> str:
    amount = fields["amount"]
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return str(amount)
    code = str(fields.get("currency_code") or "").strip().upper()
    return format_amount(code, value)


def _wallet_transition(fields: dict[str, Any]) -> str | None:
    before = fields.get("wallet_before")
    after = fields.get("wallet_after")
    if before is None or after is None:
        return None
    code = str(fields.get("currency_code") or "").strip().upper()
    return f"{format_amount(code, float(before))}→{format_amount(code, float(after))}"


def _quote(value: Any) -> str:
    text = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{text}'"
