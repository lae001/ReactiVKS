# 9. UML-представления

Сводка диаграмм, которые концепция (п. 8.2) требует для проектирования: прецедентов, компонентов,
последовательности, развертывания; дополнительно – классы предметной области и состояния.
Диаграммы выполнены в Mermaid; нотация UML передана средствами Mermaid (актеры – овалы, прецеденты – скругленные
блоки, интерфейсы компонентов – кружки «◯»).

| Вид UML | Где |
|---|---|
| Прецедентов | [9.1](#91-диаграмма-прецедентов) |
| Компонентов | [9.2](#92-диаграмма-компонентов) |
| Классов (предметная область) | [9.3](#93-диаграмма-классов-предметной-области) |
| Состояний | [9.4](#94-диаграммы-состояний), жизненный цикл встречи – [04-data-model.md](04-data-model.md#жизненный-цикл-встречи) |
| Последовательности | [03-scenarios.md](03-scenarios.md) (UC-1…UC-7), [backend/conventions.md](../backend/conventions.md#6-публикация-событий-transactional-outbox) (outbox) |
| Развертывания | [06-deployment.md](06-deployment.md#61-диаграмма-развертывания) |

## 9.1 Диаграмма прецедентов

```mermaid
flowchart LR
    ORG(["👤 Организатор"])
    GUEST(["👤 Участник"])
    ADMIN(["👤 Администратор"])
    ML(["⚙ ML-сервис<br/>(системный актер)"])

    subgraph SYS["Система ReactiVKS"]
        UC1("UC-1 Зарегистрироваться / войти")
        UC2("UC-2 Создать встречу<br/>и пригласить участников")
        UC3("UC-3 Присоединиться к встрече")
        UC3a("Дать / отозвать согласие<br/>на анализ")
        UC3b("Проверить камеру<br/>и микрофон")
        UC4("UC-4 Провести встречу<br/>с анализом эмоций")
        UC4a("Наблюдать панель эмоций")
        UC4b("Модерировать участников")
        UC4c("Отметить момент")
        UC4d("Общаться в чате")
        UC4e("Распознать эмоции участника")
        UC5("UC-5 Просмотреть отчет")
        UC6("UC-6 Экспортировать результаты")
        UC8("Просмотреть историю встреч")
        UC9("Настроить анализ по умолчанию")
        UC7("UC-7 Управлять пользователями")
        UC7a("Просмотреть состояние сервисов")
    end

    ORG --- UC1 & UC2 & UC4 & UC5 & UC8 & UC9
    GUEST --- UC3 & UC4
    ADMIN --- UC1 & UC7 & UC7a
    ML --- UC4e

    UC3 -. "«include»" .-> UC3b
    UC3 -. "«include»" .-> UC3a
    UC4 -. "«include»" .-> UC4d
    UC4a -. "«extend»" .-> UC4
    UC4b -. "«extend»" .-> UC4
    UC4c -. "«extend»" .-> UC4
    UC4 -. "«include»<br/>если анализ включен" .-> UC4e
    UC6 -. "«extend»" .-> UC5
```

Организатор при входе во встречу с анализом также проходит «Дать согласие» (как любой участник, см. открытый
вопрос 4 в [08-implementation-plan.md](08-implementation-plan.md#84-открытые-вопросы)).

## 9.2 Диаграмма компонентов

Предоставляемые интерфейсы обозначены «◯ имя», требуемые – стрелкой к интерфейсу. Библиотеки `vks_common` (шасси)
и `vks_contracts` (контракты событий) входят в каждый Python-сервис; события сервисов с БД идут в Kafka только
через outbox – таблицу своей схемы и фоновый `OutboxRelay` ([ADR-011](../adr/ADR-011-transactional-outbox.md)).

```mermaid
flowchart TB
    subgraph FE["«component» frontend"]
        FE_UI["Интерфейс SPA"]
    end

    subgraph AUTH["«component» auth-service"]
        A_API["◯ Auth REST API"]
        A_JWKS["◯ JWKS"]
    end

    subgraph MEET["«component» meeting-service"]
        M_API["◯ Meetings REST API"]
        M_INT["◯ Internal API"]
        M_WH["◯ LiveKit Webhook"]
        M_GW["«interface» LiveKitGateway"]
        M_OB["outbox + OutboxRelay"]
    end

    subgraph RT["«component» realtime-service"]
        RT_WS["◯ WebSocket vks.v1"]
    end

    subgraph AN["«component» analytics-service"]
        AN_API["◯ Reports REST API"]
    end

    subgraph ML["«component» emotion-ml-service"]
        ML_AG["Agent worker"]
        ML_CL["«interface» EmotionClassifier"]
        ML_FD["«interface» FaceDetector"]
    end

    subgraph LIBS["«library» общие пакеты backend/libs"]
        L_COM["vks_common: конфиг, ошибки RFC 9457,<br/>JWT/JWKS, БД, outbox, Kafka"]
        L_CON["vks_contracts: конверт и payload событий"]
    end

    subgraph LK["«component» LiveKit Server"]
        LK_SIG["◯ Signaling / WebRTC"]
        LK_API["◯ Server API"]
        LK_AG["◯ Agents protocol"]
    end

    subgraph BUS["«component» Apache Kafka"]
        S_EM["◯ топики emotion.samples / ml.status"]
        S_MT["◯ топики meeting.events / report.events / user.events"]
    end

    DB[("«database» PostgreSQL<br/>auth | meeting | analytics")]
    ONNX[/"«artifact» emotion-*.onnx<br/>yunet.onnx"/]

    FE_UI --> A_API & M_API & AN_API & RT_WS & LK_SIG
    M_GW --> LK_API
    LK -. вебхуки .-> M_WH
    ML_AG --> LK_AG
    ML_AG --> S_EM
    ML_CL & ML_FD --- ONNX
    M_OB --> S_MT
    AUTH --> S_MT
    AN --> S_MT
    RT --> S_EM & S_MT
    AN --> S_EM
    RT --> M_INT
    AN --> M_INT
    MEET & AN & RT --> A_JWKS
    AUTH & MEET & AN --> DB
    AUTH & MEET & RT & AN -. «use» .-> LIBS
    ML -. «use» .-> L_CON
```

## 9.3 Диаграмма классов предметной области

Доменные сущности сервисов (слой `domain/`); сервисы не разделяют классы – связи между контекстами идут через
идентификаторы и события. Сущности неизменяемы: переход состояния возвращает новый объект. Для auth и meeting
диаграмма повторяет реализованный код; операции следующих задач помечены «план» в таблице под диаграммой.

```mermaid
classDiagram
    direction LR

    namespace auth {
        class User {
            <<entity>>
            +UserId id
            +str email
            +str display_name
            +Role role
            +UserStatus status
            +ensure_can_sign_in()
            +renamed(display_name) User
        }
        class RefreshToken {
            <<entity>>
            +RefreshTokenId id
            +SessionFamilyId family_id
            +bytes token_hash
            +datetime expires_at
            +datetime revoked_at
            +RefreshTokenId replaced_by
            +is_expired(now) bool
            +rotated(successor, now) RefreshToken
        }
        class TokenSigner {
            <<interface>>
            +sign(claims) str
            +published_keys() list
        }
        class PasswordHasher {
            <<interface>>
            +hash(password) str
            +verify(password, hash) bool
        }
    }

    namespace meeting {
        class Meeting {
            <<entity>>
            +MeetingId id
            +UserId owner_id
            +str owner_name
            +str title
            +str invite_code
            +MeetingStatus status
            +bool analysis_enabled
            +int analysis_fps
            +schedule(organizer, title, …) Meeting
            +started(now) Meeting
            +ensure_open_for_guests()
            +ended(now, reason) Meeting
        }
        class AnalysisDefaults {
            <<value object>>
            +bool enabled
            +int fps
        }
        class Participant {
            <<entity>>
            +ParticipantId id
            +MeetingId meeting_id
            +UserId user_id
            +str display_name
            +ParticipantRole role
            +ConsentState consent_state
            +bool is_removed
            +livekit_identity str
            +with_consent(state) Participant
        }
        class ConsentNotice {
            <<value object>>
            +str version
            +str text_md
        }
        class ConsentRecord {
            <<immutable>>
            +ConsentState decision
            +str notice_version
            +str display_name
            +str meeting_title
            +datetime decided_at
        }
        class LiveKitGateway {
            <<interface>>
            +public_url str
            +ensure_room(room)
            +delete_room(room)
            +issue_token(RoomAccess) str
        }
        class RoomAccess {
            <<value object>>
            +str room
            +str identity
            +str name
            +Mapping attributes
        }
    }

    namespace analytics {
        class SecondBucket {
            +UUID meeting_id
            +UUID participant_id
            +datetime ts
            +int samples
            +int face_samples
            +add(sample)
            +mean() EmotionVector
        }
        class EmotionVector {
            <<value object>>
            +float[7] p
            +dominant() EmotionLabel
            +valence() float
            +negative_share() float
        }
        class Report {
            +UUID meeting_id
            +ReportStatus status
            +Summary summary
            +build(series, projection)
        }
        class Marker {
            +UUID id
            +datetime ts
            +MarkerKind kind
            +str label
        }
        class KeyMomentDetector {
            +float threshold
            +detect(series) Marker[]
        }
    }

    User "1" --> "*" RefreshToken
    Meeting ..> AnalysisDefaults : параметры по умолчанию
    Meeting "1" *-- "*" Participant
    Participant "1" --> "*" ConsentRecord
    ConsentRecord ..> ConsentNotice : версия текста
    LiveKitGateway ..> RoomAccess
    RoomAccess ..> Participant : room_access(meeting, participant)
    SecondBucket ..> EmotionVector
    Report "1" o-- "*" Marker
    KeyMomentDetector ..> Marker : создает
```

| Класс | Реализовано | План |
|---|---|---|
| `User`, `RefreshToken`, `TokenSigner`, `PasswordHasher` | Вход, ротация refresh-токенов с отзывом семьи, профиль, смена пароля (EMO-33, EMO-67) | `block()`, `unblock()` – администрирование (EMO-67) |
| `Meeting` | Создание, вход организатора (`scheduled → active`), завершение, правила входа гостя (EMO-53) | `cancelled(now)` – `DELETE` (EMO-68), проверка `meeting_full` по онлайн-участникам (EMO-69) |
| `Participant`, `ConsentRecord`, `ConsentNotice` | Регистрация организатора и гостя, решение о согласии и журнал (EMO-53) | `removed()` – модерация (EMO-70), отзыв согласия (EMO-84) |
| `LiveKitGateway` | `CreateRoom`, `DeleteRoom`, токены с атрибутами `vks.*` (EMO-53) | `UpdateParticipant`, `MutePublishedTrack`, `RemoveParticipant`, `CreateDispatch` (EMO-70, EMO-84) |
| analytics | – | EMO-86, EMO-87 |

## 9.4 Диаграммы состояний

### Встреча

```mermaid
stateDiagram-v2
    [*] --> scheduled: POST /meetings
    scheduled --> active: первый вход организатора (POST /join)
    scheduled --> cancelled: DELETE (EMO-68)
    active --> ended: POST /end или вебхук room_finished (EMO-69)
    scheduled --> scheduled: POST /end – 409 meeting_not_started
    ended --> ended: POST /end – без изменений
    ended --> [*]
    cancelled --> [*]
```

Гость входит только в `active`: в `scheduled` – `409 meeting_not_started` (клиент повторяет), в `ended` и
`cancelled` – `409 meeting_ended` / `meeting_cancelled`.

### Согласие участника

```mermaid
stateDiagram-v2
    [*] --> not_required: анализ во встрече выключен
    [*] --> granted: вход с согласием
    [*] --> denied: вход с отказом
    denied --> granted: дал согласие во время встречи
    granted --> revoked: отозвал
    revoked --> granted: дал повторно
    granted --> [*]: встреча завершена
    denied --> [*]
    revoked --> [*]
    not_required --> [*]
```

### Анализ участника (в ML-сервисе и на панели)

```mermaid
stateDiagram-v2
    [*] --> no_consent
    no_consent --> analyzing: consent = granted и камера включена
    analyzing --> no_face: лицо не найдено
    no_face --> analyzing: лицо найдено
    analyzing --> camera_off: камера выключена
    no_face --> camera_off
    camera_off --> analyzing: камера включена
    analyzing --> no_consent: согласие отозвано
    no_face --> no_consent
    camera_off --> no_consent
    analyzing --> left: участник вышел
    no_face --> left
    camera_off --> left
    no_consent --> left
    left --> [*]
```

### Отчет

```mermaid
stateDiagram-v2
    [*] --> pending: meeting.ended
    pending --> ready: построен
    pending --> pending: ошибка, попытка < 3
    pending --> failed: 3 неудачные попытки
    failed --> pending: ручной перезапуск (админ, CLI)
    ready --> [*]
```
