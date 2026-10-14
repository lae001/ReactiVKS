import { setupServer } from 'msw/node';

/** Мок сети для тестов: обработчики добавляются в тесте через server.use(...). */
export const server = setupServer();
