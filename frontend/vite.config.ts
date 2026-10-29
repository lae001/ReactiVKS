/// <reference types="vitest/config" />
import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

// Конфигурация сборки SPA (ADR-006). В проде статику раздает Nginx,
// API и WebSocket проксируются им же; в dev – прокси Vite на локальные сервисы.
export default defineConfig(({ mode }) => {
  // Адрес бэкенда для dev-прокси; по умолчанию – локальный auth-service (backend/services/auth_service)
  const apiTarget =
    loadEnv(mode, import.meta.dirname, 'VITE_').VITE_DEV_API_TARGET || 'http://127.0.0.1:8001';
  // meeting-service (make run-meeting, порт 8002); при нехватке ресурсов – облегченный dev-api (dev-api/README.md)
  const meetingTarget =
    loadEnv(mode, import.meta.dirname, 'VITE_').VITE_DEV_MEETING_API_TARGET ||
    'http://127.0.0.1:8002';
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { '@': path.resolve(import.meta.dirname, './src') },
    },
    server: {
      port: 5173,
      proxy: {
        // Пути meeting-service (8002), включая /admin/meetings и /admin/health; остальное /api – auth-service
        // (8001): /auth, /users, /admin/users. Правило с регулярным выражением стоит выше общего '/api':
        // Vite берет первое совпадение, поэтому /admin/meetings не попадает на общий /admin
        '^/api/v1/(meetings|join|participants|settings|admin/(meetings|health))': {
          target: meetingTarget,
          changeOrigin: true,
        },
        // Один origin для SPA и API: так работает cookie vks_refresh (SameSite=Strict, Path=/api/v1/auth)
        '/api': { target: apiTarget, changeOrigin: true },
        '/ws': { target: 'ws://localhost:8080', ws: true },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      css: false,
    },
  };
});
