# REST API

Базовый адрес внешнего API – `https://vks.<домен>/api/v1`. Формат – JSON (`snake_case`, UTF-8), время – ISO 8601 UTC,
идентификаторы – UUID.

Этот документ – контракт REST API до начала разработки. После реализации сервисы публикуют OpenAPI, генерируемый
FastAPI из кода (`/openapi.json`, в dev – Swagger UI); по нему фронтенд генерирует типы (`openapi-typescript`).
Расхождение кода и этого документа исправляется в том же pull request.

## 1. Общие правила

| Аспект | Правило |
|---|---|
| Аутентификация организатора и администратора | `Authorization: Bearer <access_token>` (JWT RS256, 15 мин) |
| Аутентификация гостя | `Authorization: Participant <participant_token>` |
| Refresh-токен | Cookie `vks_refresh` (`HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`, 30 сут) |
| Межсервисные вызовы | `X-Service-Token: <секрет>` (только `/internal/*`, не доступны через Nginx) |
| Пагинация | `?limit=20&cursor=<opaque>` (limit 1–100) → `{"items": [...], "next_cursor": "…" \| null}` |
| Идемпотентность | `POST /meetings` принимает заголовок `Idempotency-Key` (до 64 символов, хранится 24 ч) |
| Трассировка | Nginx проставляет `X-Request-ID`; сервисы возвращают его в ответе и в ошибках (`request_id`) |
| Ограничение частоты | `429 too_many_requests` + заголовок `Retry-After` (с) |

### Формат ошибок (RFC 9457 Problem Details)

`Content-Type: application/problem+json`

```json
{
  "type": "https://vks.example.ru/errors/meeting_not_started",
  "title": "Встреча еще не началась",
  "status": 409,
  "detail": "Организатор еще не начал встречу",
  "code": "meeting_not_started",
  "request_id": "c0a8…",
  "errors": [{"loc": ["body", "display_name"], "msg": "…", "type": "…"}]
}
```

`errors` присутствует только у `validation_error`. Чужой ресурс возвращает `404`, а не `403`.

### Реестр кодов ошибок

| Код | HTTP | Где |
|---|---|---|
| `validation_error` | 422 | Везде |
| `unauthorized` | 401 | Нет/недействителен токен |
| `forbidden` | 403 | Недостаточно прав (например, не admin) |
| `not_found` | 404 | Ресурс не найден или не принадлежит пользователю |
| `too_many_requests` | 429 | Вход, ссылки-приглашения, восстановление пароля |
| `invalid_credentials` | 401 | Неверный e-mail или пароль |
| `user_blocked` | 401 / 403 | Вход или вход во встречу заблокированного пользователя |
| `email_taken` | 409 | Регистрация |
| `invalid_reset_token` | 400 | Восстановление пароля |
| `last_admin` | 409 | Нельзя заблокировать/понизить/удалить последнего администратора или себя |
| `meeting_not_started` | 409 | Вход гостя до начала встречи |
| `meeting_ended` | 409 | Вход/действия в завершенной встрече |
| `meeting_cancelled` | 409 | Вход в отмененную встречу |
| `meeting_full` | 409 | Превышено 10 участников |
| `meeting_not_editable` | 409 | Изменение параметров начатой встречи |
| `consent_required` | 409 | Не передано решение о согласии при включенном анализе |
| `notice_outdated` | 409 | Показанная версия уведомления устарела |
| `analysis_disabled` | 409 | Изменение согласия во встрече без анализа |
| `participant_removed` | 409 | Повторный вход удаленного участника |
| `idempotency_key_reused` | 409 | Тот же `Idempotency-Key` с другим телом |
| `meeting_in_progress` | 409 | Экспорт CSV до завершения встречи |
| `report_not_ready` | 409 | Экспорт PDF до готовности отчета |
| `livekit_unavailable` | 503 | LiveKit недоступен при входе или модерации |
| `internal_error` | 500 | Непредвиденная ошибка |

### Общие типы

| Тип | Значения |
|---|---|
| `MeetingStatus` | `scheduled` \| `active` \| `ended` \| `cancelled` |
| `ConsentState` | `granted` \| `denied` \| `revoked` \| `not_required` |
| `EmotionLabel` | `angry` \| `disgust` \| `fear` \| `happy` \| `sad` \| `surprise` \| `neutral` (этот порядок – во всех массивах вероятностей) |
| `EmotionDistribution` | Объект с 7 полями `EmotionLabel` → число 0…1, сумма ≈ 1 |

