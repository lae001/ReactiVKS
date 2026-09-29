# База данных: физическая схема

Детализация логической модели из [architecture/04-data-model.md](../architecture/04-data-model.md).
DDL ниже – целевое состояние начальных миграций; проверено на PostgreSQL 16 (применение скриптов, ограничения,
изоляция схем). Источник истины после старта разработки – миграции Alembic в `backend/services/<service>/migrations/`;
при изменении миграций этот документ обновляется.

## Общие правила

| Правило | Значение |
|---|---|
| Идентификаторы | UUIDv7, генерируются в приложении (`uuid6.uuid7()`), кроме журналов (`bigint identity`) |
| Время | `timestamptz`, UTC; `created_at`/`updated_at` на всех изменяемых таблицах (`updated_at` выставляет приложение) |
| Перечисления | `text` + `CHECK` (а не тип `ENUM`: проще миграции) |
| Имена ограничений | `<таблица>_<поле>_ck`, `_uk`, `_idx`, FK – по умолчанию PostgreSQL |
| Связи между схемами | Запрещены: ни FK, ни JOIN, ни `SELECT` из чужой схемы (обеспечено правами) |
| Удаление | Встречи – мягкое (`deleted_at`) с физической очисткой через 30 дней; аналитика – физическое |
| Миграции | Alembic, одна ветка на сервис, `alembic_version` в схеме сервиса (`version_table_schema`); только вперед, без ручных правок |
| Роли | Одна роль на сервис – владелец своей схемы; миграции выполняет та же роль (сервис `migrate` в compose) |

## Инициализация БД

Скрипт `deploy/postgres/init/00-init.sql` выполняется суперпользователем один раз при создании тома:

```sql
-- Выполняется один раз суперпользователем при создании БД (deploy/postgres/init/).
-- Пароли подставляются psql-переменными: psql -v auth_password=... -v meeting_password=... -v analytics_password=...

CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO PUBLIC;   -- только для доступа к типам и функциям расширений

CREATE ROLE auth_svc      LOGIN PASSWORD :'auth_password';
CREATE ROLE meeting_svc   LOGIN PASSWORD :'meeting_password';
CREATE ROLE analytics_svc LOGIN PASSWORD :'analytics_password';

CREATE SCHEMA auth      AUTHORIZATION auth_svc;
CREATE SCHEMA meeting   AUTHORIZATION meeting_svc;
CREATE SCHEMA analytics AUTHORIZATION analytics_svc;

ALTER ROLE auth_svc      SET search_path = auth, public;
ALTER ROLE meeting_svc   SET search_path = meeting, public;
ALTER ROLE analytics_svc SET search_path = analytics, public;
```

## Схема `auth`

```sql
-- Схема auth (владелец auth_svc). Начальная миграция Alembic auth-service.
SET ROLE auth_svc;

CREATE TABLE auth.users (
    id             uuid        PRIMARY KEY,
    email          citext      NOT NULL,
    password_hash  text        NOT NULL,
    display_name   text        NOT NULL,
    role           text        NOT NULL DEFAULT 'organizer',
    status         text        NOT NULL DEFAULT 'active',
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    last_login_at  timestamptz,
    CONSTRAINT users_email_uk          UNIQUE (email),
    CONSTRAINT users_email_ck          CHECK (email ~ '^[^@\s]+@[^@\s]+$' AND char_length(email) <= 254),
    CONSTRAINT users_display_name_ck   CHECK (char_length(display_name) BETWEEN 1 AND 100),
    CONSTRAINT users_role_ck           CHECK (role IN ('organizer', 'admin')),
    CONSTRAINT users_status_ck         CHECK (status IN ('active', 'blocked'))
);

CREATE TABLE auth.refresh_tokens (
    id           uuid        PRIMARY KEY,
    user_id      uuid        NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    family_id    uuid        NOT NULL,
    token_hash   bytea       NOT NULL,
    expires_at   timestamptz NOT NULL,
    revoked_at   timestamptz,
    replaced_by  uuid,
    user_agent   text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT refresh_tokens_hash_uk UNIQUE (token_hash)
);
CREATE INDEX refresh_tokens_user_idx   ON auth.refresh_tokens (user_id);
CREATE INDEX refresh_tokens_family_idx ON auth.refresh_tokens (family_id);
CREATE INDEX refresh_tokens_expires_idx ON auth.refresh_tokens (expires_at);

CREATE TABLE auth.password_reset_tokens (
    id          uuid        PRIMARY KEY,
    user_id     uuid        NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    token_hash  bytea       NOT NULL,
    expires_at  timestamptz NOT NULL,
    used_at     timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT password_reset_tokens_hash_uk UNIQUE (token_hash)
);
CREATE INDEX password_reset_tokens_user_idx ON auth.password_reset_tokens (user_id);

CREATE TABLE auth.outbox (
    id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id      uuid        NOT NULL,
    topic         text        NOT NULL,                        -- топик Kafka
    event_key     text        NOT NULL,                        -- ключ сообщения (meeting_id / user_id)
    event_type    text        NOT NULL,
    envelope      jsonb       NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    published_at  timestamptz,
    attempts      int         NOT NULL DEFAULT 0,
    CONSTRAINT outbox_event_uk UNIQUE (event_id)
);
CREATE INDEX outbox_unpublished_idx ON auth.outbox (id) WHERE published_at IS NULL;

RESET ROLE;
```

