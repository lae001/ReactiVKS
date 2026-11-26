# Спринт 6. Backend: реализация и проверка

Дата: 25.11.2026 (Asia/Krasnoyarsk). Ветка: `codex/backend-sprint6`. Исходная `main`: `c84321a`.
Числовые результаты: [sprint6-backend-evidence.json](sprint6-backend-evidence.json).

## Задачи

| Задача | Реализация и результат |
|---|---|
| EMO-100 | CSV с BOM, посекундными рядами и защитой от формул; PDF WeasyPrint с графиком matplotlib; создание/удаление ручных отметок. Владелец проверяется в SQL, проверяются участник и интервал встречи. |
| EMO-101 | `/admin/meetings` с курсором, фильтром и online; `/admin/health` с реальными проверками сервисов, PostgreSQL, Kafka, Redis, LiveKit и heartbeat ML. Восстановление пароля за флагом: SHA-256 одноразового случайного токена, 30 минут, лимит запросов, отзыв refresh-сессий, SMTP STARTTLS или локальные `.eml`. |
| EMO-102 | Сверка комнат каждые 60 с; подтверждение отсутствия 2 минуты хранится в БД. Отмена просроченных scheduled, очистка deleted через 30 дней, согласий через 3 года, webhook/outbox через 7 дней, токенов и аналитики через заданный срок (по умолчанию 365 дней). PostgreSQL advisory locks защищают периодические задачи и порядок outbox. DLQ: просмотр по умолчанию, повтор только с `--execute`. |
| EMO-103 | Профиль monitoring: Prometheus, Grafana, kafka-exporter; `/metrics` во всех backend-сервисах, HTTP и job-метрики. 5×10 запущено; ограничение ML на текущем стенде описано ниже. |
| EMO-104 | 496 backend-тестов прошли; покрытие с ветвлениями 84,50% при пороге 60%. Ruff, форматирование, mypy strict и 13 контрактов импортов прошли. Исправлен дефект ML→Kafka: агенту не хватало extra `aiokafka[lz4]`. |
| EMO-105 | Техническая демонстрация подготовлена и выполнена автоматическим браузерным прогоном. Командные совещания и ежедневные статусы этим протоколом не подтверждаются. |

## Полный стенд

Linux; Python 3.12 / uv; Node 22.18; PostgreSQL 16, Redis 7, Kafka 4.1, LiveKit 1.13.7 в Docker.
Четыре Python-сервиса запущены на хосте: auth :8001, meeting :8002, analytics :8003, realtime :8080.
Frontend Vite :5173 в `VITE_API_MODE=http`, ML-агент :8081 с настоящими ONNX/MediaPipe моделями из `ml-v1.2.0`.
Все SHA-256 моделей проверены штатным скриптом. Модели/тестовое видео/пароли не добавлены в git.
Monitoring: Prometheus :9090, Grafana :3000, kafka-exporter :9308, LiveKit :6789; все шесть целей `up=1`.
`scripts/dev.sh` для этого прогона не использовался: он запускает подменный `dev-api`.

Браузер — Chromium с фиксированным видео лица из публичного образца OpenCV `lena.jpg`, камера и микрофон виртуальные.
Ни REST, ни WebSocket, ни Kafka, ни ML-вывод не подменялись.

## Сквозная проверка

| Проверка | Результат |
|---|---|
| Вход через UI, создание встречи, организатор и гость | Настоящие auth/meeting/LiveKit, два connected клиента |
| Видео → ML → Kafka → realtime → WebSocket → панель | Получены `emotion.update` с 7 вероятностями, панель показывает анализ |
| Ручная отметка через UI | 201; отметка видна в готовом отчете |
| Отзыв согласия | 200/202; `participant.status no_consent`; гость без согласия не анализируется |
| Отказ ML | SIGKILL конкретного ML job-процесса тестовой комнаты; панель перешла в «Анализ недоступен». У гостя video 640×480 продолжило декодирование: 124 → 130 кадров, 5 новых представленных кадров |
| Завершение и отчет | `ready`, есть реальные интервалы анализа и ручная отметка |
| Скачивание CSV/PDF через UI | Оба файла скачаны. Проверены BOM CSV, сигнатура PDF, A4 и извлечение русского текста |
| Администрирование через UI | Список встреч и health — 200; рабочие компоненты показаны `ok` |
| Доступ организатора к admin и чужой аналитике | 403/404 подтверждены интеграционными тестами |
| Восстановление пароля | Интеграционные тесты: выключенный флаг, неизвестный email, 429, одноразовый токен, новый пароль и отзыв refresh-сессий |
| DLQ | На настоящем Kafka режим просмотра пустой `meeting.events.dlq` вернул 0; отправка/чтение DLQ и outbox проверены интеграционными тестами |

