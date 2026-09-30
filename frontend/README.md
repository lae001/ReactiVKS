# ReactiVKS — frontend

React 19 + TypeScript (strict) + Vite, Tailwind CSS 4 + shadcn/ui, React Router. Подробности — [docs/frontend](../docs/frontend/README.md).

## Запуск (macOS, Apple Silicon)
```bash
brew install node@22 pnpm      # или: corepack enable
cd frontend
cp .env.example .env
pnpm install
pnpm dev                       # http://localhost:5173
```

## Команды
| Команда | Действие |
|---|---|
| `pnpm dev` | dev-сервер |
| `pnpm build` | проверка типов и сборка в `dist/` |
| `pnpm lint` / `pnpm format:check` | ESLint / Prettier |
| `pnpm typecheck` | `tsc` |
| `pnpm test` | Vitest + Testing Library |

Дополнительно: [UI-кит](docs/ui-kit.md) · [заметки по WebRTC и LiveKit](docs/webrtc-livekit-notes.md).
