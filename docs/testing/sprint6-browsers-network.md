# EMO-108 — браузеры и качество соединения

13 ноября 2026, macOS на Mac M3, 8 ГБ. Прогоны выполнены последовательно,
по одному браузеру, `workers: 1`. Memory pressure перед тяжёлыми запусками
проверялся, доля свободной памяти составляла примерно 30–46%.

## Браузерная матрица

| Фактически запущенный браузер | Сценарий | Результат |
|---|---|---|
| Playwright Chromium 156.0.8078.4 | История, серверное скачивание контрактных CSV/PDF, настройки/reload/создание, права и действия admin | 3/3, контрактные API |
| Playwright Chromium 156.0.8078.4 | Новые реальные сервисы, два контекста, виртуальные устройства, согласие и reload, no_consent snapshot, unavailable и медиапотоки | 1/1 после исправления EMO-110 |
| Google Chrome 157.0.8103.51, установленный `/Applications/Google Chrome.app` | Те же три контрактных сценария | 3/3 |
| Google Chrome 157.0.8103.51 | Новые реальные сервисы и двусторонние медиапотоки при unavailable | 1/1 |
| Firefox 157.0, сборка Playwright | Три контрактных сценария | 3/3 |
| Firefox 157.0, сборка Playwright | Реальный медиасценарий | 0/1: подключение ICE не установлено, подробности ниже |
| Safari 26.6.2, установленный | Доступность WebDriver | Сессия не создана: Allow remote automation выключено |
| Microsoft Edge | В `/Applications` и `~/Applications` отсутствует | Нужен ручной прогон на доступной машине |
| Яндекс Браузер | В `/Applications` и `~/Applications` отсутствует | Нужен ручной прогон на доступной машине |
| Playwright WebKit | В кеше Playwright отсутствует | Не запускался |

Версия каждого запущенного Playwright-браузера получена через `browser.version()`.
Firefox запущен из комплекта Playwright, проверка установленного приложения Firefox
с физическими устройствами остаётся ручной. Результаты Safari и WebKit учитываются
под собственными названиями.

Контрактные прогоны используют тестовые ответы HTTP, включая auth. Реальная
интеграция использует auth 8001, meeting 8013, realtime 8080, analytics 8003,
LiveKit 7890 и виртуальные устройства. Исключены трассы с токенами и паролями.

```sh
cd /Users/z.kirill/dev/ReactiVKS/frontend
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
pnpm exec playwright test -c playwright.sprint6.config.ts --project=chrome
pnpm exec playwright test -c playwright.sprint6.config.ts --project=firefox
# E2E_REAL_EMAIL и E2E_REAL_PASSWORD передаются окружением из приватного хранилища.
pnpm exec playwright test -c playwright.sprint6-services.config.ts --project=chrome
pnpm exec playwright test -c playwright.sprint6-services.config.ts --project=firefox
```

На этой машине `/tmp/reactivks-sprint6/run-browser.py` читает ранее созданную
тестовую учётную запись из приватного файла и передаёт её дочернему процессу.
Команды выполняются по очереди. Конфиги используют свой Vite 5184.

## Непройденная проверка Firefox и доступность Safari

Firefox 157.0 воспроизводит сбой при входе организатора: REST join отвечает 200,
LiveKit принимает сигнальную сессию, но RTCPeerConnection переходит в
`connectionState=failed`, `iceConnectionState=failed`, `signalingState=stable`.
В 15 последовательных снимках getStats нет candidate/candidate-pair. Через
примерно 15 секунд SDK завершает ожидание транспорта ошибкой. Первый расходящийся
этап — установка ICE-транспорта, до приёма RTP и декодирования. Ожидание теста
`connected` не ослаблено. Контрактные страницы в этом Firefox проходят 3/3.

