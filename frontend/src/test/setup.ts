import '@testing-library/jest-dom/vitest';

import { resetSession } from '@/shared/api/session';

import { server } from './server';

// Node-овский fetch не принимает относительные адреса, а приложение ходит на /api/... (один origin).
const nativeFetch = globalThis.fetch.bind(globalThis);
globalThis.fetch = (input, init) =>
  typeof input === 'string' && input.startsWith('/')
    ? nativeFetch(new URL(input, window.location.href), init)
    : nativeFetch(input, init);

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }));
afterEach(() => {
  server.resetHandlers();
  resetSession();
  localStorage.clear();
  sessionStorage.clear();
});
afterAll(() => server.close());
