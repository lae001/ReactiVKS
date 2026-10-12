# ReactiVKS – бэкенд

Python-сервисы и общая библиотека в одном uv workspace. Устройство – [docs/backend](../docs/backend/README.md),
правила написания кода – [coding-standards.md](../docs/backend/coding-standards.md).

## Требования

- [uv](https://docs.astral.sh/uv/) 0.12+ (Python 3.12 uv поставит сам)
- Docker – для интеграционных тестов (testcontainers) и локальной инфраструктуры

## Команды

Из каталога `backend/`:

| Команда | Что делает |
|---|---|
| `make sync` | Окружение `.venv` по `uv.lock` |
| `make lint` / `make format` | ruff: проверка / исправление стиля |
| `make type` | mypy `--strict` по каждому пакету |
| `make imports` | import-linter: границы слоев |
| `make test` / `make test-unit` | Все тесты / только без Docker |
| `make cov` | Тесты с покрытием, порог 60 % |
| `make check` | Все проверки, как в CI |

Pre-commit (из корня репозитория, один раз на клон): `uv run --directory backend pre-commit install`.

## Структура

```text
backend/
├── libs/vks_common/     # шасси: конфиг, журналы, ошибки, фабрика приложения, БД, проверка JWT
└── services/            # сервисы, по каталогу на сервис
```
