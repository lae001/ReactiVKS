import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e',
  testMatch: 'backend-sprint6.integration.ts',
  workers: 1,
  timeout: 180_000,
  reporter: [['list'], ['json', { outputFile: '/tmp/reactivks-s6/browser-results.json' }]],
  outputDir: '/tmp/reactivks-s6/browser-output',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
    permissions: ['camera', 'microphone'],
    launchOptions: {
      args: [
        '--use-fake-device-for-media-stream',
        '--use-fake-ui-for-media-stream',
        ...(process.env.E2E_VIDEO
          ? [`--use-file-for-fake-video-capture=${process.env.E2E_VIDEO}`]
          : []),
      ],
    },
  },
});
