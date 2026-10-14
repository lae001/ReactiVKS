import { create } from 'zustand';

import { ApiError, toApiError } from './problem';
import type { components } from './schema';
import type { User } from './types';

export type TokenResponse = components['schemas']['TokenResponse'];

/**
 * unknown – при старте еще не выяснили, есть ли сессия (идет POST /auth/refresh);
 * unavailable – выяснить не удалось из-за сбоя сети или сервера.
 */
export type SessionStatus = 'unknown' | 'authenticated' | 'anonymous' | 'unavailable';

interface SessionState {
  status: SessionStatus;
  /** Access-токен живет только здесь, в памяти: ни localStorage, ни sessionStorage (docs/frontend/README.md). */
  accessToken: string | null;
  user: User | null;
}

/** Обновляем токен за столько секунд до конца срока. */
const REFRESH_LEEWAY_S = 60;
/** Но не чаще, чем раз в столько секунд, если срок выдан слишком коротким. */
const MIN_REFRESH_DELAY_S = 5;

export const useSessionStore = create<SessionState>(() => ({
  status: 'unknown',
  accessToken: null,
  user: null,
}));

let refreshTimer: ReturnType<typeof setTimeout> | undefined;
let inflightRefresh: Promise<string | null> | null = null;

function cancelScheduledRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = undefined;
}

/** Сохраняет выданную пару и планирует упреждающее обновление по expires_in. */
export function setSession(tokens: TokenResponse) {
  useSessionStore.setState({
    status: 'authenticated',
    accessToken: tokens.access_token,
    user: tokens.user,
  });
  cancelScheduledRefresh();
  const delayS = Math.max(tokens.expires_in - REFRESH_LEEWAY_S, MIN_REFRESH_DELAY_S);
  refreshTimer = setTimeout(() => {
    refreshSession().catch(() => {
      // сбой сети: следующий запрос получит 401 и обновит сессию сам
    });
  }, delayS * 1000);
}

/** Меняет профиль в уже открытой сессии (например, после PATCH /users/me). */
export function updateSessionUser(user: User) {
  useSessionStore.setState({ user });
}

export function clearSession(status: SessionStatus = 'anonymous') {
  cancelScheduledRefresh();
  useSessionStore.setState({ status, accessToken: null, user: null });
}

/** Для тестов: вернуть хранилище к состоянию «только что открыли страницу». */
export function resetSession() {
  inflightRefresh = null;
  clearSession('unknown');
}

/**
 * POST /auth/refresh по cookie vks_refresh. Параллельные вызовы делят один запрос
 * (single-flight): refresh-токен одноразовый, второй обмен тем же токеном отозвал бы сессию.
 * Возвращает новый access-токен или null, если сессии нет (401). Сбой сети и 5xx – исключение,
 * состояние сессии при этом не меняется.
 */
export function refreshSession(): Promise<string | null> {
  inflightRefresh ??= doRefresh().finally(() => {
    inflightRefresh = null;
  });
  return inflightRefresh;
}

async function doRefresh(): Promise<string | null> {
  let response: Response;
  try {
    response = await fetch('/api/v1/auth/refresh', { method: 'POST' });
  } catch (cause) {
    throw new ApiError({
      status: 0,
      code: 'network_error',
      message: cause instanceof Error ? cause.message : 'Сбой сети',
    });
  }
  if (response.status === 401) {
    clearSession();
    return null;
  }
  if (!response.ok) throw await toApiError(response);
  const tokens = (await response.json()) as TokenResponse;
  setSession(tokens);
  return tokens.access_token;
}

/** Стартовая проверка сессии: есть ли живая cookie. */
export async function restoreSession(): Promise<void> {
  try {
    await refreshSession();
  } catch {
    clearSession('unavailable');
  }
}
