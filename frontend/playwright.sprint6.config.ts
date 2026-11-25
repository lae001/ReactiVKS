import { defineConfig } from '@playwright/test';

// Контрактные HTTP-сценарии без изменения пользовательского стенда :5183.
// Каждый проект запускается отдельно: --project=chromium, --project=chrome, --project=firefox.
export default defineConfig({
  testDir: './e2e',
  testMatch: 'sprint6.contract.ts',
  workers: 1,
  fullyParallel: false,
  timeout: 60_000,
  reporter: [['list']],
  outputDir: '/tmp/reactivks-sprint6/playwright',
  use: { baseURL: 'http://localhost:5184', trace: 'off', viewport: { width: 1440, height: 900 } },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'chrome', use: { browserName: 'chromium', channel: 'chrome' } },
    { name: 'firefox', use: { browserName: 'firefox' } },
  ],
  webServer: {
    command: 'pnpm dev --port 5184 --strictPort',
    url: 'http://localhost:5184',
    reuseExistingServer: true,
    env: { VITE_API_MODE: 'http', VITE_DEV_MEETING_API_TARGET: 'http://127.0.0.1:8013' },
  },
});
