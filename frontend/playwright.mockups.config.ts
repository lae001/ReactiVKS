import { defineConfig } from '@playwright/test';

// Скриншоты экранов для docs/frontend/mockups.md. Только Chromium (фейковая камера для лобби и комнаты),
// бэкенд не нужен: ответы auth-service подменяются в самом тесте.
export default defineConfig({
  testDir: './e2e',
  testMatch: 'mockups.shots.ts',
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    launchOptions: {
      args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
    },
    permissions: ['camera', 'microphone'],
    locale: 'ru-RU',
    timezoneId: 'Europe/Moscow',
    colorScheme: 'light',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
