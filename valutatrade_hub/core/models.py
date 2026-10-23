from datetime import datetime

from valutatrade_hub.core.constants import DEFAULT_BASE_CURRENCY, MIN_PASSWORD_LENGTH
from valutatrade_hub.core.exceptions import InsufficientFundsError
from valutatrade_hub.core.utils import (
    format_amount,
    format_datetime,
    hash_password,
    is_positive_number,
    normalize_currency,
    parse_datetime,
)


class User:
    """Пользователь системы: приватный хеш пароля с солью, без хранения plaintext."""

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ):
        self.user_id = user_id
        self.username = username
        self._salt = salt
        self._hashed_password = hashed_password
        self._registration_date = parse_datetime(registration_date)

    @property
    def user_id(self) -> int:
        return self._user_id

    @user_id.setter
    def user_id(self, value: int) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("Идентификатор пользователя должен быть int")
        self._user_id = value

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        if not isinstance(value, str):
            raise ValueError("Имя пользователя должно быть строкой")
        if not value.strip():
            raise ValueError("Имя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        return self._hashed_password

    @property
    def salt(self) -> str:
        return self._salt

    @property
    def registration_date(self) -> datetime:
        return self._registration_date

    def get_user_info(self) -> dict:
        """Публичные сведения о пользователе без пароля, соли и хеша."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "registration_date": format_datetime(self._registration_date),
        }

    @staticmethod
    def validate_password(password: str) -> str:
        if not isinstance(password, str):
            raise ValueError("Пароль должен быть строкой")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(
                f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов"
            )
        return password

    def change_password(self, new_password: str) -> None:
        password = self.validate_password(new_password)
        self._hashed_password = hash_password(password, self._salt)

    def verify_password(self, password: str) -> bool:
        if not isinstance(password, str):
            return False
        return self._hashed_password == hash_password(password, self._salt)

    def to_dict(self) -> dict:
        return {
            "user_id": self._user_id,
            "username": self._username,
            "hashed_password": self._hashed_password,
            "salt": self._salt,
            "registration_date": format_datetime(self._registration_date),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            hashed_password=data["hashed_password"],
            salt=data["salt"],
            registration_date=data["registration_date"],
        )


class Wallet:
    """Кошелёк одной валюты: баланс неотрицательный, списание проверяет остаток."""

    def __init__(self, currency_code: str, balance: float = 0.0):
        self.currency_code = currency_code
        self.balance = balance

    @property
    def currency_code(self) -> str:
        return self._currency_code

    @currency_code.setter
    def currency_code(self, value: str) -> None:
        self._currency_code = normalize_currency(value)

    @property
    def balance(self) -> float:
        return self._balance

    @balance.setter
    def balance(self, value) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("Баланс должен быть числом")
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")
        self._balance = float(value)

    def deposit(self, amount: float) -> None:
        if not is_positive_number(amount):
            raise ValueError("'amount' должен быть положительным числом")
        self.balance = self._balance + float(amount)

    def withdraw(self, amount: float) -> None:
        if not is_positive_number(amount):
            raise ValueError("'amount' должен быть положительным числом")
        amount = float(amount)
        if amount > self._balance:
            raise InsufficientFundsError(
                available=format_amount(self.currency_code, self._balance),
                required=format_amount(self.currency_code, amount),
                code=self.currency_code,
            )
        self.balance = self._balance - amount

    def get_balance_info(self) -> str:
        """Человекочитаемый баланс, например ``0.0100 BTC``."""
        amount = format_amount(self.currency_code, self._balance)
        return f"{amount} {self.currency_code}"

    def to_dict(self) -> dict:
        return {
            "currency_code": self.currency_code,
            "balance": self._balance,
        }

    @classmethod
    def from_dict(cls, currency_code: str, data: dict) -> "Wallet":
        code = data.get("currency_code", currency_code)
        return cls(currency_code=code, balance=data.get("balance", 0.0))


class Portfolio:
    """Набор кошельков пользователя: уникальность валют и оценка в базовой валюте."""

    def __init__(
        self,
        user_id: int,
        wallets: dict[str, Wallet] | None = None,
        user: User | None = None,
    ):
        self._user_id = user_id
        self._wallets: dict[str, Wallet] = wallets or {}
        self._user = user

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def user(self) -> User | None:
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        return self._wallets.copy()

    def add_currency(self, currency_code: str) -> Wallet:
        """Создаёт кошелёк, если валюты ещё нет в портфеле."""
        code = normalize_currency(currency_code)
        if code in self._wallets:
            raise ValueError(f"Данная валюта уже существует в кошельке: '{code}'")
        wallet = Wallet(code, 0.0)
        self._wallets[code] = wallet
        return wallet

    def get_wallet(self, currency_code: str) -> Wallet | None:
        return self._wallets.get(normalize_currency(currency_code))

    def get_or_create_wallet(self, currency_code: str) -> Wallet:
        code = normalize_currency(currency_code)
        wallet = self._wallets.get(code)
        if wallet is None:
            wallet = self.add_currency(code)
        return wallet

    def get_total_value(
        self,
        base_currency: str = DEFAULT_BASE_CURRENCY,
        exchange_rates: dict[str, float] | None = None,
    ) -> float:
        base = normalize_currency(base_currency)
        rates = exchange_rates or {}
        if base not in rates:
            raise ValueError(f"Неизвестная базовая валюта '{base}'")

        base_rate = rates[base]
        total = 0.0
        for code, wallet in self._wallets.items():
            rate = rates.get(code)
            if rate is None:
                raise ValueError(f"Не удалось получить курс для {code}→{base}")
            total += wallet.balance * rate / base_rate
        return total

    def to_dict(self) -> dict:
        return {
            "user_id": self._user_id,
            "wallets": {
                code: wallet.to_dict() for code, wallet in self._wallets.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict, user: User | None = None) -> "Portfolio":
        wallets = {
            code: Wallet.from_dict(code, payload)
            for code, payload in data.get("wallets", {}).items()
        }
        return cls(user_id=data["user_id"], wallets=wallets, user=user)
