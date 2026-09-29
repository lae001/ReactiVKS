# Интеграция с LiveKit

Вся зависимость от LiveKit сосредоточена в двух адаптерах: `LiveKitGateway` (meeting-service) и транспортном слое
emotion-ml-service. Клиентская часть использует официальный SDK.

## Соответствие понятий

| Система | LiveKit |
|---|---|
| Встреча `meetings.id` | Комната `room.name` |
| Участник `participants.id` | `identity = p_<participant_id>` |
| Отображаемое имя | `name` |
| Роль, согласие | Атрибуты участника `vks.role`, `vks.consent` |
| ML-агент | Агент `emotion-agent` (LiveKit Agents), атрибут `vks.kind = agent` |
| Чат | Текстовые потоки / data-сообщения, тема `lk.chat` |

## Атрибуты участника

| Атрибут | Значения | Кто устанавливает |
|---|---|---|
| `vks.role` | `organizer` \| `guest` | meeting-service (в токене) |
| `vks.consent` | `granted` \| `denied` \| `revoked` \| `not_required` | meeting-service (в токене, затем `UpdateParticipant`) |
| `vks.kind` | `human` \| `agent` | meeting-service / агент |

Участники не могут менять собственные атрибуты (`canUpdateOwnMetadata = false`).

## Токен доступа участника

```json
{
  "iss": "<LIVEKIT_API_KEY>",
  "sub": "p_0192…",
  "name": "Анна",
  "exp": "<+6 ч>",
  "video": {"room": "0192…", "roomJoin": true, "canPublish": true, "canSubscribe": true,
            "canPublishData": true, "canUpdateOwnMetadata": false,
            "canPublishSources": ["camera", "microphone", "screen_share", "screen_share_audio"]},
  "attributes": {"vks.role": "guest", "vks.consent": "granted", "vks.kind": "human"}
}
```

## Вызовы Server API (meeting-service → LiveKit)

| Операция | Когда |
|---|---|
| `CreateRoom(name, empty_timeout=300, departure_timeout=20, max_participants=11)` | Первый вход организатора |
| `CreateDispatch(room, agent_name="emotion-agent", metadata={"fps": 3})` | После создания комнаты, если анализ включен |
| `UpdateParticipant(room, identity, attributes)` | Изменение согласия |
| `MutePublishedTrack(room, identity, track_sid, muted=true)` | Модерация (выключить микрофон/камеру) |
| `RemoveParticipant(room, identity)` | Модерация (удалить); повторный вход того же участника блокируется флагом в БД |
| `DeleteRoom(room)` | Завершение встречи организатором |
| `ListRooms`, `ListParticipants` | `/admin/health`, `/admin/meetings`, сверка состояния |

## Вебхуки (LiveKit → meeting-service)

Адрес: `http://meeting-service:8002/webhooks/livekit` (внутренняя сеть). Проверка подписи – `WebhookReceiver` SDK.

| Событие | Обработка |
|---|---|
| `participant_joined` | `first_joined_at`, событие `participant.joined` (для агента – игнорируется) |
| `participant_left` | `last_left_at`, событие `participant.left` |
| `room_finished` | Если встреча `active` – перевод в `ended` (`reason = empty_timeout`), событие `meeting.ended` |
| `track_published` | Не используется в MVP (ML получает события напрямую из комнаты) |

## Конфигурация LiveKit (`deploy/livekit/livekit.yaml`, основное)

```yaml
port: 7880
rtc:
  tcp_port: 7881
  udp_port: 7882          # мультиплексированный UDP-порт
  use_external_ip: true
turn:
  enabled: true
  domain: turn.<домен>
  udp_port: 3478
  tls_port: 5349          # доступен снаружи через Nginx stream на 443
  external_tls: true      # TLS терминируется Nginx
keys:
  <LIVEKIT_API_KEY>: <LIVEKIT_API_SECRET>
webhook:
  api_key: <LIVEKIT_API_KEY>
  urls: ["http://127.0.0.1:8002/webhooks/livekit"]
room:
  empty_timeout: 300
  max_participants: 11
logging:
  level: info
```

Точные ключи конфигурации сверяются с версией LiveKit, выбранной на спайке 1.

## Замена медиасервера

При замене LiveKit (например, на mediasoup) переписываются: `LiveKitGateway`, транспорт ML-сервиса (получение
кадров и событий участников), комната во frontend. Контракты `meeting.events`, `emotion.samples`, REST и WebSocket
остаются без изменений.