## Схема `meeting`

```sql
-- Схема meeting (владелец meeting_svc). Начальная миграция Alembic meeting-service.
SET ROLE meeting_svc;

CREATE TABLE meeting.organizer_settings (
    user_id                   uuid        PRIMARY KEY,           -- sub из JWT, без FK (другая схема)
    analysis_enabled_default  boolean     NOT NULL DEFAULT true,
    analysis_fps_default      smallint    NOT NULL DEFAULT 3,
    updated_at                timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT organizer_settings_fps_ck CHECK (analysis_fps_default BETWEEN 2 AND 5)
);

CREATE TABLE meeting.meetings (
    id                uuid        PRIMARY KEY,                  -- = имя комнаты LiveKit
    owner_id          uuid        NOT NULL,                     -- sub из JWT
    title             text        NOT NULL,
    invite_code       text        NOT NULL,
    status            text        NOT NULL DEFAULT 'scheduled',
    analysis_enabled  boolean     NOT NULL,
    analysis_fps      smallint    NOT NULL,
    scheduled_at      timestamptz,
    started_at        timestamptz,
    ended_at          timestamptz,
    end_reason        text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    deleted_at        timestamptz,
    CONSTRAINT meetings_invite_code_uk UNIQUE (invite_code),
    CONSTRAINT meetings_invite_code_ck CHECK (invite_code ~ '^[a-z2-7]{10}$'),
    CONSTRAINT meetings_title_ck       CHECK (char_length(title) BETWEEN 1 AND 200),
    CONSTRAINT meetings_status_ck      CHECK (status IN ('scheduled', 'active', 'ended', 'cancelled')),
    CONSTRAINT meetings_fps_ck         CHECK (analysis_fps BETWEEN 2 AND 5),
    CONSTRAINT meetings_started_ck     CHECK (status NOT IN ('active', 'ended') OR started_at IS NOT NULL),
    CONSTRAINT meetings_ended_ck       CHECK (status <> 'ended' OR ended_at IS NOT NULL),
    CONSTRAINT meetings_end_reason_ck  CHECK (end_reason IS NULL OR end_reason IN ('organizer', 'empty_timeout', 'admin'))
);
CREATE INDEX meetings_owner_idx  ON meeting.meetings (owner_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX meetings_status_idx ON meeting.meetings (status) WHERE status IN ('scheduled', 'active');
CREATE INDEX meetings_title_trgm_idx ON meeting.meetings USING gin (title gin_trgm_ops);
CREATE INDEX meetings_deleted_idx ON meeting.meetings (deleted_at) WHERE deleted_at IS NOT NULL;

CREATE TABLE meeting.participants (
    id                      uuid        PRIMARY KEY,            -- identity LiveKit: p_<id>
    meeting_id              uuid        NOT NULL REFERENCES meeting.meetings (id) ON DELETE CASCADE,
    user_id                 uuid,                               -- NULL для гостя
    display_name            text        NOT NULL,
    role                    text        NOT NULL,
    consent_state           text        NOT NULL,
    participant_token_hash  bytea,                              -- только у гостей
    is_removed              boolean     NOT NULL DEFAULT false, -- удален организатором, повторный вход запрещен
    first_joined_at         timestamptz,
    last_left_at            timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT participants_token_uk      UNIQUE (participant_token_hash),
    CONSTRAINT participants_name_ck       CHECK (char_length(display_name) BETWEEN 1 AND 64),
    CONSTRAINT participants_role_ck       CHECK (role IN ('organizer', 'guest')),
    CONSTRAINT participants_consent_ck    CHECK (consent_state IN ('granted', 'denied', 'revoked', 'not_required')),
    CONSTRAINT participants_identity_ck   CHECK (
        (role = 'organizer' AND user_id IS NOT NULL AND participant_token_hash IS NULL) OR
        (role = 'guest'     AND user_id IS NULL     AND participant_token_hash IS NOT NULL))
);
CREATE INDEX participants_meeting_idx ON meeting.participants (meeting_id);
CREATE UNIQUE INDEX participants_meeting_user_uk ON meeting.participants (meeting_id, user_id) WHERE user_id IS NOT NULL;

-- Журнал согласий: append-only, намеренно без FK, чтобы переживать очистку встреч (хранится 3 года).
CREATE TABLE meeting.consents (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    meeting_id      uuid        NOT NULL,
    participant_id  uuid        NOT NULL,
    display_name    text        NOT NULL,                        -- снимок на момент решения
    meeting_title   text        NOT NULL,                        -- снимок на момент решения
    decision        text        NOT NULL,
    notice_version  text        NOT NULL,
    ip              inet,
    user_agent      text,
    decided_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT consents_decision_ck CHECK (decision IN ('granted', 'denied', 'revoked'))
);
CREATE INDEX consents_participant_idx ON meeting.consents (participant_id, decided_at);
CREATE INDEX consents_meeting_idx     ON meeting.consents (meeting_id);
CREATE INDEX consents_decided_idx     ON meeting.consents (decided_at);

-- Проекция заблокированных организаторов из user.events.
CREATE TABLE meeting.blocked_users (
    user_id     uuid        PRIMARY KEY,
    blocked_at  timestamptz NOT NULL DEFAULT now()
);

-- Идемпотентность вебхуков LiveKit.
CREATE TABLE meeting.processed_webhooks (
    event_id     text        PRIMARY KEY,
    received_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX processed_webhooks_received_idx ON meeting.processed_webhooks (received_at);

-- Отложенная синхронизация атрибутов участника в LiveKit (если LiveKit был недоступен).
CREATE TABLE meeting.livekit_sync_queue (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    meeting_id      uuid        NOT NULL,
    participant_id  uuid        NOT NULL,
    attributes      jsonb       NOT NULL,
    attempts        int         NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    last_error      text,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX livekit_sync_queue_next_idx ON meeting.livekit_sync_queue (next_attempt_at);

CREATE TABLE meeting.outbox (
    id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id      uuid        NOT NULL,
    topic         text        NOT NULL,                        -- топик Kafka
    event_key     text        NOT NULL,                        -- ключ сообщения (meeting_id / user_id)
    event_type    text        NOT NULL,
    envelope      jsonb       NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    published_at  timestamptz,
    attempts      int         NOT NULL DEFAULT 0,
    CONSTRAINT outbox_event_uk UNIQUE (event_id)
);
CREATE INDEX outbox_unpublished_idx ON meeting.outbox (id) WHERE published_at IS NULL;

RESET ROLE;
```

