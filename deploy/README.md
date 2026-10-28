# Развертывание

| Файл | Назначение |
|---|---|
| `docker-compose.dev.yml` | Инфраструктура для локальной разработки: PostgreSQL 16, Redis 7, Kafka (KRaft), kafka-ui, LiveKit |
| `docker-compose.yml` | Система целиком: nginx со статикой SPA, auth- и meeting-service, миграции, инфраструктура (EMO-71) |
| `nginx/` | Образ nginx: сборка фронтенда и маршрутизация `/api/v1/*` по сервисам |
| `postgres/init/` | Роли и схемы сервисов при создании тома ([database.md](../docs/backend/database.md#инициализация-бд)) |
| `kafka/` | Топики ([events.md](../docs/api/events.md#топики)) и скрипт их создания для контейнера `kafka-init` |
| `livekit/livekit.dev.yaml` | Конфигурация LiveKit для разработки ([livekit-integration.md](../docs/api/livekit-integration.md)) |
| `.env.example` | Шаблон паролей; `deploy/.env` в git не попадает |

Полная схема развертывания – [06-deployment.md](../docs/architecture/06-deployment.md).

## Система целиком (`docker-compose.yml`)

```bash
cp deploy/.env.example deploy/.env           # заполнить пароли, LIVEKIT_API_KEY и LIVEKIT_API_SECRET (≥ 32 символов)
(cd backend && make jwt-key) && cp backend/secrets/jwt-private.pem deploy/secrets/   # ключ подписи JWT
docker compose -f deploy/docker-compose.dev.yml down                                 # LiveKit обоих – в сети хоста
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build --wait
docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec auth-service \
    vks-auth create-admin --email admin@example.ru --display-name "Администратор"
```

Открыть <http://localhost> (порт – `NGINX_HTTP_PORT`). Порядок старта: `postgres` → `migrate-auth`, `migrate-meeting`
(миграции ролями сервисов) → `auth-service` → `meeting-service` → `nginx`; `kafka` → `kafka-init` (топики).
Образы Python-сервисов собираются одним `backend/Dockerfile` с аргументом `PACKAGE`.

| Путь | Куда |
|---|---|
| `/api/v1/auth/`, `/api/v1/users/`, `/api/v1/admin/users` | auth-service |
| `/api/v1/meetings`, `/join/`, `/participants/`, `/settings`, `/admin/meetings`, `/admin/health` | meeting-service |
| остальное | статика SPA (`index.html` для маршрутов фронтенда) |

`/webhooks`, `/internal`, `/health`, `/ready` наружу не проксируются. LiveKit присылает вебхуки на
`127.0.0.1:${MEETING_WEBHOOK_PORT}` – ключом `LIVEKIT_API_KEY`, конфигурация LiveKit задается в compose
(`LIVEKIT_CONFIG`). kafka-ui – профиль `dev`: `--profile dev`, <http://127.0.0.1:8090>.

## Локальная разработка

```bash
docker compose -f deploy/docker-compose.dev.yml up -d --wait   # все сервисы
docker compose -f deploy/docker-compose.dev.yml up -d --wait postgres redis   # только БД и Redis
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

## Сервисы и адреса

| Сервис | Адрес с хоста | Назначение |
|---|---|---|
| `postgres` | `127.0.0.1:5432` | БД, по схеме на сервис |
| `redis` | `127.0.0.1:6379` | Служебные ключи (пароль `redis-dev-password`) |
| `kafka` | `localhost:9092` (из контейнеров – `kafka:19092`) | Шина событий; топики создает `kafka-init`, автосоздание выключено |
| `kafka-ui` | <http://127.0.0.1:8090> | Просмотр топиков и сообщений |
| `livekit` | `ws://localhost:7880` (сигнализация и Server API), 7881/tcp, 7882/udp, 3478/udp | Медиасервер; сеть хоста |

## LiveKit

Ключи API – `LIVEKIT_API_KEY` и `LIVEKIT_API_SECRET` (по умолчанию `devkey` и
`dev-secret-change-me-0123456789abcdef`). Сервер получает их переменной `LIVEKIT_KEYS`, в YAML они не хранятся.
Те же значения задаются meeting-service: токены, которые он выпускает, LiveKit проверяет этим секретом.

Проверка со второго компьютера в локальной сети: `LIVEKIT_NODE_IP=<IP этого компьютера в LAN>` в `deploy/.env`,
адрес сервера на странице – `ws://<IP>:7880`. Камера в браузере доступна только в безопасном контексте
(`https://` или `localhost`).

e2e-тесты фронтенда (`pnpm test:e2e:livekit`) по умолчанию рассчитаны на `livekit-server --dev` (`devkey` /
`secret`); с этим LiveKit они запускаются с теми же ключами:

```bash
LIVEKIT_API_KEY=devkey LIVEKIT_API_SECRET=dev-secret-change-me-0123456789abcdef pnpm test:e2e:livekit
```

## Kafka

Топики, число партиций и срок хранения – в `kafka/topics.yaml` (повторяет [events.md](../docs/api/events.md#топики)).
`kafka-init` выполняется при каждом `up`, создает недостающие топики и приводит `retention.ms` к описанному; число
партиций только растет.

```bash
docker compose -f deploy/docker-compose.dev.yml logs kafka-init   # какие топики созданы
```
