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

**Нужен Node 22.18 или новее:** с этой версии Node сам убирает типы TypeScript без флагов, а `dev:api` запускает `node dev-api/server.ts` напрямую (поэтому в коде нет «свойств-параметров» конструктора и других конструкций, которым нужно преобразование; проверяет `erasableSyntaxOnly` в `tsconfig.node.json`). auth-service (порт 8001) нужен для входа
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

- Организатором считается запрос с `Authorization: Bearer <JWT>`; подпись не проверяется. Из токена берутся
  claims `sub` (id пользователя, он же владелец) и `name` (имя в галерее, иначе «Организатор»); токен без `sub`
  пользователя не определяет – `401`. Состав claims auth-service: `iss`, `aud`, `sub`, `role`, `name`, `iat`,
  `exp`, `jti`.
- **У каждой встречи свой владелец** (`sub` создателя, в ответы API не попадает). Маршруты организатора
  (список, карточка, изменение, удаление, `join`, `end`, участники, `mute`, `remove`, согласие организатора) работают
  только для владельца: чужая встреча даёт `404 not_found`, как в контракте («встречи нет или она чужая»); список
  показывает только свои встречи. Настройки анализа и ключи `Idempotency-Key` тоже у каждого пользователя свои.
  Организатор в LiveKit получает `identity = p_org-<id встречи>`, поэтому два аккаунта в разных встречах не
  выбивают друг друга. Гостевые маршруты (`/join/{код}`, `rejoin`, согласие гостя) владельца не требуют.
- Администратор (`role = admin`) чужие встречи тоже не видит: как и в настоящем сервисе, доступ только у владельца.
- Гость определяется по `Authorization: Participant pt_…`, токены хранятся в памяти.
- Запросы с чужим именем хоста (не `127.0.0.1` и не `localhost`) отклоняются с `403`.
- Вебхуков LiveKit нет, поэтому «в комнате» считается так: участник онлайн, если он есть в
  `ListParticipants` LiveKit, либо вошел по REST меньше минуты назад и еще не подключался. Так комната
  не «забивается» вышедшими и гостями, которые не дошли до LiveKit.
- Встреча «сейчас» создается в `scheduled`, статус `active` – после входа организатора.

## Статус проверки

Проверено 2026-10-28 (Node 26.10.0, livekit-server 1.13.9, `lk` 2.19.0, macOS). Запускались только
`livekit-server --dev --bind 127.0.0.1`, `pnpm dev:api` и `curl`; браузеры и Vite не запускались.

Проверено на живых процессах (`curl` + `RoomServiceClient` + `lk room join` как настоящий участник LiveKit):

- создание встречи (`scheduled`), `GET /join/{code}` с уведомлением `v1`;
- `meeting_not_started` до входа организатора; `consent_required` для организатора и для гостя;
  `notice_outdated` при версии `v0`;
- вход организатора: встреча стала `active`, в LiveKit создана комната (`max_participants = 11`);
- токены (организатора и гостя) проходят проверку подписью `devkey`/`secret`; в них `sub = p_<id>`, `name`,
  `canUpdateOwnMetadata = false`, источники публикации и атрибуты `vks.role`, `vks.consent`, `vks.kind`;
- гость подключен к комнате клиентом `lk` под identity `p_<id>`: `ListParticipants` показал его;
- `PUT /participants/me/consent` (`revoked`, затем `granted`): ответ `200 synced=true`, атрибут `vks.consent`
  в LiveKit действительно изменился оба раза;
- `mute` видео: трек в LiveKit стал `muted`; `mute` аудио без треков – `204`;
- `remove`: гость исчез из `ListParticipants` (клиент получил `PARTICIPANT_REMOVED`), в REST `is_removed`,
  повторный `rejoin` – `409 participant_removed`;
- `end`: `200 ended`, повтор идемпотентен, комната LiveKit удалена, вход гостя после этого – `meeting_ended`;
- 10 участников (организатор и 9 гостей) вошли, следующий получил `409 meeting_full`, в списке его нет;
- при остановленном LiveKit вход организатора – `503 livekit_unavailable`, встреча осталась `scheduled`;
- запрос с чужим `Host` – `403`;
- после остановки обоих процессов по PID порты 7880, 7881, 8002 свободны.

Найдено и исправлено по ходу: запрос согласия с токеном удаленного участника проходил (`202`) –
теперь `401`, как для недействительного токена (`rejoin` по-прежнему отвечает `participant_removed`).

**Не проверено:**

- `meeting_full` в LiveKit: в комнату подключались только 1–2 участника, одиннадцать настоящих клиентов
  не поднимались (проверка по данным REST и по модульным тестам);
- токен из ответа dev-api в настоящем клиенте (`lk room join` выписывает свой токен с теми же identity и
  атрибутами, а токены dev-api проверены только подписью и содержимым);
- публикация и прием аудио и видео между участниками через токены dev-api;
- прокси Vite и работа SPA в режиме `VITE_API_MODE=http`;
- освобождение мест вышедшими участниками на живом LiveKit (проверено только модульно, с подменой времени);
- `UpdateParticipant` для участника, которого нет в комнате (в живом прогоне такой случай дал `202`, но
  это единственная проверка);
- Node 22.18 (проверялась только Node 26).

## Тесты

`pnpm vitest run dev-api` – REST-часть на подмене LiveKit (`app.test.ts`), без сети и без LiveKit.
Реальный LiveKit через dev-api не проверялся автоматически.
