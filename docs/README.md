# Документация Системы «ReactiVKS»

Платформа видеоконференцсвязи со встроенным распознаванием эмоций участников
(«Приложение для распознавания эмоций собеседников на встречах с использованием видеоконференцсвязи»).

| Параметр | Значение |
|---|---|
| Версия | 0.2 (этап проектирования) |
| Дата | 29.09.2026 |
| Исходные документы | Документ-концепция (27.09.2026), Устав проекта (27.09.2026) |

## Структура и ответственность

Документы разделены по уровню, а не по людям: системный уровень и контракты читают все участники.

| Раздел | Содержание | Ответственный | Изменения согласует |
|---|---|---|---|
| [architecture/](architecture/) | Архитектура Системы целиком | Архитектор – Халецкий Д. Е. | Руководитель проекта (для влияющих на сроки и состав функций) |
| [adr/](adr/) | Архитектурные решения | Автор решения (любой участник) | Архитектор |
| [api/](api/) | Контракты между частями Системы | Сторона, предоставляющая контракт | Сторона-потребитель + архитектор |
| [backend/](backend/) | Устройство бэкенд-сервисов | Халецкий Д. Е. | – |
| [ml/](ml/) | ML-сервис и обучение модели | ML Engineer – Лесовой А. Е.; интеграция с шиной и LiveKit – архитектор | Архитектор (для интеграции) |
| [frontend/](frontend/) | Клиентская часть | Frontend Developer – Зимирев К. М. | Архитектор (для контрактов и ADR) |
| [plan/](plan/) | План по 7 спринтам, задачи и оценки | Руководитель проекта – Лесовой А. Е. | Команда на планировании спринта |

## Порядок чтения

### Архитектура ([architecture/](architecture/))

| № | Документ | Содержание |
|---|---|---|
| 1 | [01-overview.md](architecture/01-overview.md) | Цели, ограничения, архитектурные драйверы, контекст, трассировка НФТ |
| 2 | [02-containers.md](architecture/02-containers.md) | Состав сервисов, ответственность, взаимодействие, отказы |
| 3 | [03-scenarios.md](architecture/03-scenarios.md) | Прецеденты UC-1…UC-7 – диаграммы последовательности |
| 4 | [04-data-model.md](architecture/04-data-model.md) | Логическая модель данных, Kafka и Redis, хранение и удаление |
| 5 | [05-security-privacy.md](architecture/05-security-privacy.md) | Безопасность, авторизация, 152-ФЗ |
| 6 | [06-deployment.md](architecture/06-deployment.md) | Развертывание, сеть, конфигурация, бэкапы, мониторинг |
| 7 | [07-development.md](architecture/07-development.md) | Монорепозиторий, инструменты, стандарты, CI, тестирование |
| 8 | [08-implementation-plan.md](architecture/08-implementation-plan.md) | Спринты и архитектурные результаты, открытые вопросы |
| 9 | [09-uml.md](architecture/09-uml.md) | UML: прецеденты, компоненты, классы, состояния; сводка всех диаграмм |

### Контракты ([api/](api/))

| Документ | Содержание |
|---|---|
| [rest-api.md](api/rest-api.md) | REST API всех сервисов: эндпоинты, схемы, коды ошибок, примеры |
| [websocket-protocol.md](api/websocket-protocol.md) | Протокол WebSocket панели эмоций |
| [events.md](api/events.md) | События Kafka: топики, ключи, группы потребителей, форматы |
| [livekit-integration.md](api/livekit-integration.md) | Токены, атрибуты, вебхуки, конфигурация LiveKit |

### План разработки ([plan/](plan/README.md))

[README.md](plan/README.md) – 7 спринтов, вехи, трудоемкость · задачи по спринтам: [1](plan/sprint-1.md) · [2](plan/sprint-2.md) · [3](plan/sprint-3.md) · [4](plan/sprint-4.md) · [5](plan/sprint-5.md) · [6](plan/sprint-6.md) · [7](plan/sprint-7.md)

### Бэкенд ([backend/](backend/README.md))

[conventions.md](backend/conventions.md) · [database.md](backend/database.md) · [background-jobs.md](backend/background-jobs.md) ·
[auth-service](backend/auth-service.md) · [meeting-service](backend/meeting-service.md) ·
[realtime-service](backend/realtime-service.md) · [analytics-service](backend/analytics-service.md)

### ML ([ml/](ml/))

[emotion-ml-service.md](ml/emotion-ml-service.md) · [ml-model.md](ml/ml-model.md)

### Frontend ([frontend/](frontend/README.md))

[README.md](frontend/README.md) – исходное описание от архитектора; раздел развивает разработчик frontend.

### Архитектурные решения ([adr/](adr/))

| № | Решение | Статус |
|---|---|---|
| [ADR-001](adr/ADR-001-microservices.md) | Микросервисная архитектура из пяти сервисов | Принято |
| [ADR-002](adr/ADR-002-livekit.md) | LiveKit как медиасервер и сигнализация WebRTC | Принято |
| [ADR-003](adr/ADR-003-event-bus-redis-streams.md) | Redis Streams как шина событий | Заменено ADR-012 |
| [ADR-004](adr/ADR-004-postgres-schema-per-service.md) | Один PostgreSQL, схема на сервис | Принято |
| [ADR-005](adr/ADR-005-gateway-and-jwt.md) | Nginx как точка входа, JWT RS256 с проверкой в сервисах | Принято |
| [ADR-006](adr/ADR-006-frontend-stack.md) | React + TypeScript + Vite | Принято |
| [ADR-007](adr/ADR-007-ml-as-livekit-agent.md) | ML-модуль как агент LiveKit Agents | Принято |
| [ADR-008](adr/ADR-008-chat-via-livekit-data.md) | Чат через LiveKit без сохранения | Принято |
| [ADR-009](adr/ADR-009-emotion-data-retention.md) | Хранение только посекундных агрегатов | Принято |
| [ADR-010](adr/ADR-010-monorepo.md) | Монорепозиторий | Принято |
| [ADR-011](adr/ADR-011-transactional-outbox.md) | Transactional outbox для публикации событий | Принято |
| [ADR-012](adr/ADR-012-kafka.md) | Apache Kafka (KRaft) как брокер событий | Принято |

Новый ADR – по [шаблону](adr/template.md), следующий свободный номер.

## Соглашения

- Диаграммы – Mermaid (отображаются в GitHub/GitLab).
- Идентификаторы – на английском, описания – на русском.
- Термины – по глоссарию документа-концепции (раздел 10).
- При изменении решения обновляется документ; архитектурно значимое изменение – новый ADR со ссылкой на заменяемый.
