# Развертывание

| Файл | Назначение |
|---|---|
| `docker-compose.dev.yml` | Инфраструктура для локальной разработки: PostgreSQL 16, Redis 7 |
| `postgres/init/` | Роли и схемы сервисов при создании тома ([database.md](../docs/backend/database.md#инициализация-бд)) |
| `.env.example` | Шаблон паролей; `deploy/.env` в git не попадает |

Полная схема развертывания – [06-deployment.md](../docs/architecture/06-deployment.md).

## Локальная разработка

```bash
docker compose -f deploy/docker-compose.dev.yml up -d --wait   # PostgreSQL на 127.0.0.1:5432, Redis на 127.0.0.1:6379
docker compose -f deploy/docker-compose.dev.yml down            # остановить, данные сохраняются в томе pgdata
docker compose -f deploy/docker-compose.dev.yml down -v         # удалить и том: init-скрипт выполнится заново
```

| Роль | Схема | Пароль по умолчанию | `DATABASE_URL` сервиса |
|---|---|---|---|
| `auth_svc` | `auth` | `auth-dev-password` | `postgresql+asyncpg://auth_svc:auth-dev-password@localhost:5432/vks` |
| `meeting_svc` | `meeting` | `meeting-dev-password` | `postgresql+asyncpg://meeting_svc:meeting-dev-password@localhost:5432/vks` |
| `analytics_svc` | `analytics` | `analytics-dev-password` | `postgresql+asyncpg://analytics_svc:analytics-dev-password@localhost:5432/vks` |

Init-скрипт выполняется только на пустом томе: после изменения `postgres/init/` или паролей том пересоздается
(`down -v`).
