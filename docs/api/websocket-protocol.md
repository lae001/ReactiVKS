# Протокол WebSocket (realtime-service)

Адрес: `wss://vks.<домен>/ws`. Используется только организатором для панели эмоций и уведомлений.
Сигнализация WebRTC и чат **не** идут через этот канал – их обслуживает LiveKit.

## Подключение

1. Клиент открывает `wss://vks.<домен>/ws` (подпротокол `vks.v1`).
2. Первое сообщение клиента – `auth` с access-токеном (токен не передается в URL, чтобы не попадать в журналы).
3. Сервер отвечает `welcome`; затем клиент отправляет `subscribe`.

Все сообщения – JSON-объекты с полем `type`. Поле `id` (необязательное) в запросах клиента возвращается в ответе.

## Сообщения клиента

| type | Поля | Описание |
|---|---|---|
| `auth` | `token` | Первичная аутентификация |
| `auth.refresh` | `token` | Обновление токена в открытом соединении |
| `subscribe` | `meeting_id` | Подписка на встречу (только владелец) |
| `unsubscribe` | `meeting_id` | Отписка |
| `ping` | – | Проверка соединения (каждые 20 с) |

## Сообщения сервера

| type | Поля | Когда |
|---|---|---|
| `welcome` | `user_id`, `server_time` | После успешного `auth` |
| `subscribed` | `meeting_id`, `snapshot` | После `subscribe` |
| `emotion.update` | `meeting_id`, `items[]` | Пакет обновлений (не чаще 4/с) |
| `participant.status` | `meeting_id`, `participant_id`, `display_name`, `state` | Вход/выход, изменение согласия |
| `analysis.status` | `meeting_id`, `state`, `effective_fps?` | `active` \| `degraded` \| `unavailable` \| `off` |
| `meeting.ended` | `meeting_id` | Встреча завершена |
| `report.ready` | `meeting_id` | Отчет сформирован |
| `pong` | `server_time` | Ответ на `ping` |
| `error` | `code`, `message`, `id?` | Ошибка запроса |

### `snapshot`
```json
{
  "analysis": {"state": "active", "effective_fps": 3},
  "participants": [
    {"participant_id": "0192…", "display_name": "Анна", "role": "guest", "state": "analyzing",
     "last": {"ts": "2026-11-20T07:12:03.310Z", "dominant": "happy", "confidence": 0.71,
              "p": [0.02, 0.01, 0.03, 0.71, 0.05, 0.08, 0.10]}},
    {"participant_id": "0193…", "display_name": "Олег", "role": "guest", "state": "no_consent", "last": null}
  ],
  "labels": ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]
}
```

### `emotion.update`
```json
{"type": "emotion.update", "meeting_id": "0192…",
 "items": [
   {"participant_id": "0192…", "ts": "2026-11-20T07:12:03.643Z", "state": "analyzing",
    "dominant": "neutral", "confidence": 0.58, "p": [0.03, 0.01, 0.02, 0.21, 0.07, 0.08, 0.58]},
   {"participant_id": "0194…", "ts": "2026-11-20T07:12:03.650Z", "state": "no_face"}
 ]}
```

Порядок вероятностей `p` соответствует `labels` из `snapshot`.

### Состояния участника (`state`)

| state | Значение |
|---|---|
| `analyzing` | Анализ идет, лицо найдено |
| `no_face` | Лицо не обнаружено |
| `camera_off` | Камера выключена |
| `no_consent` | Участник не дал согласие или отозвал его |
| `left` | Участник покинул встречу |

## Коды закрытия

| Код | Причина |
|---|---|
| 4400 | Некорректное сообщение |
| 4401 | Нет или истек токен |
| 4403 | Нет доступа к встрече |
| 4408 | Не выполнены `auth`/`subscribe` в течение 10 с |
| 1012 | Перезапуск сервиса (клиент переподключается) |

## Переподключение

Экспоненциальная задержка 0,5 → 1 → 2 → 4 → 8 с (макс. 10 с, со случайным разбросом). После переподключения –
повторные `auth` и `subscribe`; пропущенный участок графика клиент догружает запросом
`GET /api/v1/reports/{meeting_id}/series?since=<последний ts>&resolution=1s`.

## Версионирование

Несовместимые изменения – новый подпротокол (`vks.v2`); добавление полей – без смены версии (клиент игнорирует
неизвестные поля и типы сообщений).