## 2. auth-service

| Метод | Путь | Доступ | Назначение |
|---|---|---|---|
| POST | `/auth/register` | все | Регистрация организатора |
| POST | `/auth/login` | все | Вход |
| POST | `/auth/refresh` | cookie | Обновление токенов |
| POST | `/auth/logout` | cookie | Выход |
| GET | `/auth/.well-known/jwks.json` | все | Публичные ключи JWT |
| GET | `/auth/config` | все | Публичные флаги |
| POST | `/auth/password-reset/request` | все | Письмо для восстановления пароля (доп.) |
| POST | `/auth/password-reset/confirm` | все | Новый пароль по токену (доп.) |
| GET, PATCH | `/users/me` | организатор, admin | Профиль |
| POST | `/users/me/password` | организатор, admin | Смена пароля |
| GET | `/admin/users` | admin | Список пользователей |
| PATCH, DELETE | `/admin/users/{user_id}` | admin | Блокировка, роль, удаление |

### Схемы

| Схема | Поля |
|---|---|
| `User` | `id`, `email`, `display_name`, `role`: `organizer` \| `admin` |
| `AdminUser` | `User` + `status`: `active` \| `blocked`, `created_at`, `last_login_at` \| null |
| `TokenResponse` | `access_token`, `token_type` = `Bearer`, `expires_in` (с), `user`: `User` |

### `POST /auth/register`

| Поле запроса | Тип | Ограничения |
|---|---|---|
| `email` | string | e-mail, ≤ 254 |
| `password` | string | 8–128 символов |
| `display_name` | string | 1–100 |

Ответы: `201 User`; `409 email_taken`; `422`; `429`.

### `POST /auth/login`

Запрос `{"email", "password"}`. Ответ `200 TokenResponse` + `Set-Cookie: vks_refresh=…`.
Ошибки: `401 invalid_credentials` | `user_blocked`; `422`; `429` (5 попыток за 15 мин на IP + e-mail).

```json
{"access_token": "eyJ…", "token_type": "Bearer", "expires_in": 900,
 "user": {"id": "0192…", "email": "user@example.ru", "display_name": "Иван Петров", "role": "organizer"}}
```

### `POST /auth/refresh`, `POST /auth/logout`

`refresh`: `200 TokenResponse` + новый cookie (ротация); `401 unauthorized` (в т. ч. при повторном использовании
токена – отзывается вся цепочка). `logout`: `204`, cookie очищается.

### `GET /auth/.well-known/jwks.json`

`200 {"keys": [{"kty": "RSA", "kid": "…", "use": "sig", "alg": "RS256", "n": "…", "e": "AQAB"}]}`

### `GET /auth/config`

`200 {"registration_enabled": true, "password_reset_enabled": false}`

### `POST /auth/password-reset/request`, `/confirm`

- `request`: `{"email"}` → `202` всегда (не раскрывает существование адреса); `404`, если функция выключена; `429`.
- `confirm`: `{"token", "new_password" (8–128)}` → `204` (все сессии завершены); `400 invalid_reset_token`; `422`.

### `/users/me`

- `GET` → `200 User`.
- `PATCH {"display_name"}` → `200 User`.
- `POST /users/me/password {"current_password", "new_password"}` → `204` (остальные сессии завершаются); `401 invalid_credentials`.

### `/admin/users`

- `GET ?q=&status=active|blocked&limit=&cursor=` → `200 {items: AdminUser[], next_cursor}`.
- `PATCH /admin/users/{user_id} {"status"?, "role"?}` → `200 AdminUser`; `404`; `409 last_admin`.
- `DELETE /admin/users/{user_id}` → `204` (встречи и аналитика удаляются каскадно через события); `404`; `409 last_admin`.

## 3. meeting-service

