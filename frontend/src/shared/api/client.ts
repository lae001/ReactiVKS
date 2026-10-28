import { ApiError, toApiError } from './problem';
import { refreshSession, useSessionStore } from './session';

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  /** Тело запроса, отправляется как JSON. */
  body?: unknown;
  /** false – запрос без Authorization и без повтора после refresh (сами вызовы /auth/*). */
  auth?: boolean;
  /** Дополнительные заголовки (Idempotency-Key, Authorization: Participant …). */
  headers?: Record<string, string>;
  /** Параметры строки запроса; undefined пропускаются. */
  query?: Record<string, string | number | undefined>;
  signal?: AbortSignal;
}

async function send(path: string, options: RequestOptions, token: string | null) {
  const headers = new Headers({ Accept: 'application/json, application/problem+json' });
  if (options.body !== undefined) headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  for (const [name, value] of Object.entries(options.headers ?? {})) headers.set(name, value);
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(options.query ?? {})) {
    if (value !== undefined && value !== '') search.set(name, String(value));
  }
  const url = search.size > 0 ? `${path}?${search}` : path;
  try {
    return await fetch(url, {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new ApiError({
      status: 0,
      code: 'network_error',
      message: cause instanceof Error ? cause.message : 'Сбой сети',
    });
  }
}

/**
 * Тонкая обертка над fetch для REST API (docs/api/rest-api.md): JSON, Bearer-токен из сессии,
 * разбор problem+json в ApiError. На 401 один раз обновляет сессию и повторяет запрос;
 * параллельные 401 делят одно обновление (см. refreshSession).
 */
export async function apiFetch<T = void>(path: string, options: RequestOptions = {}): Promise<T> {
  const useAuth = options.auth !== false;
  const sentToken = useAuth ? useSessionStore.getState().accessToken : null;
  let response = await send(path, options, sentToken);

  if (response.status === 401 && useAuth) {
    // Если токен уже сменили, пока запрос был в пути, обмен делать не нужно – хватит повтора
    const current = useSessionStore.getState().accessToken;
    const fresh = current !== sentToken && current ? current : await refreshSession();
    if (fresh) response = await send(path, options, fresh);
  }

  if (!response.ok) throw await toApiError(response);
  if (response.status === 204 || response.headers.get('Content-Length') === '0') {
    return undefined as T;
  }
  return (await response.json()) as T;
}
