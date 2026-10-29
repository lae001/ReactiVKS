import { defineConfig } from '@playwright/test';

// Живые снимки комнаты для docs/frontend/mockups.md: настоящая комната на LiveKit в режиме
// VITE_API_MODE=http, фейковая камера Chromium. Нужны livekit-server --dev и pnpm dev:api;
// Vite поднимает сам Playwright. Один Chromium, auth-service подменяется в скрипте.
export default defineConfig({
  testDir: './e2e',
  testMatch: 'room-live.shots.ts',
  workers: 1,
  fullyParallel: false,
  reporter: 'list',
  timeout: 90_000,
  use: {
    baseURL: 'http://localhost:5173',
    launchOptions: {
      args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
    },
    locale: 'ru-RU',
    timezoneId: 'Europe/Moscow',
    colorScheme: 'light',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:5173',
    reuseExistingServer: false,
    timeout: 60_000,
    env: { VITE_API_MODE: 'http' },
  },
});
