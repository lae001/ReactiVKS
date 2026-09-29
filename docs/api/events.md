# События шины (Apache Kafka)

Брокер – Apache Kafka ([ADR-012](../adr/ADR-012-kafka.md)). Контракты описаны pydantic-моделями в
`backend/libs/vks_contracts` – это источник истины; документ дублирует их для чтения.

## Формат сообщения

| Часть сообщения Kafka | Содержимое |
|---|---|
| **key** | Ключ упорядочивания (UTF-8): `meeting_id` для событий встреч и отсчетов, `user_id` для `user.events` |
| **value** | JSON-конверт (UTF-8), см. ниже |
| **headers** | `event_type`, `event_id`, `event_version`, `producer`, `correlation_id` – дублируют поля конверта, чтобы потребитель мог отфильтровать сообщение без разбора тела |
| **timestamp** | `CreateTime` = `occurred_at` |

```json
{
  "event_id": "0192f1c4-…",          // UUIDv7, для идемпотентной обработки
  "type": "participant.joined",
  "version": 1,
  "occurred_at": "2026-11-20T07:05:11.204Z",
  "producer": "meeting-service",
  "correlation_id": "c0a8…",         // request_id исходного запроса (сквозная трассировка), может отсутствовать
  "payload": { … }
}
```

Правила эволюции: добавление необязательных полей – без смены `version`; удаление/переименование/смена смысла –
новая `version`, потребители поддерживают обе версии в переходный период. Schema Registry не используется:
совместимость проверяется в CI по JSON Schema, сгенерированной из `vks_contracts` ([ADR-012](../adr/ADR-012-kafka.md)).

## Топики

| Топик | Производитель | Ключ | Партиций | Хранение (`retention.ms`) | Группы потребителей |
|---|---|---|---|---|---|
| `emotion.samples` | emotion-ml-service | `meeting_id` | 6 | 1 ч | `realtime-<instance>`, `analytics` |
| `ml.status` | emotion-ml-service | `meeting_id` | 3 | 1 ч | `realtime-<instance>`, `meeting` |
| `meeting.events` | meeting-service (outbox) | `meeting_id` | 3 | 7 сут | `realtime-<instance>`, `analytics` |
| `report.events` | analytics-service (outbox) | `meeting_id` | 3 | 7 сут | `realtime-<instance>` |
| `user.events` | auth-service (outbox) | `user_id` | 1 | 7 сут | `meeting`, `analytics` |
| `<топик>.dlq` | потребитель, не сумевший обработать сообщение | как у исходного | 1 | 14 сут | – (разбор вручную) |

- Порядок гарантируется **внутри ключа**: все события одной встречи (а для `user.events` – одного пользователя)
  обрабатываются по порядку. Порядок между разными встречами не гарантируется и не требуется.
- Хранение `emotion.samples` – 1 ч: отсчеты эфемерны ([ADR-009](../adr/ADR-009-emotion-data-retention.md)), хранятся
  в брокере только для догонки потребителей после сбоя.
- Число партиций выбрано с запасом для параллелизма (6 потребителей analytics / ML-воркеров); на одном брокере
  коэффициент репликации = 1, `min.insync.replicas` = 1.
- Топики создаются заранее контейнером `kafka-init` ([06-deployment.md](../architecture/06-deployment.md)); автосоздание
  отключено (`auto.create.topics.enable=false`).

## Группы потребителей

