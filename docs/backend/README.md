# Бэкенд

Ответственный – Халецкий Д. Е. (архитектор, бэкенд).

## Документы

| Документ | Содержание |
|---|---|
| [conventions.md](conventions.md) | Общие правила сервисов: `vks_common`, ошибки, межсервисные вызовы, outbox, потребители Kafka, БД, health, журналы, тесты |
| [database.md](database.md) | Физическая схема PostgreSQL: DDL, ограничения, индексы, роли |
| [background-jobs.md](background-jobs.md) | Фоновые задачи и потребители событий всех сервисов |
| [auth-service.md](auth-service.md) | Учетные записи, JWT, восстановление пароля, администрирование пользователей |
| [meeting-service.md](meeting-service.md) | Встречи, участники, согласия, интеграция с LiveKit |
| [realtime-service.md](realtime-service.md) | WebSocket-шлюз панели эмоций |
| [analytics-service.md](analytics-service.md) | Ряды, отчеты, экспорт |

## Контракты, которые бэкенд предоставляет

| Контракт | Потребители | Документ |
|---|---|---|
| REST API | frontend | [api/rest-api.md](../api/rest-api.md) |
| WebSocket `vks.v1` | frontend | [api/websocket-protocol.md](../api/websocket-protocol.md) |
| События Kafka | сервисы, ML | [api/events.md](../api/events.md) |
| Токены и атрибуты LiveKit | frontend, ML | [api/livekit-integration.md](../api/livekit-integration.md) |

Изменение контракта – pull request с обновлением соответствующего документа и ревью стороны-потребителя.

## Порядок реализации (итерация 1 → 2)

1. `vks_common` (app, config, errors, auth, db, logging) + `vks_contracts` – основа для всех сервисов.
2. auth-service → meeting-service (без согласия) → интеграция с LiveKit – видеовстреча работает.
3. Kafka в compose + `vks_common.kafka` (производитель, потребитель, outbox-релей) → события и согласие в meeting-service.
4. realtime-service → analytics-service (ряды) → отчет → экспорт.
