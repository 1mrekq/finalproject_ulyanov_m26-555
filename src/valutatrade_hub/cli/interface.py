import shlex

from valutatrade_hub.core.currencies import supported_codes
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.storage import initialize_storage
from valutatrade_hub.core.usecases import (
    buy,
    get_rate,
    login_user,
    register_user,
    sell,
    show_portfolio,
)

CMD_HELP = "help"
CMD_EXIT = "exit"
CMD_REGISTER = "register"
CMD_LOGIN = "login"
CMD_SHOW_PORTFOLIO = "show-portfolio"
CMD_BUY = "buy"
CMD_SELL = "sell"
CMD_GET_RATE = "get-rate"

FUNDS_ERROR = (
    "Недостаточно средств: доступно {available} {code}, требуется {required} {code}"
)
API_ERROR = "Ошибка при обращении к внешнему API: {reason}"
UNKNOWN_CURRENCY_ERROR = "Неизвестная валюта '<code>'"
MISSING_WALLET_ERROR = (
    "У вас нет кошелька 'BTC'. Добавьте валюту: "
    "она создаётся автоматически при первой покупке."
)

COMMAND_ERRORS = {
    CMD_REGISTER: (
        "Имя пользователя '<name>' уже занято",
        "Пароль должен быть не короче 4 символов",
    ),
    CMD_LOGIN: (
        "Пользователь '<name>' не найден",
        "Неверный пароль",
    ),
    CMD_SHOW_PORTFOLIO: (
        "Сначала выполните login",
        "Неизвестная базовая валюта 'ABC'",
    ),
    CMD_BUY: (
        "'amount' должен быть положительным числом",
        UNKNOWN_CURRENCY_ERROR,
        FUNDS_ERROR,
        API_ERROR,
    ),
    CMD_SELL: (
        MISSING_WALLET_ERROR,
        FUNDS_ERROR,
        UNKNOWN_CURRENCY_ERROR,
        API_ERROR,
    ),
    CMD_GET_RATE: (
        UNKNOWN_CURRENCY_ERROR,
        API_ERROR,
    ),
}

current_user = None


def help_command(topic: str | None = None) -> None:
    if topic is None:
        print("Доступные команды:")
        print("  register --username <str> --password <str>")
        print("  login --username <str> --password <str>")
        print("  show-portfolio [--base <str>]")
        print("  buy --currency <str> --amount <float>")
        print("  sell --currency <str> --amount <float>")
        print("  get-rate --from <str> --to <str>")
        print("  help [команда]")
        print("  exit")
        print("Подробности и раздел «Ошибки»: help get-rate")
        return

    errors = COMMAND_ERRORS.get(topic)
    if errors is None:
        print(f"Нет справки для '{topic}'. Введите help для списка команд.")
        return

    print(f"Команда {topic}")
    print("Ошибки:")
    for index, message in enumerate(errors, start=1):
        print(f"  {index}) {message}")
    if topic == CMD_GET_RATE:
        print(f"Поддерживаемые коды: {', '.join(supported_codes())}")


def tokenize(user_input: str) -> list[str]:
    lexer = shlex.shlex(user_input, posix=True)
    lexer.whitespace_split = True
    lexer.whitespace = " \t\r\n"
    return list(lexer)


def print_invalid_value(command: str, command_args: list[str]) -> None:
    value = " ".join(command_args) if command_args else command
    print(f"Некорректное значение: {value}. Попробуйте снова.")


def parse_named_args(command_args, required=(), optional=()):
    allowed = set(required) | set(optional)
    parsed = {}
    index = 0
    while index < len(command_args):
        flag = command_args[index]
        if flag not in allowed or index + 1 >= len(command_args):
            return None
        value = command_args[index + 1]
        if flag in parsed or value.startswith("--"):
            return None
        parsed[flag] = value
        index += 2
    if any(flag not in parsed for flag in required):
        return None
    return parsed


def require_login():
    if current_user is None:
        raise ValueError("Сначала выполните login")
    return current_user


def handle_command_error(error: Exception) -> None:
    if isinstance(error, InsufficientFundsError):
        print(error)
        return
    if isinstance(error, CurrencyNotFoundError):
        print(error)
        print("Введите help get-rate для справки и списка поддерживаемых кодов.")
        print(f"Поддерживаемые коды: {', '.join(supported_codes())}")
        return
    if isinstance(error, ApiRequestError):
        print(error)
        print("Повторите попытку позже и проверьте подключение к сети.")
        return
    print(error)


def run() -> None:
    global current_user
    initialize_storage()
    help_command()

    while True:
        try:
            user_input = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        try:
            args = tokenize(user_input)
        except ValueError:
            print_invalid_value(user_input, [])
            continue

        if not args:
            continue

        command, *command_args = args

        try:
            if command == CMD_EXIT:
                break
            if command == CMD_HELP:
                topic = command_args[0] if command_args else None
                help_command(topic)
            elif command == CMD_REGISTER:
                parsed = parse_named_args(
                    command_args, required=("--username", "--password")
                )
                if parsed is None:
                    print_invalid_value(user_input, command_args)
                    continue
                username = parsed["--username"]
                user_id = register_user(username, parsed["--password"])
                print(
                    f"Пользователь '{username}' зарегистрирован (id={user_id}). "
                    f"Войдите: login --username {username} --password ****"
                )
            elif command == CMD_LOGIN:
                parsed = parse_named_args(
                    command_args, required=("--username", "--password")
                )
                if parsed is None:
                    print_invalid_value(user_input, command_args)
                    continue
                username = parsed["--username"]
                current_user = login_user(username, parsed["--password"])
                print(f"Вы вошли как '{current_user.username}'")
            elif command == CMD_SHOW_PORTFOLIO:
                parsed = parse_named_args(command_args, optional=("--base",))
                if parsed is None:
                    print_invalid_value(user_input, command_args)
                    continue
                user = require_login()
                base = parsed.get("--base", "USD")
                print(show_portfolio(user, base))
            elif command == CMD_BUY:
                parsed = parse_named_args(
                    command_args, required=("--currency", "--amount")
                )
                if parsed is None:
                    print_invalid_value(user_input, command_args)
                    continue
                user = require_login()
                print(buy(user, parsed["--currency"], parsed["--amount"]))
            elif command == CMD_SELL:
                parsed = parse_named_args(
                    command_args, required=("--currency", "--amount")
                )
                if parsed is None:
                    print_invalid_value(user_input, command_args)
                    continue
                user = require_login()
                print(sell(user, parsed["--currency"], parsed["--amount"]))
            elif command == CMD_GET_RATE:
                parsed = parse_named_args(command_args, required=("--from", "--to"))
                if parsed is None:
                    print_invalid_value(user_input, command_args)
                    continue
                print(get_rate(parsed["--from"], parsed["--to"]))
            else:
                print(f"Неизвестная команда: {command}. Введите help для справки.")
        except (
            InsufficientFundsError,
            CurrencyNotFoundError,
            ApiRequestError,
            ValueError,
        ) as error:
            handle_command_error(error)
