# 3. Ключевые сценарии

Сценарии соответствуют прецедентам документа-концепции (раздел 7). Пути REST приведены сокращенно,
полное описание – в [api/rest-api.md](../api/rest-api.md).

Обозначение «→ Kafka (outbox)» означает: событие записывается в таблицу `outbox` в той же транзакции, что и данные,
и публикуется в Kafka фоновым релеем в течение ≤ 1 с ([ADR-011](../adr/ADR-011-transactional-outbox.md)).

## 3.1 UC-1. Регистрация, вход, обновление токена

```mermaid
sequenceDiagram
    autonumber
    actor U as Организатор
    participant FE as frontend
    participant A as auth-service
    participant DB as PostgreSQL (auth)

    U->>FE: e-mail, пароль, имя
    FE->>A: POST /api/v1/auth/register
    A->>DB: INSERT users (password_hash = Argon2id)
    A-->>FE: 201 {user}
    U->>FE: вход
    FE->>A: POST /api/v1/auth/login
    A->>DB: проверка хеша, status = active
    A->>DB: INSERT refresh_tokens (hash)
    A-->>FE: 200 {access_token (JWT RS256, 15 мин)} + Set-Cookie refresh (httpOnly, 30 дн)
    Note over FE: access_token хранится только в памяти
    FE->>A: POST /api/v1/auth/refresh (cookie)
    A->>DB: проверка и ротация refresh-токена
    A-->>FE: новый access_token + новый cookie
```

Повторное предъявление уже использованного refresh-токена считается компрометацией: отзываются все
refresh-токены пользователя.

## 3.2 UC-2. Создание встречи

```mermaid
sequenceDiagram
    autonumber
    actor O as Организатор
    participant FE as frontend
    participant M as meeting-service
    participant DB as PostgreSQL (meeting)
    participant K as Kafka

    O->>FE: название, время (опц.), анализ вкл/выкл
    FE->>M: POST /api/v1/meetings (Bearer JWT)
    M->>DB: INSERT meetings (status = scheduled) + INSERT outbox (meeting.created)
    M-->>FE: 201 {id, invite_url = https://домен/j/{invite_code}}
    M-)K: meeting.events: meeting.created (outbox-релей)
    O->>O: отправляет ссылку участникам
```

Создание и отправка приглашения укладываются в 3 действия: «Новая встреча» → «Создать» → «Копировать ссылку».

## 3.3 UC-4 (начало). Организатор запускает встречу

```mermaid
sequenceDiagram
    autonumber
    actor O as Организатор
    participant FE as frontend
    participant M as meeting-service
    participant LK as LiveKit
    participant ML as emotion-ml-service
    participant K as Kafka
    participant RT as realtime-service

    O->>FE: «Начать встречу», проверка камеры/микрофона
    FE->>M: POST /api/v1/meetings/{id}/join {consent}
    alt встреча в статусе scheduled
        M->>LK: CreateRoom(name = meeting_id, empty_timeout)
        M-)K: meeting.events: meeting.started (outbox)
        opt analysis_enabled
            M->>LK: CreateDispatch(agent = emotion-agent, metadata = {fps})
            LK->>ML: задание на комнату
            ML->>LK: вход как служебный участник (vks.kind = agent)
            ML-)K: ml.status {state: active}
        end
    end
    M->>M: participant (role = organizer), consent в журнал
    M-->>FE: {participant_id, livekit_url, livekit_token}
    FE->>LK: connect(livekit_token), публикация камеры и микрофона
    FE->>RT: WSS /ws + subscribe {meeting_id}
    RT->>M: GET /internal/meetings/{id}/access?user_id (кеш 60 с)
    RT-->>FE: subscribed + текущий snapshot
```

## 3.4 UC-3. Участник присоединяется по ссылке

