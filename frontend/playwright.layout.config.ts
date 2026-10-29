import { defineConfig } from '@playwright/test';

// Раскладка комнаты в режиме mock: у страницы нет прокрутки ни по одной оси на любой ширине окна.
// Бэкенд и LiveKit не нужны: auth-service подменяется в тесте. Свой Vite на порту 5290, чтобы не мешать `pnpm dev`.
const PORT = 5290;

export default defineConfig({
  testDir: './e2e',
  testMatch: '*.layout.ts',
  workers: 1,
  reporter: 'list',
  timeout: 60_000,
  use: {
    baseURL: `http://localhost:${PORT}`,
    launchOptions: {
      args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
    },
    permissions: ['camera', 'microphone'],
    locale: 'ru-RU',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
  webServer: {
    command: `pnpm exec vite --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: false,
    timeout: 60_000,
    env: { VITE_API_MODE: 'mock' },
  },
});
