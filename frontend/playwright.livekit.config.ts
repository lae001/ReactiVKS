import { defineConfig } from '@playwright/test';

// Проверки видеовстречи через LiveKit (EMO-53): `pnpm test:e2e:livekit`. Нужен `livekit-server --dev`
// (README). Только Chromium с фейковой камерой, один воркер: рассчитано на слабую машину.
export default defineConfig({
  testDir: './e2e',
  testMatch: '*.lk.ts',
  workers: 1,
  fullyParallel: false,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    launchOptions: {
      args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
    },
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
