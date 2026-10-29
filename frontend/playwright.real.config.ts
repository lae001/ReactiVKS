import { defineConfig } from '@playwright/test';

// Вход, лобби и комната против НАСТОЯЩИХ auth-service (8001), meeting-service (8002) и LiveKit с вебхуками
// (VITE_API_MODE=http): один Chromium с фейковыми камерой и микрофоном, два контекста (организатор и гость).
// Сервисы поднимаются вручную (docs/testing/sprint4-frontend-status.md); Vite поднимает сам Playwright.
export default defineConfig({
  testDir: './e2e',
  testMatch: '*.real.ts',
  workers: 1,
  fullyParallel: false,
  reporter: 'list',
  timeout: 90_000,
  use: {
    baseURL: 'http://localhost:5173',
    launchOptions: {
      args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
    },
    trace: 'retain-on-failure',
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