Повтор с тестовым `media.peerconnection.ice.loopback=true` результата не изменил.
Этот pref предназначен Mozilla для автономных тестовых окружений
([исходный all.js](https://github.com/mozilla/gecko-dev/blob/master/modules/libpref/init/all.js)).
Причина между настройками локальной сети, сборкой Firefox и SDK пока не установлена;
это открытый воспроизведённый сбой, а не подтверждённая ошибка кода React.
Frontend и владелец стенда должны повторить тот же сценарий на разрешённом
внешнем LiveKit/TURN и установленном Firefox, сопоставить ICE-логи.
Обезличенное наблюдение сохранено в `sprint6-browsers-evidence.json` и журнале дефектов.

Safari 26.6.2: вызов WebDriver create session вернул `session not created`:
“You must enable 'Allow remote automation' in the Developer section of Safari Settings”.
Браузерный сценарий не выполнялся. Временный safaridriver завершён; настройки
пользовательского Safari не менялись. Для автоматического повторения владелец
машины включает Settings → Developer → Allow remote automation; альтернативой
остаётся ручной гостевой сценарий ниже.

## TURN

В локальной конфигурации LiveKit отсутствует секция TURN. Выбранные пары в
реальном Chrome-прогоне имеют `local=host`, `remote=host`, `protocol=udp`,
`state=succeeded` у обоих клиентов. Результат проверки relay остаётся открытым.
Сведения считывает `selectedIcePairs()` из `transport.selectedCandidatePairId`
в `getStats()`, затем из соответствующих local/remote candidate. IP-адреса
и ICE credentials в приложение к протоколу не включены.

Владелец зависимости — backend/deploy. Нужны разрешённый стенд с TURN, TLS,
выдача ICE server credentials через LiveKit и две внешние клиентские сети.
Условие повтора — стенд доступен и владелец разрешил сетевой сценарий.

1. В временном Playwright-сценарии до `goto` установить обёртку RTCPeerConnection,
   передающую `iceTransportPolicy: 'relay'` в constructor и `setConfiguration`.
   Список iceServers сохраняется из конфигурации LiveKit.
2. Выполнить UC-3 в двух контекстах. Считать выбранные пары через `selectedIcePairs`.
3. Требовать непустой список выбранных пар и local candidate type `relay`
   для транспорта реально принимающего/публикующего медиа.
4. Сохранить новые кадры видимого remote video, рост decoded и аудиобайтов,
   двусторонний чат, значения RTT и используемый relay protocol.
5. Повторить с UDP TURN и TLS TURN, если оба предусмотрены стендом.

Политика relay ограничивает кандидаты ретрансляцией. Успех проверяется по выбранной
паре и медиапотоку. Основание — [спецификация WebRTC W3C](https://www.w3.org/TR/webrtc/#dom-rtcicetransportpolicy-relay).

## Ограниченный канал

Сетевое ограничение в текущем прогоне не включалось, измеренного эффекта нет.
Владелец зависимости — backend/deploy или владелец выделенной тестовой Linux-ВМ.
Нужны интерфейс, несущий UDP/TCP-медиа до LiveKit/TURN, и разрешение менять его qdisc.
HTTP throttling страницы не подтверждает этот критерий.

На выделенной тестовой ВМ с исходящим WebRTC через `eth0` сохранить состояние
qdisc, затем применить ограничение. Имя интерфейса подтвердить маршрутом до
медиаадреса LiveKit/TURN. Команда `add` должна завершиться ошибкой, если на root
уже задан пользовательский qdisc — в таком случае профиль согласуется с владельцем.

```sh
NETEM_DEVICE=eth0
ip route get <медиа-IP-LiveKit-или-TURN>
tc -s qdisc show dev "$NETEM_DEVICE"
sudo tc qdisc add dev "$NETEM_DEVICE" root handle 10: netem rate 1mbit delay 100ms 20ms loss 1%
tc -s qdisc show dev "$NETEM_DEVICE"
# После измерений удалить созданный в этом сценарии root qdisc.
sudo tc qdisc del dev "$NETEM_DEVICE" root handle 10:
```

Профиль задаёт исходящее ограничение 1 Мбит/с, задержку 100 мс с вариацией 20 мс
и потери 1%. Для обоих направлений использовать два интерфейса выделенного
тестового маршрутизатора или два согласованных ограничения egress. Команды
основаны на [руководстве tc-netem](https://man7.org/linux/man-pages/man8/tc-netem.8.html).

До ограничения записать 60 с baseline. Затем измерять 60 с под ограничением
и 30 с восстановления. Каждые 5 с сохранять RTP bytesSent/Received, framesDecoded,
framesPerSecond, packetsLost, jitter, RTT выбранной пары и availableOutgoingBitrate,
если браузер его отдаёт. Битрейт рассчитывать как `8 × Δbytes / Δtime`.
Рост счётчиков qdisc вместе с изменением медиастатистики подтверждает, что
ограничение затронуло WebRTC. Дополнительно проверить отзыв согласия, чат и
сохранение соединения, записать наблюдаемые зависания и качество звука.

## Остаток ручного прогона

Для Edge и Яндекс Браузера пройти дополнительные шаги из `sprint6-pmi-frontend.md`
с паспортом версии и устройств. Для Safari проверить гостевой вход, выбор устройств,
переключения, reload, чат и завершение. Отметки вручную проставляются после выполнения.
Нагрузку 5×10 проводит команда в EMO-96/103 на отдельном стенде.
