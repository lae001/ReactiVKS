# Заметки по WebRTC и LiveKit в браузере

Результат задачи EMO-17 (спринт 1). Автор – Зимирев К. М. Пробное подключение – страница `/dev/livekit`
(только `pnpm dev`), проверка возможностей браузера – `frontend/src/shared/lib/webrtc-support.ts`.

## 1. WebRTC API браузера

| API | Зачем | Замечания |
|---|---|---|
| `navigator.mediaDevices.getUserMedia({ audio, video })` | Доступ к камере и микрофону | Только в защищённом контексте: HTTPS или `localhost`. Запрос разрешения показывает браузер |
| `navigator.mediaDevices.enumerateDevices()` | Список камер и микрофонов для лобби | Подписи устройств (`label`) доступны только после выдачи разрешения |
| `RTCPeerConnection` | Само соединение, ICE, SRTP | Напрямую не используется: сигнализацию, ICE и работу с SFU берёт на себя `livekit-client` |
| `chrome://webrtc-internals` | Диагностика соединения | Дамп прикладывается к дефектам по видеосвязи ([журнал дефектов](../testing/defect-log.md)) |

Перед входом в лобби `checkWebRtcSupport()` проверяет `RTCPeerConnection`, `getUserMedia` и защищённый контекст,
`describeWebRtcProblem()` возвращает понятное сообщение ([поддержка браузеров](README.md)).

## 2. livekit-client

- `Room` – центральный объект: подключение (`connect(url, token)`), события `RoomEvent.*`, участники, дорожки.
- Параметры комнаты, нужные Системе: `adaptiveStream`, `dynacast`, simulcast (3 слоя для 720p).
- Атрибуты участника (`participant.attributes`): `vks.role`, `vks.consent`, `vks.kind`. Участник с `vks.kind = agent`
  – ML-агент: по нему включается индикатор «Идет анализ эмоций», а сам агент исключается из раскладки плиток
  ([livekit-integration.md](../api/livekit-integration.md)).

## 3. @livekit/components-react

| Компонент | Назначение |
|---|---|
| `<LiveKitRoom token serverUrl connect audio video>` | Провайдер контекста комнаты |
| `<VideoConference />` | Готовая раскладка – используется в песочнице; в продукте собираем свою из `GridLayout`, `ParticipantTile`, `ControlBar`, `Chat` |
| `<RoomAudioRenderer />` | Воспроизведение звука участников |

Стили – `@livekit/components-styles` и атрибут `data-lk-theme="default"`; поверх них – токены проекта
(переменные `--lk-*`, см. [UI-кит](ui-kit.md)).

## 4. Пробное подключение (песочница `/dev/livekit`)

1. Запустить LiveKit в режиме разработки: `livekit-server --dev` (ключи режима: `devkey` / `secret`, порт 7880).
2. Выпустить два токена с разными `identity`:
   `lk token create --api-key devkey --api-secret secret --join --room test --identity u1`
   (и так же для `u2`).
3. `pnpm dev`, открыть `http://localhost:5173/dev/livekit` в двух вкладках, указать адрес
   `ws://localhost:7880` и токен.
4. Должно появиться видео обеих вкладок. Камера нужна разрешённая; для проверки без камеры в Chrome есть флаги
   `--use-fake-device-for-media-stream --use-fake-ui-for-media-stream`.

Статус проверки: страница собирается и проходит типизацию и линтер; подключение к реальному серверу LiveKit
вручную подтверждается отдельно (запись результата – в отчёте о статусе спринта).

## 5. Открытые вопросы (спринты 2–3)

- Выдача токена участнику и гостю по ссылке `/j/:inviteCode` – по контракту meeting-service
  ([livekit-integration.md](../api/livekit-integration.md)).
- Safari 17+: проверить simulcast и выбор устройства вывода звука.
- Поведение при закрытых UDP-портах (TURN по TLS на 443) – проверяется на стенде в спринтах 3–5.
