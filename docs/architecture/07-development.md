# 7. Разработка: репозиторий, инструменты, стандарты

## 7.1 Структура монорепозитория

```text
ReactiVKS/
├── frontend/                      # SPA: React + TypeScript + Vite
│   ├── src/
│   │   ├── app/                   # корневой компонент, роутер, провайдеры
│   │   ├── pages/                 # страницы (маршруты)
│   │   ├── features/              # auth, meetings, room, emotions, reports, admin, settings
│   │   └── shared/                # api-клиент, ui-компоненты, хуки, типы, legal/
│   ├── public/
│   ├── package.json
│   └── vite.config.ts
├── backend/
│   ├── pyproject.toml             # uv workspace: dev-зависимости, ruff, mypy, pytest, import-linter
│   ├── Makefile                   # lint, type, imports, test, migrate
│   ├── libs/
│   │   ├── vks_common/            # шасси: конфиг, журналы, ошибки, app, БД, проверка JWT, затем Kafka и outbox
│   │   └── vks_contracts/         # pydantic-модели событий шины и внутренних API
│   └── services/
│       ├── auth_service/
│       ├── meeting_service/
│       ├── realtime_service/
│       └── analytics_service/
│           ├── src/analytics_service/
│           │   ├── main.py        # сборка приложения, роутеры, lifespan
│           │   ├── settings.py    # pydantic-settings
│           │   ├── api/v1/        # вход: роутеры FastAPI и сборка зависимостей
│           │   ├── schemas/       # DTO запросов и ответов
│           │   ├── consumers/     # вход: потребители Kafka
│           │   ├── workers/       # вход: периодические задачи
│           │   ├── services/      # сценарии использования, границы транзакций
│           │   ├── domain/        # сущности, правила, порты (Protocol) – без ввода-вывода
│           │   ├── repositories/  # весь SQL, ORM ↔ доменные сущности
│           │   ├── models/        # ORM-модели SQLAlchemy
│           │   ├── adapters/      # реализации портов: криптография, Redis, LiveKit, SMTP
│           │   └── clients/       # исходящие вызовы других сервисов
│           ├── migrations/        # Alembic
│           ├── tests/             # unit/, integration/, api/
│           ├── pyproject.toml
│           └── Dockerfile
├── ml/
│   ├── emotion_service/           # сервис инференса (агент LiveKit)
│   │   ├── src/emotion_service/
│   │   ├── tests/
│   │   ├── pyproject.toml         # зависит от backend/libs/vks_contracts (path-зависимость)
│   │   └── Dockerfile             # варианты cpu / gpu
│   ├── training/                  # обучение и экспорт моделей
│   │   ├── configs/               # YAML-конфигурации экспериментов
│   │   ├── src/fer_training/      # датасеты, модели, обучение, оценка, экспорт ONNX
│   │   ├── notebooks/             # исследовательские ноутбуки
│   │   └── experiments.md         # журнал экспериментов
│   └── models/                    # model_card.json (веса – в Releases / Git LFS, не в git)
├── deploy/
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   ├── .env.example
│   ├── nginx/                     # конфигурация Nginx (http + stream)
│   ├── livekit/livekit.yaml
│   ├── postgres/init/00-init.sql  # роли и схемы (см. docs/backend/database.md)
│   ├── kafka/                     # server.properties, topics.yaml, create-topics.sh (топики, SCRAM, ACL)
│   ├── monitoring/                # prometheus.yml, дашборды Grafana
│   └── scripts/                   # gen-keys, init-certs, fetch-models, backup, restore
├── docs/
│   ├── architecture/              # уровень Системы
│   ├── adr/                       # архитектурные решения
│   ├── api/                       # контракты: REST, WebSocket, события, LiveKit
│   ├── backend/  ml/  frontend/   # устройство частей
├── .github/workflows/
└── README.md
```

Общий пакет `vks_contracts` – единственное место, где описаны форматы событий. Его используют все сервисы
`backend/` и `ml/emotion_service`; изменение контракта видно в одном pull request со всеми потребителями.

## 7.2 Внутренняя структура Python-сервиса

Слоистая архитектура (упрощенная «чистая архитектура»). Входы (`api`, `cli`, `consumers`, `workers`) вызывают
сценарии; сценарии управляют транзакциями и опираются на домен и репозитории; внешние системы скрыты за портами
домена, которые реализуются в `adapters/`.

```mermaid
flowchart LR
    IN["api/ · cli · consumers/ · workers/<br/>вход: разбор запроса, ответ"] --> SVC["services/<br/>сценарии, транзакции"]
    IN --> SCH["schemas/<br/>DTO"]
    SVC --> DOM["domain/<br/>сущности, правила,<br/>порты (Protocol)"]
    SVC --> REPO["repositories/<br/>SQL"]
    SVC --> CL["clients/<br/>другие сервисы"]
    REPO --> MOD["models/<br/>ORM"]
    REPO --> DOM
    AD["adapters/<br/>Argon2, RSA, Redis, LiveKit"] -. "реализует порт" .-> DOM
    MAIN["main.py<br/>корень сборки"] --> AD
    MAIN --> IN
```

- Зависимости сценариев передаются через конструктор; роутер собирает сценарий через `Depends` FastAPI, адаптеры
  создаются один раз в `main.py` и лежат в `app.state`. В тестах подменяются только внешние границы.
