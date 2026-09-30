# ReactiVKS – клиентская часть

SPA на React 19 + TypeScript + Vite ([ADR-006](../docs/adr/ADR-006-frontend-stack.md)).
Устройство и маршруты – [docs/frontend](../docs/frontend/README.md).

## Требования

- Node.js 22 LTS
- pnpm 9 (`corepack enable` или `npm i -g pnpm@9`)

## Команды

| Команда                             | Что делает                                                                    |
| ----------------------------------- | ----------------------------------------------------------------------------- |
| `pnpm install`                      | Установка зависимостей                                                        |
| `pnpm dev`                          | Dev-сервер на http://localhost:5173 (прокси `/api`, `/ws` → `localhost:8080`) |
| `pnpm build`                        | Проверка типов + production-сборка в `dist/`                                  |
| `pnpm lint`                         | ESLint                                                                        |
| `pnpm format` / `pnpm format:check` | Prettier (с сортировкой классов Tailwind)                                     |
| `pnpm typecheck`                    | `tsc -b` в строгом режиме                                                     |
| `pnpm test`                         | Vitest + Testing Library                                                      |

## Структура

```text
src/
├── app/            # App, маршруты, раскладки (layouts), глобальные стили и токены
├── pages/          # страницы (по одной на маршрут); dev/ – служебные страницы
├── features/       # auth, meetings, lobby, room, emotions, reports, admin (с спринта 2)
├── shared/
│   ├── ui/         # компоненты shadcn/ui и общие элементы (Wordmark, PageStub)
│   ├── config/     # пути, классы эмоций
│   └── lib/        # утилиты (cn, проверка поддержки WebRTC)
└── test/           # настройка Vitest
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