| Метод | Путь | Доступ | Назначение |
|---|---|---|---|
| POST | `/meetings` | организатор | Создать встречу |
| GET | `/meetings` | организатор | История и запланированные встречи |
| GET, PATCH, DELETE | `/meetings/{meeting_id}` | владелец | Карточка, изменение, удаление |
| POST | `/meetings/{meeting_id}/join` | владелец | Вход организатора (первый вход активирует встречу) |
| POST | `/meetings/{meeting_id}/end` | владелец | Завершить встречу |
| GET | `/meetings/{meeting_id}/participants` | владелец | Участники и согласия |
| POST | `/meetings/{meeting_id}/participants/{participant_id}/mute` | владелец | Выключить микрофон/камеру |
| POST | `/meetings/{meeting_id}/participants/{participant_id}/remove` | владелец | Удалить из встречи |
| GET | `/join/{invite_code}` | все | Информация для лобби |
| POST | `/join/{invite_code}` | все | Вход гостя |
| PUT | `/participants/me/consent` | гость (Participant) или организатор (Bearer) | Изменить согласие |
| POST | `/participants/me/rejoin` | гость | Новый токен LiveKit |
| GET, PUT | `/settings` | организатор | Настройки анализа по умолчанию |
| GET | `/admin/meetings` | admin | Все встречи |
| GET | `/admin/health` | admin | Состояние компонентов |
| GET | `/internal/meetings/{meeting_id}/access?user_id=` | сервис | Проверка организатора (realtime) |
| GET | `/internal/meetings/{meeting_id}` | сервис | Встреча с участниками (analytics, realtime) |
| POST | `/webhooks/livekit` | LiveKit | Вебхуки ([livekit-integration.md](livekit-integration.md)) |

### Схемы

| Схема | Поля |
|---|---|
| `Meeting` | `id`, `title`, `status`: `MeetingStatus`, `invite_code` (`^[a-z2-7]{10}$`), `invite_url`, `analysis_enabled`, `analysis_fps` (2–5), `scheduled_at` \| null, `started_at` \| null, `ended_at` \| null, `participants_count`, `created_at` |
| `AdminMeeting` | `Meeting` + `owner_id`, `online_participants` |
| `Participant` | `id`, `display_name`, `role`: `organizer` \| `guest`, `consent_state`: `ConsentState`, `online`, `is_removed`, `first_joined_at` \| null, `last_left_at` \| null |
| `JoinResult` | `participant_id`, `livekit_url`, `livekit_token`, `meeting`: `{id, title, status, analysis_enabled}` |
| `ConsentResult` | `consent_state`, `synced` (атрибут в LiveKit уже обновлен) |
| `Settings` | `analysis_enabled_default`, `analysis_fps_default` (2–5) |

### `POST /meetings`

| Поле запроса | Тип | Обязательно | Ограничения / по умолчанию |
|---|---|---|---|
| `title` | string | да | 1–200 |
| `scheduled_at` | datetime \| null | нет | null – встреча «сейчас» |
| `analysis_enabled` | bool | нет | из `/settings` |
| `analysis_fps` | int | нет | 2–5, из `/settings` |

Заголовок `Idempotency-Key` (опц.). Ответы: `201 Meeting`; `409 idempotency_key_reused`; `422`.

```json
{"id": "0192…", "title": "Переговоры с ООО «Ромашка»", "status": "scheduled", "invite_code": "k3m7qx4tpa",
 "invite_url": "https://vks.example.ru/j/k3m7qx4tpa", "analysis_enabled": true, "analysis_fps": 3,
 "scheduled_at": "2026-11-20T07:00:00Z", "started_at": null, "ended_at": null,
 "participants_count": 0, "created_at": "2026-11-19T10:00:00Z"}
```

### `GET /meetings`

Параметры: `status` (через запятую), `q` (подстрока названия, ≤ 100), `from`, `to` (даты), `limit`, `cursor`.
Сортировка – `coalesce(started_at, scheduled_at, created_at) desc`, удаленные не возвращаются.
Ответ `200 {items: Meeting[], next_cursor}`.

### `/meetings/{meeting_id}`

- `GET` → `200 Meeting`; `404`.
- `PATCH {"title"?, "scheduled_at"?, "analysis_enabled"?, "analysis_fps"?}` → `200 Meeting`; `title` меняется в любом
  статусе, остальное – только в `scheduled` (`409 meeting_not_editable`).
- `DELETE` → `204`; активная встреча сначала завершается; аналитика удаляется по событию `meeting.deleted`.

### `POST /meetings/{meeting_id}/join`

