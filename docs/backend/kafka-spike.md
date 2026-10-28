# Спайк 3. Kafka и transactional outbox (EMO-52)

Цель – подтвердить на реальном запуске решения [ADR-011](../adr/ADR-011-transactional-outbox.md) и
[ADR-012](../adr/ADR-012-kafka.md): событие, записанное сервисом в outbox в одной транзакции с изменением данных,
доходит до потребителя через Kafka быстрее 1 с, без потерь и с порядком внутри ключа.

## Что сделано

| Часть | Где | Назначение |
|---|---|---|
| `EventProducer` | `vks_common.kafka.producer` | `acks=all`, `enable_idempotence`, `linger_ms=5`, сжатие `lz4`; пачка отправляется и подтверждается целиком |
| `outbox_table`, `OutboxWriter` | `vks_common.kafka.outbox` | Таблица `outbox` в схеме сервиса; запись конверта события в транзакции сценария |
| `OutboxRelay` | `vks_common.kafka.outbox` | Фоновая задача: `SELECT … FOR UPDATE SKIP LOCKED` по возрастанию `id`, отправка, `published_at`; просыпается по сигналу после фиксации или раз в 1 с |
| `EventConsumer` | `vks_common.kafka.consumer` | Ручная фиксация смещений после обработки, последовательная обработка партиции, повторы `TemporaryFailure`, DLQ `<топик>.dlq` |
| Контракты | `vks_contracts` (EMO-50) | Конверт, payload, разбор `parse_event`: неизвестный тип – пропуск, нарушение контракта – DLQ |
| meeting-service | миграция `0002_outbox`, `repositories/outbox.py` | `meeting.created`, `meeting.started`, `participant.registered`, `consent.changed`, `meeting.ended` пишутся в outbox той же транзакцией |

Сигнал релею: фабрика сессий сервиса кладет в `session.info` функцию `OUTBOX_NOTIFY`; `OutboxWriter` вешает на
сессию обработчик `after_commit`, который будит релей один раз на транзакцию. Откатившаяся транзакция релей не
будит и событий не оставляет.

## Как проверялось

Интеграционные тесты `backend/libs/vks_common/tests/integration/test_kafka.py` на настоящих PostgreSQL 16 и Kafka
(testcontainers, KRaft):

| Проверка | Результат |
|---|---|
| Событие из outbox доходит до потребителя, `published_at` проставлен | ✓ |
| Откатившаяся транзакция ничего не публикует | ✓ |
| 20 событий одной встречи приходят в порядке записи | ✓ |
| Неизвестный тип пропускается, нарушение контракта уходит в `meeting.events.dlq` с заголовками `error`, `source_topic`, `source_offset` | ✓ |
| `TemporaryFailure` повторяется без продвижения смещения; после успеха смещение зафиксировано – новая сессия группы сообщение не получает | ✓ |
| **Задержка** «фиксация транзакции → обработчик потребителя», 100 событий по одному на транзакцию | **p50 = 16,6 мс, p95 = 18,7 мс, max = 30,1 мс** |

```bash
cd backend && uv run pytest libs/vks_common/tests/integration/test_kafka.py -s   # печатает замер задержки
```

Проверка на dev-окружении (`deploy/docker-compose.dev.yml`, `apache/kafka:4.1.0`): meeting-service с
`KAFKA_BOOTSTRAP_SERVERS=localhost:9092`, сценарий «создать – войти – завершить». В `meeting.events` пришли
`meeting.created`, `meeting.started`, `participant.registered`, `meeting.ended` с ключом `meeting_id`, заголовками
`event_type`, `event_id`, `event_version`, `producer` и `correlation_id` = `request_id` запроса; строки outbox помечены
отправленными. `/ready` показывает `kafka: ok`.

```bash
docker compose -f deploy/docker-compose.dev.yml exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic meeting.events --from-beginning --property print.headers=true
```

## Выводы

- Критерий спринта выполнен с запасом: задержка на два порядка ниже 1 с. Основной вклад – сигнал после фиксации;
  без него задержка определялась бы интервалом опроса (до 1 с).
- Kafka для meeting-service некритична: сервис стартует без брокера, события копятся в outbox, релей
  переподключается каждые 5 с и отправляет накопленное по порядку.
- Отправка пачки держит строки outbox заблокированными (`FOR UPDATE SKIP LOCKED`) только на время подтверждения
  брокером – сценарии в эти строки не пишут, поэтому не ждут.

## Ограничения и что дальше

| Ограничение | Когда снимается |
|---|---|
| Релей один на процесс; защиты от параллельной работы на нескольких репликах (распределенная блокировка) нет | `vks_common.jobs`, вместе с первой периодической задачей ([background-jobs.md](background-jobs.md)) |
| Повтор `TemporaryFailure` блокирует всю выборку, а не только партицию (`consumer.pause()` не используется) | С первым потребителем в сервисе (analytics, EMO-86) |
| Очистка опубликованных записей outbox через 7 дней | Фоновая задача, [background-jobs.md](background-jobs.md) |
| В тестах брокер – `confluentinc/cp-kafka:7.6.0` (его запускает `KafkaContainer` testcontainers), в dev – `apache/kafka:4.1.0`; протокол один | – |
| Метрики `outbox_pending`, `consumer_lag_messages` | С мониторингом (спринт 6) |
