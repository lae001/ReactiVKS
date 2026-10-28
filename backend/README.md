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
| `make contracts-snapshot` | Обновить снимок JSON Schema событий – вместе с `docs/api/events.md` |
| `make migrate` | Миграции всех сервисов к БД из `deploy/docker-compose.dev.yml` (`migrate-auth`, `migrate-meeting` – по одному) |
| `make jwt-key` | Ключ подписи JWT для локального запуска (`secrets/`, в git не попадает) |
| `make run-auth` | auth-service на http://127.0.0.1:8001 (`AUTH_PORT=…` – другой порт) |
| `make run-meeting` | meeting-service на http://127.0.0.1:8002 (`MEETING_PORT=…` – другой порт) |

## Локальный запуск auth-service

```bash
docker compose -f ../deploy/docker-compose.dev.yml up -d --wait postgres redis
cp services/auth_service/.env.example services/auth_service/.env
make sync migrate jwt-key run-auth
uv run --env-file services/auth_service/.env vks-auth create-admin --email admin@example.ru --display-name "Администратор"
```

Swagger UI – http://127.0.0.1:8001/docs. Dev-сервер фронтенда проксирует `/api` на auth-service
(`VITE_DEV_API_TARGET`, по умолчанию `http://127.0.0.1:8001`).

## Локальный запуск meeting-service

Нужны PostgreSQL, LiveKit и запущенный auth-service (по его JWKS проверяются access-токены):

```bash
docker compose -f ../deploy/docker-compose.dev.yml up -d --wait postgres livekit
cp services/meeting_service/.env.example services/meeting_service/.env
make migrate run-meeting
```

Swagger UI – http://127.0.0.1:8002/docs. Сценарий проверки «организатор и гость в одной комнате»:

```bash
TOKEN=$(curl -s localhost:8001/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"email": "ivan@example.ru", "password": "correct-horse-7"}' | jq -r .access_token)
MEETING=$(curl -s localhost:8002/api/v1/meetings -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"title": "Демонстрация"}')
curl -s localhost:8002/api/v1/meetings/$(echo $MEETING | jq -r .id)/join -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"consent": "granted"}' | jq -r .livekit_token          # токен организатора
curl -s localhost:8002/api/v1/join/$(echo $MEETING | jq -r .invite_code) -H 'content-type: application/json' \
  -d '{"display_name": "Анна", "consent": "granted", "notice_version": "v1-draft"}' | jq -r .livekit_token  # токен гостя
```

Токены вставляются на странице фронтенда `/dev/livekit` (адрес сервера – `ws://localhost:7880`) в двух вкладках:
участники видят и слышат друг друга.

Pre-commit (из корня репозитория, один раз на клон): `uv run --directory backend pre-commit install`.

## Структура

```text
backend/
├── conftest.py          # общие фикстуры тестов (PostgreSQL в контейнере)
├── libs/vks_common/     # шасси: конфиг, журналы, ошибки, фабрика приложения, БД, проверка JWT
├── libs/vks_contracts/  # контракты событий Kafka: конверт, payload, топики (только pydantic)
└── services/
    ├── auth_service/    # учетные записи, вход, JWT RS256 и JWKS
    └── meeting_service/ # встречи, участники, согласия, токены LiveKit
```
