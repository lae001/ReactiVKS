import { defineConfig } from '@playwright/test';

// Дополнительный настоящий стенд. 5183 и его процессы не управляются этим конфигом.
export default defineConfig({
  testDir: './e2e',
  testMatch: 'sprint6-services.integration.ts',
  workers: 1,
  timeout: 90_000,
  reporter: [['list'], ['json', { outputFile: '/tmp/reactivks-sprint6/integration-results.json' }]],
  outputDir: '/tmp/reactivks-sprint6/integration-output',
  use: {
    baseURL: 'http://localhost:5184',
    trace: 'off',
    launchOptions: {
      args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
    },
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
  webServer: {
    command: 'pnpm dev --port 5184 --strictPort',
    url: 'http://localhost:5184',
    reuseExistingServer: true,
    env: { VITE_API_MODE: 'http', VITE_DEV_MEETING_API_TARGET: 'http://127.0.0.1:8013' },
  },
});