Запрос `{"consent": "granted" | "denied"}` (обязательно, если анализ включен). Ответ `200 JoinResult`.
Ошибки: `403 user_blocked`; `404`; `409 meeting_ended` | `meeting_cancelled` | `meeting_full` | `consent_required`;
`503 livekit_unavailable`.

```json
{"participant_id": "0192…", "livekit_url": "wss://livekit.example.ru", "livekit_token": "eyJ…",
 "meeting": {"id": "0192…", "title": "…", "status": "active", "analysis_enabled": true}}
```

### `POST /meetings/{meeting_id}/end`

Идемпотентно. `200 Meeting` (`status = ended`); `404`; `409 meeting_cancelled`.

### Участники и модерация

- `GET /meetings/{meeting_id}/participants` → `200 {items: Participant[]}`.
- `POST …/participants/{participant_id}/mute {"kind": "audio" | "video"}` → `204`; `409 meeting_ended`; `503`.
- `POST …/participants/{participant_id}/remove` → `204`; повторный вход по токену этого участника – `409 participant_removed`.

### `GET /join/{invite_code}` (без аутентификации)

```json
{"title": "…", "organizer_name": "Иван Петров", "status": "active", "scheduled_at": null,
 "analysis_enabled": true,
 "consent_notice": {"version": "v1", "text_md": "Во время встречи организатор видит…"}}
```

`consent_notice` = null, если анализ выключен. Ошибки: `404`; `429`.

### `POST /join/{invite_code}` (без аутентификации)

| Поле запроса | Тип | Обязательно | Ограничения |
|---|---|---|---|
| `display_name` | string | да | 1–64 |
| `consent` | `granted` \| `denied` | если анализ включен | – |
| `notice_version` | string | если анализ включен | должна совпадать с текущей |

Ответ `200 JoinResult + participant_token`:

```json
{"participant_id": "0192…", "participant_token": "pt_…", "livekit_url": "wss://livekit.example.ru",
 "livekit_token": "eyJ…", "meeting": {"id": "0192…", "title": "…", "status": "active", "analysis_enabled": true}}
```

Ошибки: `404`; `409 meeting_not_started` (клиент повторяет раз в 5 с) | `meeting_ended` | `meeting_full` |
`consent_required` | `notice_outdated`; `422`; `429`; `503`.

### `PUT /participants/me/consent`

Аутентификация – `Participant <token>` либо `Bearer` + параметр `?meeting_id=` (организатор). Запрос
`{"decision": "granted" | "revoked"}`. Ответы: `200 ConsentResult` (LiveKit синхронизирован) или
`202 ConsentResult` (`synced = false`, синхронизация в очереди); `401`; `409 analysis_disabled` | `meeting_ended`.

### `POST /participants/me/rejoin`

Гость после перезагрузки вкладки. `200 JoinResult`; `401`; `409 meeting_ended` | `participant_removed`.

### `/settings`

`GET` → `200 Settings`; `PUT Settings` → `200 Settings`.

### `GET /admin/meetings?status=&limit=&cursor=`

`200 {items: AdminMeeting[], next_cursor}` – без аналитики и данных участников.

### `GET /admin/health`

`status`: `ok` | `degraded` | `down` – сводный и по компонентам.

```json
{"status": "degraded", "checked_at": "2026-11-20T07:15:00Z",
 "components": {
   "auth-service": {"status": "ok"}, "meeting-service": {"status": "ok"},
   "realtime-service": {"status": "ok"},
   "analytics-service": {"status": "ok", "consumer_lag_s": 0.4},
   "emotion-ml-service": {"status": "down", "last_heartbeat": "2026-11-20T07:14:31Z"},
   "livekit": {"status": "ok", "rooms": 2, "participants": 9},
   "kafka": {"status": "ok"}, "postgres": {"status": "ok"}, "redis": {"status": "ok"}}}
```

### Внутренний API

- `GET /internal/meetings/{meeting_id}/access?user_id=` →
  `200 {"allowed": true, "meeting_status": "active", "analysis_enabled": true}`.
- `GET /internal/meetings/{meeting_id}` → `200 Meeting + {"owner_id", "participants": Participant[]}`; `404`.

## 4. analytics-service

