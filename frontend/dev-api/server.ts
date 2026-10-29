import { createServer } from 'node:http';

import { createApp } from './app.ts';
import { createLiveKitGateway } from './livekit.ts';

// ВРЕМЕННЫЙ dev-сервер вместо meeting-service. Только localhost, без проверки JWT (dev-api/README.md).
const HOST = '127.0.0.1';
const PORT = Number(process.env.DEV_API_PORT ?? 8002);

const gateway = createLiveKitGateway();
const app = createApp({
  gateway,
  origin: process.env.DEV_API_ORIGIN ?? 'http://localhost:5173',
});

const server = createServer((req, res) => void app.handle(req, res));
server.listen(PORT, HOST, () => {
  console.warn(`dev-api: http://${HOST}:${PORT} (LiveKit ${gateway.url}), данные в памяти`);
});

for (const signal of ['SIGINT', 'SIGTERM'] as const) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
