import { defineConfig } from '@playwright/test';

// Живая проверка против запущенного бэкенда (VITE_DEV_API_TARGET, по умолчанию auth-service на :8001).
// Браузеры гоняются по одному (workers: 1): проверка рассчитана на слабую машину.
export default defineConfig({
  testDir: './e2e',
  testMatch: '*.e2e.ts',
  workers: 1,
  fullyParallel: false,
  reporter: 'list',
  use: { baseURL: 'http://localhost:5173', trace: 'retain-on-failure' },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'firefox', use: { browserName: 'firefox' } },
  ],
  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
