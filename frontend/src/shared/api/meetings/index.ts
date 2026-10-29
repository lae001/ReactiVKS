import type { MeetingsApi } from './api';
import { createHttpMeetingsApi } from './http';
import { createMockMeetingsApi } from './mock';

export type { MeetingsApi } from './api';
export * from './types';

export type ApiMode = 'mock' | 'http';

/**
 * Режим слоя API по VITE_API_MODE: `mock` (по умолчанию, данные в памяти) или `http`
 * (настоящий meeting-service через /api/v1). Неизвестное значение – `mock`.
 */
export function resolveApiMode(value: string | undefined): ApiMode {
  return value === 'http' ? 'http' : 'mock';
}

export const API_MODE = resolveApiMode(import.meta.env.VITE_API_MODE);

const mock = createMockMeetingsApi();

/** Единственная точка доступа страниц к meeting-service. */
export const meetingsApi: MeetingsApi = API_MODE === 'http' ? createHttpMeetingsApi() : mock;

/** Сброс данных mock-режима (тесты). */
export function resetMockMeetings() {
  mock.reset();
}
