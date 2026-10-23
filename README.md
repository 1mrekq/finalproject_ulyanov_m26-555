# ValutaTrade Hub

Платформа для управления виртуальным портфелем фиатных и криптовалют: регистрация, вход, покупка/продажа и просмотр курсов через CLI.

## Запуск

```bash
uv sync
uv run valutatrade-hub
```

## Команды

```
register --username <str> --password <str>
login --username <str> --password <str>
show-portfolio [--base <str>]
buy --currency <str> --amount <float>
sell --currency <str> --amount <float>
get-rate --from <str> --to <str>
currencies
help [команда]
exit
```

Раздел «Ошибки» у команды: `help buy`, `help sell`, `help get-rate`.
Данные хранятся в JSON-файлах каталога `data/`, журнал операций — в `logs/actions.log`.
