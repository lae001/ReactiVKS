# Заметки: WebRTC и LiveKit в браузере (EMO-17)

## WebRTC API браузера

- `navigator.mediaDevices.getUserMedia({ audio, video })` — доступ к камере и микрофону, только в защищённом контексте (HTTPS или `localhost`).
- `navigator.mediaDevices.enumerateDevices()` — список устройств; подписи (`label`) доступны только после выдачи разрешения.
- `RTCPeerConnection` — само соединение; сигнализацию, ICE и SFU в проекте берёт на себя LiveKit, напрямую API не используется.
- Перед входом в лобби проверяем наличие `RTCPeerConnection` и `getUserMedia` и показываем понятное сообщение (docs/frontend/README.md, «Поддержка браузеров»).

## livekit-client

- `Room` — центральный объект: `connect(url, token)`, события `RoomEvent.*`, участники, дорожки.
- Опции комнаты, которые нужны проекту: `adaptiveStream`, `dynacast`, simulcast (3 слоя для 720p).
- Атрибуты участника (`participant.attributes`): ML-агент помечается `vks.kind = agent` — по нему включаем индикатор «Идёт анализ эмоций» и исключаем агента из плиток.

## @livekit/components-react

- `<LiveKitRoom token serverUrl connect audio video>` — провайдер контекста комнаты.
- `<VideoConference />` — готовая раскладка (для спайка); в продукте собираем свою из `GridLayout`, `ParticipantTile`, `ControlBar`, `Chat`.
- `<RoomAudioRenderer />` — воспроизведение звука участников.
- Стили: `@livekit/components-styles` + атрибут `data-lk-theme="default"`, поверх — токены проекта.

## Пример подключения

`src/features/room/LiveKitConnectExample.tsx`. Для локальной проверки:

1. `livekit-server --dev` (ключи dev: `devkey` / `secret`);
2. `lk token create --api-key devkey --api-secret secret --join --room test --identity u1`;
3. передать токен в компонент, `VITE_LIVEKIT_URL=ws://localhost:7880`.

Компонент проверен на сборку и типы; подключение к реальному серверу в этом спринте вручную не проверялось.

## Открытые вопросы для спринтов 2–3

- Как гость получает токен (`/j/:inviteCode` → meeting-service) — см. docs/api/livekit-integration.md.
- Safari 17+: проверить simulcast и выбор устройств вывода.
