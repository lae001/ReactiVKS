import { defineConfig } from '@playwright/test';

// Проверка лобби в настоящем Chromium с фейковыми камерой и микрофоном. Один браузер (workers: 1),
// бэкенд не нужен: слой API работает в режиме mock, а auth-service подменяется в самом тесте.
export default defineConfig({
  testDir: './e2e',
  testMatch: '*.lobby.ts',
  workers: 1,
  fullyParallel: false,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    launchOptions: {
      args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
    },
    permissions: ['camera', 'microphone'],
    locale: 'ru-RU',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 60_000,
    env: { VITE_API_MODE: 'mock' },
  },
});