| Группа | Сервис | Начальная позиция (`auto.offset.reset`) | Фиксация смещений |
|---|---|---|---|
| `analytics` | analytics-service | `earliest` | Вручную, после записи в БД ([conventions.md](../backend/conventions.md#7-потребление-событий)) |
| `meeting` | meeting-service | `earliest` для `user.events`, `latest` для `ml.status` (отдельные потребители) | Вручную, после обработки |
| `realtime-<instance>` | realtime-service | `latest` | Автоматически (доставка в реальном времени, пропущенное догружается через REST) |

realtime-service использует **отдельную группу на экземпляр** (`realtime-<HOSTNAME>`): каждой реплике нужны все события,
так как WebSocket-соединения организаторов распределены между репликами.

## Гарантии

- Производители: `acks=all`, `enable.idempotence=true` – без дублей при повторной отправке одним производителем.
- Доставка потребителям – **не менее одного раза**; потребители идемпотентны (дедупликация по `event_id` там, где повтор
  имеет побочный эффект, см. [conventions.md](../backend/conventions.md#7-потребление-событий)).
- Сервисы с БД публикуют через transactional outbox ([ADR-011](../adr/ADR-011-transactional-outbox.md)).

## `emotion.samples`

| type | payload |
|---|---|
| `emotion.sample` | см. ниже |

```json
{
  "meeting_id": "0192…",
  "participant_id": "0192…",
  "ts": "2026-11-20T07:12:03.643Z",     // время получения кадра сервисом
  "state": "analyzing",                 // analyzing | no_face | camera_off | no_consent
  "probs": {"angry": 0.03, "disgust": 0.01, "fear": 0.02, "happy": 0.21,
            "sad": 0.07, "surprise": 0.08, "neutral": 0.58},   // сглаженные; null если state ≠ analyzing
  "raw_dominant": "neutral",             // до сглаживания (для отладки качества)
  "dominant": "neutral",
  "confidence": 0.58,
  "face_box_area": 0.12,                 // доля площади кадра, для оценки качества (без координат)
  "model_version": "emotion-effnetb0@1.0.0"
}
```

Для экономии трафика `no_consent` и `camera_off` публикуются только при смене состояния, `no_face` – не чаще 1 раза в секунду.
Производитель ML-сервиса отправляет пакетами (`linger.ms=20`, сжатие `lz4`): задержка добавляется незначительная,
нагрузка на брокер снижается.

## `ml.status`

| type | payload |
|---|---|
| `ml.status` | `{"meeting_id", "state": "active" \| "degraded" \| "stopped", "effective_fps", "target_fps", "worker_id", "reason?"}` |

Публикуется при старте/остановке задания, при смене состояния и каждые 5 с (heartbeat).

## `meeting.events`

| type | payload |
|---|---|
| `meeting.created` | `{meeting_id, owner_id, title, scheduled_at, analysis_enabled}` |
| `meeting.updated` | `{meeting_id, title, scheduled_at, analysis_enabled}` |
| `meeting.started` | `{meeting_id, owner_id, title, started_at, analysis_enabled, analysis_fps}` |
| `meeting.ended` | `{meeting_id, ended_at, reason: "organizer" \| "empty_timeout" \| "admin"}` |
| `meeting.cancelled` | `{meeting_id}` |
| `meeting.deleted` | `{meeting_id}` – потребители удаляют свои данные |
| `participant.registered` | `{meeting_id, participant_id, display_name, role, consent_state}` |
| `participant.joined` | `{meeting_id, participant_id, joined_at}` |
| `participant.left` | `{meeting_id, participant_id, left_at, reason: "left" \| "removed" \| "disconnected"}` |
| `consent.changed` | `{meeting_id, participant_id, consent_state, notice_version, decided_at}` |

## `report.events`

| type | payload |
|---|---|
| `report.ready` | `{meeting_id, owner_id}` |
| `report.failed` | `{meeting_id, owner_id, reason}` |

## `user.events`

| type | payload |
|---|---|
| `user.blocked` | `{user_id}` |
| `user.unblocked` | `{user_id}` |
| `user.deleted` | `{user_id}` – meeting-service удаляет встречи пользователя (с публикацией `meeting.deleted`) |

## Конфигурация топиков (`deploy/kafka/topics.yaml`)

```yaml
defaults:
  replication_factor: 1
  config:
    cleanup.policy: delete
    compression.type: producer
topics:
  - {name: emotion.samples, partitions: 6, config: {retention.ms: 3600000, segment.ms: 600000}}
  - {name: ml.status,       partitions: 3, config: {retention.ms: 3600000, segment.ms: 600000}}
  - {name: meeting.events,  partitions: 3, config: {retention.ms: 604800000}}
  - {name: report.events,   partitions: 3, config: {retention.ms: 604800000}}
  - {name: user.events,     partitions: 1, config: {retention.ms: 604800000}}
  - {name: emotion.samples.dlq, partitions: 1, config: {retention.ms: 1209600000}}
  - {name: meeting.events.dlq,  partitions: 1, config: {retention.ms: 1209600000}}
  - {name: report.events.dlq,   partitions: 1, config: {retention.ms: 1209600000}}
  - {name: user.events.dlq,     partitions: 1, config: {retention.ms: 1209600000}}
```