Пояснения:

- `participants_identity_ck` – у организатора есть `user_id` и нет `participant_token_hash`, у гостя – наоборот.
- `consents` без внешних ключей и со снимками имени и названия встречи: журнал согласий должен пережить очистку
  встреч (срок хранения 3 года).
- `livekit_sync_queue` – гарантированная доставка изменения согласия в LiveKit
  (см. [background-jobs.md](background-jobs.md)).

## Схема `analytics`

```sql
-- Схема analytics (владелец analytics_svc). Начальная миграция Alembic analytics-service.
SET ROLE analytics_svc;

CREATE TABLE analytics.meeting_projection (
    meeting_id        uuid        PRIMARY KEY,
    owner_id          uuid        NOT NULL,
    title             text        NOT NULL,
    status            text        NOT NULL,
    analysis_enabled  boolean     NOT NULL DEFAULT false,
    started_at        timestamptz,
    ended_at          timestamptz,
    updated_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT meeting_projection_status_ck CHECK (status IN ('scheduled', 'active', 'ended', 'cancelled'))
);
CREATE INDEX meeting_projection_owner_idx ON analytics.meeting_projection (owner_id);
CREATE INDEX meeting_projection_ended_idx ON analytics.meeting_projection (ended_at);

CREATE TABLE analytics.participant_projection (
    participant_id  uuid        PRIMARY KEY,
    meeting_id      uuid        NOT NULL REFERENCES analytics.meeting_projection (meeting_id) ON DELETE CASCADE,
    display_name    text        NOT NULL,
    role            text        NOT NULL,
    consent_state        text        NOT NULL,
    consent_decided_at   timestamptz,                            -- для отбрасывания отсчетов после отзыва
    updated_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX participant_projection_meeting_idx ON analytics.participant_projection (meeting_id);

-- Посекундные агрегаты. FK на проекцию намеренно нет: отсчеты и события встреч идут разными потоками
-- и могут прийти в любом порядке. Удаление – явным DELETE по meeting_id (префикс PK).
CREATE TABLE analytics.emotion_series (
    meeting_id      uuid        NOT NULL,
    participant_id  uuid        NOT NULL,
    ts              timestamptz NOT NULL,                        -- начало секунды
    samples         smallint    NOT NULL,
    face_samples    smallint    NOT NULL,
    p_angry         real,
    p_disgust       real,
    p_fear          real,
    p_happy         real,
    p_sad           real,
    p_surprise      real,
    p_neutral       real,
    PRIMARY KEY (meeting_id, participant_id, ts),
    CONSTRAINT emotion_series_samples_ck CHECK (samples > 0 AND face_samples BETWEEN 0 AND samples),
    CONSTRAINT emotion_series_probs_ck CHECK (
        (face_samples = 0 AND p_angry IS NULL AND p_disgust IS NULL AND p_fear IS NULL AND p_happy IS NULL
                          AND p_sad IS NULL AND p_surprise IS NULL AND p_neutral IS NULL)
        OR
        (face_samples > 0 AND p_angry    BETWEEN 0 AND 1 AND p_disgust BETWEEN 0 AND 1
                          AND p_fear     BETWEEN 0 AND 1 AND p_happy   BETWEEN 0 AND 1
                          AND p_sad      BETWEEN 0 AND 1 AND p_surprise BETWEEN 0 AND 1
                          AND p_neutral  BETWEEN 0 AND 1))
);
CREATE INDEX emotion_series_meeting_ts_idx ON analytics.emotion_series (meeting_id, ts);

CREATE TABLE analytics.markers (
    id              uuid        PRIMARY KEY,
    meeting_id      uuid        NOT NULL REFERENCES analytics.meeting_projection (meeting_id) ON DELETE CASCADE,
    ts              timestamptz NOT NULL,
    kind            text        NOT NULL,
    participant_id  uuid,                                        -- NULL = вся встреча
    label           text        NOT NULL,
    details         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_by      uuid,                                        -- NULL для автоматических
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT markers_kind_ck  CHECK (kind IN ('auto_shift', 'manual')),
    CONSTRAINT markers_label_ck CHECK (char_length(label) BETWEEN 1 AND 200),
    CONSTRAINT markers_author_ck CHECK ((kind = 'manual') = (created_by IS NOT NULL))
);
CREATE INDEX markers_meeting_ts_idx ON analytics.markers (meeting_id, ts);

CREATE TABLE analytics.reports (
    meeting_id     uuid        PRIMARY KEY REFERENCES analytics.meeting_projection (meeting_id) ON DELETE CASCADE,
    status         text        NOT NULL DEFAULT 'pending',
    summary        jsonb,
    model_version  text,
    error          text,
    attempts       int         NOT NULL DEFAULT 0,
    generated_at   timestamptz,
    updated_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT reports_status_ck CHECK (status IN ('pending', 'ready', 'failed')),
    CONSTRAINT reports_ready_ck  CHECK (status <> 'ready' OR (summary IS NOT NULL AND generated_at IS NOT NULL))
);
CREATE INDEX reports_pending_idx ON analytics.reports (updated_at) WHERE status = 'pending';

CREATE TABLE analytics.outbox (
    id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id      uuid        NOT NULL,
    topic         text        NOT NULL,                        -- топик Kafka
    event_key     text        NOT NULL,                        -- ключ сообщения (meeting_id / user_id)
    event_type    text        NOT NULL,
    envelope      jsonb       NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    published_at  timestamptz,
    attempts      int         NOT NULL DEFAULT 0,
    CONSTRAINT outbox_event_uk UNIQUE (event_id)
);
CREATE INDEX outbox_unpublished_idx ON analytics.outbox (id) WHERE published_at IS NULL;

RESET ROLE;
```

