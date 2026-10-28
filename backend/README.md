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
| `make migrate` | Миграции всех сервисов к БД из `deploy/docker-compose.dev.yml` (`migrate-auth`, `migrate-meeting` – по одному) |
| `make jwt-key` | Ключ подписи JWT для локального запуска (`secrets/`, в git не попадает) |
| `make run-auth` | auth-service на http://127.0.0.1:8001 (`AUTH_PORT=…` – другой порт) |

## Локальный запуск auth-service

```bash
docker compose -f ../deploy/docker-compose.dev.yml up -d --wait   # PostgreSQL и Redis
cp services/auth_service/.env.example services/auth_service/.env
make sync migrate jwt-key run-auth
uv run --env-file services/auth_service/.env vks-auth create-admin --email admin@example.ru --display-name "Администратор"
```

Swagger UI – http://127.0.0.1:8001/docs. Dev-сервер фронтенда проксирует `/api` на `localhost:8080`: до появления
Nginx в compose запускайте `make run-auth AUTH_PORT=8080`.

Pre-commit (из корня репозитория, один раз на клон): `uv run --directory backend pre-commit install`.

## Структура

```text
backend/
├── conftest.py          # общие фикстуры тестов (PostgreSQL в контейнере)
├── libs/vks_common/     # шасси: конфиг, журналы, ошибки, фабрика приложения, БД, проверка JWT
└── services/
    ├── auth_service/    # учетные записи, вход, JWT RS256 и JWKS
    └── meeting_service/ # встречи, участники, согласия, токены LiveKit
```
