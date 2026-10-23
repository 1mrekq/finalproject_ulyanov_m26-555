# ValutaTrade Hub

Платформа виртуального портфеля фиатных и криптовалют. 
* Core Service хранит пользователей и кошельки в JSON, считает сделки по локальному кэшу курсов. 
* Parser Service отдельно опрашивает CoinGecko и ExchangeRate-API, записывает снепшот в `data/rates.json` и историю в `data/exchange_rates.json`.

## Структура каталогов

```
finalproject_ulyanov_m26-555/
├── data/
│   ├── users.json
│   ├── portfolios.json
│   ├── rates.json              # кэш для Core (TTL)
│   └── exchange_rates.json     # история Parser Service
├── valutatrade_hub/
│   ├── logging_config.py
│   ├── decorators.py
│   ├── core/                   # модели, usecases, валюты, исключения
│   ├── infra/                  # SettingsLoader, DatabaseManager
│   ├── parser_service/         # API-клиенты, updater, storage, scheduler
│   └── cli/interface.py
├── docs/
│   └── demo.cast               # запись asciinema
├── main.py
├── pyproject.toml
├── .env.example
└── README.md
```

## Установка и запуск

```bash
uv sync
uv run valutatrade-hub
# или
uv run python main.py
```

Проверка стиля:

```bash
uv run ruff check .
```

## Кэш курсов и TTL

Команды `buy`, `sell`, `get-rate` и `show-portfolio` читают `data/rates.json`.

Срок жизни кэша задаётся в `pyproject.toml`:

```toml
[tool.valutatrade]
rates_ttl_seconds = 300
base_currency = "USD"
```

Если `last_refresh` старше TTL, CLI пишет: «Данные курсов устарели. Выполните 'update-rates', чтобы обновить кеш.» Пустой файл — просьба сначала вызвать `update-rates`.

## Parser Service и API-ключ

1. Зарегистрируйтесь на [ExchangeRate-API](https://www.exchangerate-api.com/) и скопируйте ключ.
2. Скопируйте `.env.example` в `.env` (файл в `.gitignore`):

```bash
cp .env.example .env
```

```
EXCHANGERATE_API_KEY=ваш_ключ
```

CoinGecko в учебном режиме работает без ключа.

Ручное обновление из CLI:

```
update-rates
update-rates --source coingecko
update-rates --source exchangerate
show-rates
show-rates --currency BTC
show-rates --top 2
```

Периодический опрос в текущем процессе:

```bash
uv run python -c "from valutatrade_hub.parser_service.scheduler import RateScheduler; RateScheduler().run()"
```

Журнал парсера: `logs/parser.log`. 
Формат логов (`text` или `json`) — ключ `log_format` в `[tool.valutatrade]`, ротация — `log_max_bytes` / `log_backup_count`. 
Действия пользователя (`register` / `login` / `buy` / `sell`) пишутся в `logs/actions.log` декоратором `@log_action`.

## Примеры команд CLI

Стартовый баланс появляется покупкой базовой валюты (`USD`): это пополнение без списания с другого кошелька.

```
> register --username alice --password secret
Пользователь 'alice' зарегистрирован (id=1). Войдите: login --username alice --password ****

> login --username alice --password secret
Вы вошли как 'alice'

> update-rates
INFO: Starting rates update...
INFO: Fetching from CoinGecko... OK (3 rates)
INFO: Fetching from ExchangeRate-API... OK (3 rates)
INFO: Writing 6 rates to data/rates.json...
Update successful. Total rates updated: 6. Last refresh: 2026-10-23T16:43:38Z

> buy --currency USD --amount 10000
> buy --currency BTC --amount 0.01
> sell --currency BTC --amount 0.005
> show-portfolio
> show-portfolio --base EUR
> get-rate --from BTC --to USD
> currencies
> help buy
> exit
```

Ошибки (как в справке `help buy` / `help sell`):

```
> buy --currency BTC --amount 100
Недостаточно средств: доступно ... USD, требуется ... USD

> get-rate --from AAA --to USD
Неизвестная валюта 'AAA'
```

## Демо

Полный цикл CLI: register → login → update-rates / show-rates → buy/sell → show-portfolio → get-rate, плюс ошибки «недостаточно средств» и «неизвестная валюта».

[![asciicast](https://asciinema.org/a/pbEB3bqMjhfCoQqg.svg)](https://asciinema.org/a/pbEB3bqMjhfCoQqg)

Запись: https://asciinema.org/a/pbEB3bqMjhfCoQqg

Локально:

```bash
asciinema play docs/demo.cast
```