Пояснения:

- `emotion_series` без внешнего ключа на проекцию: отсчеты и события встреч читаются из разных топиков Kafka,
  порядок их прихода не гарантирован.
- `emotion_series_probs_ck` – вероятности заполнены тогда и только тогда, когда в секунде был хотя бы один кадр с лицом.

## Таблица `outbox` (во всех схемах)

Паттерн «транзакционный outbox»: событие записывается в `outbox` **в той же транзакции**, что и изменение данных;
фоновая задача отправляет его в топик Kafka `topic` с ключом `event_key` и после подтверждения брокера проставляет
`published_at`. Так событие не теряется при сбое между `COMMIT` и отправкой и не публикуется для откатившейся
транзакции. Подробнее – [conventions.md](conventions.md#6-публикация-событий-transactional-outbox),
[ADR-011](../adr/ADR-011-transactional-outbox.md).

## Оценка объема

| Таблица | Рост | Объем за семестр эксплуатации (≈ 300 встреч) |
|---|---|---|
| `analytics.emotion_series` | ≈ 54 тыс. строк на встречу (10 уч. × 1,5 ч) | ≈ 16 млн строк ≈ 1,5 ГБ с индексами (верхняя оценка) |
| `meeting.consents` | 1–3 строки на участника | < 10 тыс. строк |
| Остальные | – | Единицы МБ |

При росте `emotion_series` сверх 10 млн строк – секционирование по `ts` (месяцы) декларативным `PARTITION BY RANGE`;
первичный ключ этому не мешает (добавляется `ts` – он уже в ключе).
