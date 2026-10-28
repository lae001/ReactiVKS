# ReactiVKS – клиентская часть

SPA на React 19 + TypeScript + Vite ([ADR-006](../docs/adr/ADR-006-frontend-stack.md)).
Устройство и маршруты – [docs/frontend](../docs/frontend/README.md).

## Требования

- Node.js 22 LTS
- pnpm 9 (`corepack enable` или `npm i -g pnpm@9`)

## Команды

| Команда                             | Что делает                                                                                   |
| ----------------------------------- | -------------------------------------------------------------------------------------------- |
| `pnpm install`                      | Установка зависимостей                                                                       |
| `pnpm dev`                          | Dev-сервер на http://localhost:5173 (прокси `/api` → auth-service, `/ws` → `localhost:8080`) |
| `pnpm gen:api`                      | Типы API из OpenAPI запущенного сервиса → `src/shared/api/schema.d.ts`                       |
| `pnpm build`                        | Проверка типов + production-сборка в `dist/`                                                 |
| `pnpm lint`                         | ESLint                                                                                       |
| `pnpm format` / `pnpm format:check` | Prettier (с сортировкой классов Tailwind)                                                    |
| `pnpm typecheck`                    | `tsc -b` в строгом режиме                                                                    |
| `pnpm test`                         | Vitest + Testing Library                                                                     |
| `pnpm mockups`                      | Скриншоты экранов в `docs/frontend/mockups/` ([mockups.md](../docs/frontend/mockups.md))     |
| `pnpm test:e2e`                     | Живая проверка входа против запущенного auth-service (Playwright)                            |

## LiveKit для разработки и e2e

Прототип видеовстречи (`/dev/livekit`) и проверки `pnpm test:e2e:livekit` требуют локального сервера LiveKit.
Установка (версии – в [webrtc-livekit-notes.md](../docs/frontend/webrtc-livekit-notes.md)):

```bash
brew install livekit livekit-cli
livekit-server --dev --bind 127.0.0.1   # ws://localhost:7880, ключи devkey / secret; остановить – Ctrl-C
pnpm test:e2e:livekit                    # два участника видят друг друга (Chromium, фейковая камера)
LK_SMOKE_PUBLISHERS=9 pnpm test:e2e:livekit e2e/livekit-smoke.lk.ts   # раскладка на 10 участниках через lk load-test
```

> **Осторожно.** `livekit-server --dev` использует общеизвестные ключи `devkey` и `secret` и слушает TCP-порт 7881 на
> всех интерфейсах (`--bind 127.0.0.1` ограничивает только 7880). Не оставляйте его запущенным в публичных сетях.

Токены в тестах подписывает `e2e/livekit-token.ts` (`livekit-server-sdk`, devDependency только для e2e).

## Структура

```text
src/
├── app/            # App, маршруты, раскладки (layouts), глобальные стили и токены
├── pages/          # страницы (по одной на маршрут); dev/ – служебные страницы
├── features/       # auth, meetings, lobby, room, emotions, reports, admin (с спринта 2)
├── shared/
│   ├── api/        # fetch-клиент, сессия (Zustand), типы OpenAPI
│   ├── ui/         # компоненты shadcn/ui и общие элементы (Wordmark, PageStub)
│   ├── config/     # пути, классы эмоций
│   └── lib/        # утилиты (cn, проверка поддержки WebRTC)
└── test/           # настройка Vitest, мок сети (MSW), renderApp
```

Импорт из `src` – через псевдоним `@/`. Компоненты shadcn/ui добавляются командой
`pnpm dlx shadcn@latest add <компонент>` (настройки – `components.json`), затем правятся под токены проекта.

## Служебные страницы (только в `pnpm dev`)

| Путь           | Назначение                                                                                                               |
| -------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `/dev/ui`      | UI-кит: палитра, эмоции, типографика, компоненты ([ui-kit.md](../docs/frontend/ui-kit.md))                               |
| `/dev/livekit` | Песочница LiveKit: подключение к комнате по токену ([webrtc-livekit-notes.md](../docs/frontend/webrtc-livekit-notes.md)) |

## Переменные окружения

См. `.env.example`. Все переменные клиента начинаются с `VITE_` и попадают в сборку – секреты в них не хранятся.

### Подключение к бэкенду в dev

`pnpm dev` проксирует `/api` на адрес из `VITE_DEV_API_TARGET` (по умолчанию `http://127.0.0.1:8001` – локальный
auth-service, запуск описан в `backend/services/auth_service`). Браузер видит один origin
(`http://localhost:5173`), поэтому работает cookie `vks_refresh` (`HttpOnly; Secure; SameSite=Strict;
Path=/api/v1/auth`): Chromium и Firefox принимают `Secure`-cookie на `localhost` и по `http`. Сменить адрес:

```bash
VITE_DEV_API_TARGET=http://127.0.0.1:9000 pnpm dev
```

Типы API перегенерируются командой `pnpm gen:api` при запущенном сервисе (адрес берется из той же переменной);
сгенерированный файл коммитится. Тесты ходят не в сеть, а в мок на MSW (`src/test/`).