```mermaid
sequenceDiagram
    autonumber
    actor P as Участник
    participant FE as frontend
    participant M as meeting-service
    participant LK as LiveKit
    participant ML as emotion-ml-service
    participant K as Kafka

    P->>FE: переход по /j/{invite_code}
    FE->>M: GET /api/v1/join/{invite_code}
    M-->>FE: {title, organizer_name, status, analysis_enabled, consent_notice {version, text}}
    P->>FE: проверка устройств, имя, решение о согласии
    FE->>M: POST /api/v1/join/{invite_code} {display_name, consent: granted | denied}
    alt встреча не начата
        M-->>FE: 409 meeting_not_started (FE ждет и повторяет запрос)
    else встреча активна
        M->>M: participant (role = guest), consent в журнал, participant_token
        M-)K: meeting.events: participant.registered, consent.changed (outbox)
        M-->>FE: {participant_id, participant_token, livekit_url, livekit_token}
    end
    Note over M: livekit_token содержит атрибуты vks.role, vks.consent<br/>и запрет canUpdateOwnMetadata
    FE->>LK: connect, публикация дорожек
    LK->>M: вебхук participant_joined
    M-)K: meeting.events: participant.joined (outbox)
    LK->>ML: TrackPublished (video)
    alt vks.consent = granted
        ML->>LK: подписка на видеодорожку
    else denied
        ML->>ML: дорожка игнорируется
        ML-)K: emotion.samples {state: no_consent}
    end
```

Альтернативный сценарий 4а (NAT, межсетевой экран): клиент LiveKit перебирает ICE-кандидатов
(UDP 7882 → TCP 7881 → TURN/UDP 3478 → TURN/TLS 443 через `turn.<домен>`); логика приложения не меняется.

## 3.5 UC-4. Анализ эмоций и панель организатора

```mermaid
sequenceDiagram
    autonumber
    participant LK as LiveKit
    participant ML as emotion-ml-service
    participant K as Kafka
    participant RT as realtime-service
    participant AN as analytics-service
    participant FE as frontend организатора
    participant DB as PostgreSQL (analytics)

    loop каждые 1/fps с (по умолчанию 3 кадра/с)
        LK->>ML: видеокадры согласившихся участников
        ML->>ML: последний кадр → детекция лица → классификация (пакет) → EMA
        ML-)K: emotion.samples (key = meeting_id)
    end
    par доставка в реальном времени
        K->>RT: consume (группа realtime-<instance>)
        RT->>FE: emotion.update (пакет за ≤ 250 мс)
        FE->>FE: индикатор на плитке + график последних 5 мин
    and сохранение
        K->>AN: consume (группа analytics)
        AN->>AN: агрегация в посекундные корзины
        AN->>DB: пакетный INSERT emotion_series (раз в 5 с)
        AN->>K: commit offset (до первого несохраненного отсчета)
    end
```

Альтернативный сценарий 6а: лицо не найдено → отсчет с `state = no_face`, на панели – «лицо не обнаружено».

## 3.6 UC-4. Отзыв согласия во время встречи

```mermaid
sequenceDiagram
    autonumber
    actor P as Участник
    participant FE as frontend участника
    participant M as meeting-service
    participant LK as LiveKit
    participant ML as emotion-ml-service
    participant K as Kafka
    participant RT as realtime-service

    P->>FE: «Отключить анализ моих эмоций»
    FE->>M: PUT /api/v1/participants/me/consent {decision: revoked} (participant_token)
    M->>M: журнал согласий + outbox (consent.changed) в одной транзакции
    M->>LK: UpdateParticipant(attributes: vks.consent = revoked)
    M-->>FE: 200 (или 202, если LiveKit недоступен – повтор из очереди)
    LK->>ML: ParticipantAttributesChanged
    ML->>LK: отписка от видеодорожки, сброс состояния сглаживания
    M-)K: meeting.events: consent.changed
    K->>RT: consent.changed
    RT->>FE: participant.status {state: no_consent} (организатору)
```

Повторное согласие (`granted`) выполняется тем же запросом. Отзыв согласия не удаляет уже накопленные данные
автоматически; удаление данных встречи – право организатора (UC-5), а участник может запросить его у организатора
или администратора (см. [05-security-privacy.md](05-security-privacy.md)).

## 3.7 UC-4. Недоступность ML-сервиса (альтернативный сценарий 5а)