- Правила импорта между слоями проверяет `import-linter`; подробно – [coding-standards.md](../backend/coding-standards.md#23-правила-импорта-между-слоями).
- Асинхронный стек: `asyncpg`, `redis.asyncio`, `httpx`.
- Конфигурация – `pydantic-settings` из переменных окружения.

## 7.3 Инструменты

| Область | Инструмент |
|---|---|
| Python | 3.12, менеджер пакетов **uv** (workspace), Ruff (lint + format), mypy (strict для всего кода, кроме миграций и тестов), import-linter (границы слоев) |
| Тесты Python | pytest, pytest-asyncio, httpx `AsyncClient`, testcontainers (PostgreSQL, Redis, Kafka), coverage |
| Брокер | `aiokafka` (обертка `vks_common.kafka`); локально – `kafka-ui` для просмотра топиков |
| TypeScript | Node 22 LTS, **pnpm**, ESLint (typescript-eslint, react-hooks), Prettier |
| Тесты frontend | Vitest + Testing Library; Playwright для e2e (две вкладки с фейковой камерой `--use-fake-device-for-media-stream`) |
| API | Контракт описан в `docs/api/rest-api.md`; OpenAPI генерируется FastAPI из кода; типы клиента – `openapi-typescript` (`pnpm gen:api`) |
| БД | Alembic |
| ML | PyTorch, timm, albumentations, OpenCV, ONNX, onnxruntime; Jupyter |
| Контейнеры | Docker, Docker Compose; многоступенчатые Dockerfile, non-root пользователь |
| Pre-commit | `pre-commit`: ruff, mypy, import-linter, запрет коммита в `main`, `detect-private-key`, проверка Conventional Commits (commitizen) |

## 7.4 Стандарты кодирования (из концепции, п. 8.5)

Полные правила бэкенда – [coding-standards.md](../backend/coding-standards.md). Кратко:

- Python – PEP 8, PEP 257, аннотации типов обязательны; форматирование Ruff.
- TypeScript – строгий режим (`strict: true`), ESLint + Prettier, общая конфигурация в `frontend/`.
- Идентификаторы – на английском; комментарии, docstring, документация – на русском.
- БД – `snake_case`, миграции только через Alembic, без ручных изменений схемы.
- REST – ресурсы во множественном числе, `kebab-case` в путях, `snake_case` в JSON, версия `/api/v1`.
- Ошибки REST – единый формат (RFC 9457 Problem Details):
  `{"type": "...", "title": "...", "status": 409, "detail": "...", "code": "meeting_not_started"}`.

## 7.5 Git и процесс

- Модель ветвления **GitHub Flow**: `main` всегда рабочая; ветка на задачу `feat/EMO-<N>-short-name`, `fix/…`,
  `docs/…`, `ci/…`; зависимые задачи – стеком веток.
- Коммиты – **Conventional Commits** на русском с областью = сервис и ключом задачи:
  `feat(meeting): выдача токенов LiveKit (EMO-63)`; коммиты атомарные.
- Слияние только через pull request, минимум одно ревью (архитектор принимает код, п. 5.2 устава), зеленый CI.
- Изменение контрактов (`vks_contracts`, REST API, протокол WebSocket, топики Kafka) – обязательно с обновлением `docs/api/*`.
- Подробно и чек-лист ревью – [coding-standards.md](../backend/coding-standards.md#15-git-и-ревью).

## 7.6 Непрерывная интеграция (GitHub Actions)

| Job | Триггер (paths) | Шаги |
|---|---|---|
| `backend` (`.github/workflows/backend.yml`) | `backend/**`, `deploy/postgres/**` | ruff, mypy, import-linter; pytest + coverage (порог 60 %) с PostgreSQL в testcontainers. Сборка Docker-образов – вместе с Dockerfile сервисов (развертывание в compose) |
| `ml-service` | `ml/emotion_service/**`, `backend/libs/vks_contracts/**` | ruff, mypy, pytest (на маленькой тестовой модели), сборка образа |
| `frontend` | `frontend/**` | eslint, tsc, vitest, `vite build` |
| `contracts` | `backend/libs/vks_contracts/**`, `docs/api/**` | Проверка совместимости схем событий (генерация JSON Schema и diff) |
| `e2e` | ручной запуск / ночью | `docker compose -f deploy/docker-compose.dev.yml up`, Playwright |
| `release` | тег `v*` | Публикация образов в GHCR |

Риск недоступности GitHub (риск 8 устава): зеркало репозитория в GitVerse/GitLab, workflow-файлы держатся простыми
(`make`-цели), чтобы их было легко перенести.

## 7.7 Стратегия тестирования (архитектурный уровень)

| Уровень | Что проверяется | Инструменты |
|---|---|---|
| Модульные | domain/services сервисов, агрегация рядов, детектор ключевых моментов, сглаживание, препроцессинг кадров | pytest, Vitest |
| Интеграционные | Репозитории + PostgreSQL, производители/потребители + Kafka (outbox, фиксация смещений, DLQ), вебхуки LiveKit (записанные фикстуры) | testcontainers |
| Контрактные | Схемы событий `vks_contracts`, OpenAPI ↔ типы клиента | pydantic JSON Schema, openapi-typescript |
| Сквозные (e2e) | UC-2…UC-5 в двух браузерах с фейковым видео (заранее записанные ролики с эмоциями) | Playwright |
| Нагрузочные | 5 встреч × 10 участников: CPU/RAM, задержка медиа, фактическая частота анализа, задержка панели | `lk load-test` (LiveKit CLI) + ML-агент, метрики Prometheus |
| Качество модели | accuracy, macro-F1, матрица ошибок на тестовой выборке и на записях встреч команды | `ml/training` (скрипт `evaluate`) |
| Сети | Соединение через TURN, ограничение канала | `chrome://webrtc-internals`, `tc netem` |

Задержку панели эмоций измеряет сам фронтенд: разница между `ts` отсчета и временем отрисовки
(часы синхронизируются по `server_time` в сообщении `welcome` протокола WebSocket).
