# dev-api: временный сервер вместо meeting-service

> **Временный инструмент. Без проверки JWT, только localhost.** Не запускайте его в общей сети и не
> выставляйте наружу. Удаляется целиком (`frontend/dev-api`, скрипт `dev:api`, правило прокси в
> `vite.config.ts`, `VITE_DEV_MEETING_API_TARGET`), когда появится настоящий meeting-service.

meeting-service еще не написан, а комнате нужны настоящие токены LiveKit. dev-api реализует по
[контракту](../../docs/api/rest-api.md) (раздел 3) подмножество, которое использует слой API фронтенда
(`src/shared/api/meetings`, режим `VITE_API_MODE=http`). Данные хранятся в памяти и пропадают при
перезапуске. Новых зависимостей нет: Node `http` и `livekit-server-sdk` (он уже есть для e2e).

## Запуск

```bash
livekit-server --dev --bind 127.0.0.1     # ключи devkey / secret, ws://127.0.0.1:7880
pnpm dev:api                              # слушает ТОЛЬКО 127.0.0.1:8002
VITE_API_MODE=http pnpm dev               # SPA; прокси Vite: meetings, join, participants, settings → 8002
```

Нужен Node с отключением типов «из коробки» (22.18+). auth-service (порт 8001) нужен для входа
организатора, как и раньше; пути `/api/v1/auth/*` по-прежнему идут на него.

Переменные окружения dev-api: `DEV_API_PORT` (8002), `LIVEKIT_URL` (`ws://127.0.0.1:7880`),
`DEV_API_ORIGIN` (`http://localhost:5173`, для `invite_url`). Адрес для прокси Vite –
`VITE_DEV_MEETING_API_TARGET`.

## Что реализовано

| Метод и путь                                 | Примечания                                                                                                                          |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `POST`, `GET /meetings`                      | `Idempotency-Key`, `status` через запятую, `q`, `from`, `to`, `limit`, курсор `o:<n>`                                               |
| `GET`, `PATCH`, `DELETE /meetings/{id}`      | `meeting_not_editable` для параметров начатой встречи                                                                               |
| `POST /meetings/{id}/join`                   | Первый вход активирует встречу, создает комнату LiveKit (`max_participants = 11`)                                                   |
| `POST /meetings/{id}/end`                    | Идемпотентно, комната удаляется                                                                                                     |
| `GET /meetings/{id}/participants`            | Состав из REST, `online` – по данным LiveKit                                                                                        |
| `POST …/participants/{pid}/mute`, `…/remove` | Через `RoomServiceClient`                                                                                                           |
| `GET`, `POST /join/{code}`                   | `meeting_not_started`, `meeting_ended`, `meeting_full` (10), `consent_required`, `notice_outdated` (версия уведомления только `v1`) |
| `PUT /participants/me/consent`               | Обновляет атрибут `vks.consent` в LiveKit; `202`, если участника нет в комнате                                                      |
| `POST /participants/me/rejoin`               | Новый токен LiveKit                                                                                                                 |
| `GET`, `PUT /settings`                       |                                                                                                                                     |

Не реализовано: `/admin/*`, `/internal/*`, вебхуки LiveKit, агент `emotion-agent`, отмена встречи
(`cancelled`), лимиты запросов (`429`).

## Токены LiveKit

Подписываются ключами `devkey` / `secret` по
[livekit-integration.md](../../docs/api/livekit-integration.md): `identity = p_<id участника>`, `name`,
комната = id встречи, `canUpdateOwnMetadata = false`, источники камера, микрофон и демонстрация экрана,
атрибуты `vks.role`, `vks.consent`, `vks.kind = human`. Срок действия 6 часов.

## Допущения (вместо проверки JWT)

- Организатором считается любой запрос с заголовком `Authorization: Bearer …`; подпись не проверяется.
  Имя берется из claim `name` токена (иначе «Организатор»). Владелец у всех встреч один.
- Гость определяется по `Authorization: Participant pt_…`, токены хранятся в памяти.
- Запросы с чужим именем хоста (не `127.0.0.1` и не `localhost`) отклоняются с `403`.
- Вебхуков LiveKit нет, поэтому «в комнате» считается так: участник онлайн, если он есть в
  `ListParticipants` LiveKit, либо вошел по REST меньше минуты назад и еще не подключался. Так комната
  не «забивается» вышедшими и гостями, которые не дошли до LiveKit.
- Встреча «сейчас» создается в `scheduled`, статус `active` – после входа организатора.

## Тесты

`pnpm vitest run dev-api` – REST-часть на подмене LiveKit (`app.test.ts`), без сети и без LiveKit.
Реальный LiveKit через dev-api не проверялся автоматически.