```mermaid
sequenceDiagram
    autonumber
    participant ML as emotion-ml-service
    participant K as Kafka
    participant RT as realtime-service
    participant FE as frontend организатора
    participant LK as LiveKit

    ML-)K: ml.status {active} (heartbeat каждые 5 с)
    Note over ML: сбой процесса
    RT->>RT: нет heartbeat по встрече > 10 с
    RT->>FE: analysis.status {state: unavailable}
    FE->>FE: баннер «Анализ временно недоступен», видео работает
    Note over ML,LK: Docker перезапускает контейнер,<br/>LiveKit повторно выдает задание по комнате
    ML-)K: ml.status {active}
    K->>RT: ml.status
    RT->>FE: analysis.status {state: active}
```

Тот же сценарий срабатывает при недоступности Kafka: heartbeat не доходит до realtime-service, организатор видит
«анализ недоступен», видеосвязь не затрагивается.

## 3.8 UC-4 (завершение). Окончание встречи и формирование отчета

```mermaid
sequenceDiagram
    autonumber
    actor O as Организатор
    participant FE as frontend
    participant M as meeting-service
    participant LK as LiveKit
    participant K as Kafka
    participant AN as analytics-service
    participant RT as realtime-service

    O->>FE: «Завершить встречу»
    FE->>M: POST /api/v1/meetings/{id}/end
    M->>LK: DeleteRoom (все отключаются, агент завершает задание)
    M->>M: status = ended, ended_at + outbox (meeting.ended)
    M-->>FE: 200
    M-)K: meeting.events: meeting.ended
    K->>AN: meeting.ended
    AN->>AN: ожидание 5 с (дочитывание emotion.samples)
    AN->>AN: сброс корзин, расчет сводки и ключевых моментов
    AN-)K: report.events: report.ready (outbox)
    K->>RT: report.ready
    RT->>FE: report.ready {meeting_id}
    FE->>FE: переход на страницу отчета
```

Встреча завершается и без организатора: если комната пуста дольше `empty_timeout` (5 мин), LiveKit закрывает ее
и присылает вебхук `room_finished`, после чего meeting-service выполняет те же шаги начиная с `status = ended`.

`meeting.ended` и отсчеты идут в разных топиках, поэтому analytics-service ждет 5 с и дополнительно проверяет, что
отставание группы `analytics` по `emotion.samples` для партиции этой встречи меньше 1 с; иначе ждет еще (до 60 с).

## 3.9 UC-5, UC-6. Просмотр отчета и экспорт

```mermaid
sequenceDiagram
    autonumber
    actor O as Организатор
    participant FE as frontend
    participant AN as analytics-service

    O->>FE: История встреч → встреча
    FE->>AN: GET /api/v1/reports/{meeting_id}
    AN->>AN: проверка owner_id из проекции = sub JWT
    AN-->>FE: {summary, participants, key_moments, markers}
    FE->>AN: GET /api/v1/reports/{meeting_id}/series?resolution=5s
    AN-->>FE: ряды для графиков
    O->>FE: «Экспорт PDF» / «Экспорт CSV»
    FE->>AN: GET /api/v1/reports/{meeting_id}/export.pdf | export.csv
    AN-->>FE: файл (PDF строится на лету WeasyPrint, CSV – потоково)
```

## 3.10 UC-7. Администрирование

```mermaid
sequenceDiagram
    autonumber
    actor A as Администратор
    participant FE as frontend (/admin)
    participant AU as auth-service
    participant K as Kafka
    participant M as meeting-service

    A->>FE: раздел «Пользователи»
    FE->>AU: GET /api/v1/admin/users (role = admin)
    A->>FE: «Заблокировать»
    FE->>AU: PATCH /api/v1/admin/users/{id} {status: blocked}
    AU->>AU: отзыв всех refresh-токенов + outbox (user.blocked)
    AU-)K: user.events: user.blocked
    K->>M: user.blocked → blocked_users
    A->>FE: раздел «Состояние»
    FE->>M: GET /api/v1/admin/meetings?status=active
    FE->>M: GET /api/v1/admin/health
    Note over M: meeting-service опрашивает /ready всех сервисов,<br/>LiveKit, Kafka и возраст heartbeat ML-сервиса
```

Журналы ошибок просматриваются в Grafana/Loki (профиль мониторинга) или через `docker compose logs`
– см. [06-deployment.md](06-deployment.md).
