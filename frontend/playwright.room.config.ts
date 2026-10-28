import { defineConfig } from '@playwright/test';

// Комната и вход через dev-api (режим VITE_API_MODE=http): один Chromium с фейковыми камерой и микрофоном,
// два контекста внутри теста (организатор и гость). Нужны livekit-server --dev и pnpm dev:api; Vite поднимает
// сам Playwright. auth-service не нужен: /api/v1/auth/* подменяется в тесте (page.route).
export default defineConfig({
  testDir: './e2e',
  testMatch: '*.room.ts',
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
