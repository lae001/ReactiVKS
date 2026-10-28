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

1. Запустить LiveKit в режиме разработки (команда и установка – в [frontend/README.md](../../frontend/README.md),
   раздел «LiveKit для разработки и e2e»): `livekit-server --dev` (ключи режима: `devkey` / `secret`, порт 7880).
2. Выпустить два токена с разными `identity`:
   `lk token create --api-key devkey --api-secret secret --join --room test --identity u1`
   (и так же для `u2`).
3. `pnpm dev`, открыть `http://localhost:5173/dev/livekit` в двух вкладках, указать адрес
   `ws://localhost:7880` и токен.
4. Должно появиться видео обеих вкладок. Камера нужна разрешённая; для проверки без камеры в Chrome есть флаги
   `--use-fake-device-for-media-stream --use-fake-ui-for-media-stream`.

**Версии, на которых проверено (EMO-53):** `livekit-server` 1.13.9 и `lk` (livekit-cli) 2.19.0, установлены через
Homebrew (`brew install livekit livekit-cli`). **В `deploy/` образ LiveKit нужно брать с тем же тегом** (`livekit/livekit-server:v1.13.9`),
чтобы поведение разработки и стенда совпадало; при обновлении меняются обе версии сразу.

Прототип видеовстречи (EMO-53): страница `/dev/livekit` показывает галерею `features/room/LiveKitGallery.tsx` –
`GridLayout` по списку дорожек, число плиток не задано; на странице помещается до 12 плиток, остальные уходят на
следующие (кнопки «Предыдущая/Следующая страница» собраны на `usePagination`: готового `PaginationControl` в
`@livekit/components-react` 2.9.24 нет). Размер страницы 12 взят с запасом к лимиту комнаты в 10 человек по уставу; пагинация – на случай роста лимита. Включены `adaptiveStream` и `dynacast`. Токены пока выпускаются вручную или
вспомогательным кодом e2e (`frontend/e2e/livekit-token.ts`, пакет `livekit-server-sdk` – devDependency только для
тестов); в рабочем сценарии токен выдает meeting-service.

Статус проверки (EMO-53, EMO-54):

- Страница собирается, проходят типизация, линтер и модульные тесты. Пагинация галереи на 13 и 25 участниках
  проверена модульным тестом на подменённых дорожках (`LiveKitGallery.test.tsx`), без браузера и сервера.
- e2e `frontend/e2e/livekit.lk.ts` (два контекста Chromium, `livekit-server --dev`) проверяет видео (`videoWidth > 0`)
  и входящий звук (`inbound-rtp` audio, рост `bytesReceived` через `getStats`). Запуск 2026-10-28
  (Chromium headless shell 156, `livekit-server` 1.13.9 `--dev`, один воркер): оба теста, этот и
  `livekit-smoke` (галерея на 10 участников), прошли.
- Не проверено: реальные устройства и Safari/Firefox, закрытые UDP-порты (см. раздел 5).

## 5. Открытые вопросы (спринты 2–3)

- Выдача токена участнику и гостю по ссылке `/j/:inviteCode` – по контракту meeting-service
  ([livekit-integration.md](../api/livekit-integration.md)).
- Safari 17+: проверить simulcast и выбор устройства вывода звука.
- Поведение при закрытых UDP-портах (TURN по TLS на 443) – проверяется на стенде в спринтах 3–5.