Два финальных браузерных теста прошли за 23,0 с. Снимки и подробные результаты локального прогона — `/tmp/reactivks-s6/`.

## Нагрузка 5×10 и ограничения

Генератор `ml/emotion_service/scripts/backend_load_test.py` создает встречи и участников через REST,
публикует видео в LiveKit, читает реальные ML-события Kafka и подписывается на WebSocket организатора.
Генератор не подписывается на видео остальных участников: декодирование 450 потоков на той же машине
не входит в этот замер backend/ML. `lk` CLI на стенде отсутствует, использован существующий LiveKit Python SDK.

Первый прогон исключен: во время него LiveKit был перезапущен для включения метрик. Ниже только повторный замер.

| Показатель | Значение |
|---|---|
| Подключено | 5 встреч × 10 участников, 50 публикаций |
| Измеряемое окно после подключения всех | 60 с |
| CPU всей машины: средний / пик | 98,14% / 99,4% |
| Участников с ML-отсчетами в окне | 10 из 50; данные есть только у первой встречи |
| ML-отсчетов analyzing | 990 |
| Частота по анализируемым участникам: min / медиана / max | 1,57 / 1,66 / 1,72 кадра/с |
| WebSocket: пакетов / задержка p50 / p95 | 69 / 1,46 с / 2,06 с |
| Отчеты | 5 ready, ожидание после завершения 8,33 с; четыре отчета без ML-рядов |

Задержка рассчитана как время получения WebSocket-пакета минус `ts` ML-отсчета на одной машине;
это не замер времени от экспозиции камеры до отрисовки экрана.

**Норматив 5×10 для ML на этой машине не подтвержден:** не все участники обрабатываются,
частота ниже 2 кадр/с, p95 выше 2 с. В журнале агент помечал воркер занятым при превышении порога CPU 0,95;
наблюдались задержки WebRTC, а при завершении задания — предупреждение MediaPipe executor.
Видео, ML, генератор и инфраструктура работали на одном компьютере. Нужен повтор на рекомендуемом
сервере с вынесенными генераторами и достаточным числом ML-воркеров; это ограничение производительности,
а не подтвержденная емкость production. Отчет `ready` с пустыми рядами не считается успешным анализом.

Оставшиеся прежние TODO `EMO-68` (Idempotency-Key) и `EMO-69` (лимит публичного join) этой работой не закрываются.
TURN, реальные браузерные устройства, качество модели на людях и длительная нагрузка этим прогоном не подтверждаются.

## Повторение

```bash
# Инфраструктура и monitoring (Linux)
docker compose -f deploy/docker-compose.dev.yml -f deploy/docker-compose.monitoring.yml --profile monitoring up -d
cd backend
uv sync
make migrate jwt-key
# В отдельных терминалах, из backend/:
make run-auth AUTH_ENV_FILE=services/auth_service/.env.example
make run-meeting MEETING_ENV_FILE=services/meeting_service/.env.example
make run-analytics ANALYTICS_ENV_FILE=services/analytics_service/.env.example
make run-realtime REALTIME_ENV_FILE=services/realtime_service/.env.example
# Проверки backend
make lint type imports
make cov
```

Frontend: Node ≥22.18, `cd frontend && pnpm install --frozen-lockfile && VITE_API_MODE=http pnpm dev`.
ML: из `ml/models` выполнить `sh fetch_models.sh`; из `ml/emotion_service` — `uv sync --extra agent`,
затем `ML_KAFKA_BOOTSTRAP=localhost:9092 LIVEKIT_URL=ws://localhost:7880 LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=<секрет из LiveKit> uv run emotion-agent start` (переменные в одной строке).

```bash
# После запуска полного стенда; E2E_VIDEO — абсолютный путь к Y4M с лицом.
cd frontend
E2E_VIDEO=/path/face.y4m pnpm exec playwright test -c playwright.backend-sprint6.config.ts
# Дополнительно E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD — тестовый администратор.
# E2E_AGENT_LOG — путь к JSON-журналу ЛОКАЛЬНОГО агента: включает SIGKILL только задания тестовой комнаты.
cd ../ml/emotion_service
uv run python scripts/backend_load_test.py --image /path/face.jpg --output /tmp/load.json --seconds 60
# Просмотр DLQ, затем осознанный повтор с сохранением event_id:
cd ../../backend
uv run python scripts/dlq_replay.py meeting.events --limit 100
# Добавление --execute выполняет публикацию, исходную DLQ не удаляет.
```