Доступ ко всем эндпоинтам – только владелец встречи (Bearer).

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/reports/{meeting_id}` | Отчет: статус, сводка, отметки |
| GET | `/reports/{meeting_id}/series` | Временные ряды (и во время встречи) |
| GET | `/reports/{meeting_id}/export.csv` | Экспорт рядов в CSV |
| GET | `/reports/{meeting_id}/export.pdf` | PDF-отчет |
| POST | `/reports/{meeting_id}/markers` | Ручная отметка |
| DELETE | `/reports/{meeting_id}/markers/{marker_id}` | Удалить отметку |

### Схемы

| Схема | Поля |
|---|---|
| `Report` | `meeting_id`, `status`: `pending` \| `ready` \| `failed`, `model_version` \| null, `meeting`: `{title, started_at, ended_at, duration_s}`, `summary`: `ReportSummary` (нет при `pending`), `markers`: `Marker[]`, `disclaimer` |
| `ReportSummary` | `overall`: `{distribution: EmotionDistribution, face_detected_ratio, negative_share}`; `participants[]`: `{participant_id, display_name, consent, distribution \| null, dominant \| null, face_detected_ratio \| null, analyzed_seconds}` |
| `Marker` | `id`, `ts`, `kind`: `auto_shift` \| `manual`, `participant_id` \| null, `label`, `details` (объект) |

### `GET /reports/{meeting_id}`

```json
{"meeting_id": "0192…", "status": "ready", "model_version": "emotion-effnetb0@1.0.0",
 "meeting": {"title": "…", "started_at": "…", "ended_at": "…", "duration_s": 3120},
 "summary": {
   "overall": {"distribution": {"angry": 0.04, "disgust": 0.03, "fear": 0.02, "happy": 0.22,
                                "sad": 0.07, "surprise": 0.11, "neutral": 0.51},
               "face_detected_ratio": 0.93, "negative_share": 0.16},
   "participants": [{"participant_id": "…", "display_name": "Анна", "consent": "granted",
                     "distribution": {"…": 0.0}, "dominant": "neutral", "face_detected_ratio": 0.95,
                     "analyzed_seconds": 2950}]},
 "markers": [{"id": "…", "ts": "…", "kind": "auto_shift", "participant_id": null,
              "label": "Рост негативных эмоций", "details": {"negative_delta": 0.34}},
             {"id": "…", "ts": "…", "kind": "manual", "participant_id": null, "label": "Вопрос о зарплате", "details": {}}],
 "disclaimer": "Результаты отражают внешнее выражение лица и носят рекомендательный характер."}
```

`status = pending` – отчет строится: клиент ждет `report.ready` по WebSocket или опрашивает раз в 3 с. Ошибки: `404`.

### `GET /reports/{meeting_id}/series`

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `participant_id` | UUID | все | Один участник |
| `resolution` | `1s` \| `5s` \| `30s` | `5s` | Шаг агрегации |
| `since` | datetime | – | Только точки позже (догрузка после переподключения) |

```json
{"resolution": "5s", "labels": ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"],
 "series": [{"participant_id": "…",
             "points": [{"ts": "…", "p": [0.02, 0.01, 0.03, 0.40, 0.05, 0.09, 0.40], "face_ratio": 1.0},
                        {"ts": "…", "p": null, "face_ratio": 0.0}]}]}
```

`p = null` – лицо не найдено во всем интервале. Ошибки: `404`; `422`.

### Экспорт

- `GET /reports/{meeting_id}/export.csv` – `text/csv; charset=utf-8` с BOM, `Content-Disposition: attachment`.
  Колонки: `ts,participant_id,display_name,samples,face_samples,p_angry,p_disgust,p_fear,p_happy,p_sad,p_surprise,p_neutral`.
  Ошибки: `404`; `409 meeting_in_progress`.
- `GET /reports/{meeting_id}/export.pdf` – `application/pdf`. Ошибки: `404`; `409 report_not_ready`.

### Отметки

- `POST /reports/{meeting_id}/markers {"label" (1–200), "ts"?: datetime | null, "participant_id"?: UUID | null}` –
  `ts = null` → текущее время сервера, иначе должно попадать в интервал встречи. Ответ `201 Marker`; `404`; `422`.
- `DELETE /reports/{meeting_id}/markers/{marker_id}` → `204`; `404`.
