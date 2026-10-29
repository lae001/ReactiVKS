import { apiFetch } from '@/shared/api/client';
import { resolveApiMode } from '@/shared/api/meetings';
import type { components } from '@/shared/api/schema';
import { clearSession, setSession } from '@/shared/api/session';
import type { User } from '@/shared/api/types';

type Schemas = components['schemas'];

export type LoginRequest = Schemas['LoginRequest'];
export type RegisterRequest = Schemas['RegisterRequest'];
export type AuthConfig = Schemas['AuthConfigResponse'];

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

/** POST /auth/login: токен – в сессию (память), refresh-токен сервер кладет в cookie. */
export async function login(body: LoginRequest): Promise<User> {
  const tokens = await apiFetch<Schemas['TokenResponse']>('/api/v1/auth/login', {
    method: 'POST',
    body,
    auth: false,
  });
  setSession(tokens);
  return tokens.user;
}

/** POST /auth/register не выдает токены, поэтому после него нужен вход (делает AuthProvider). */
export function register(body: RegisterRequest): Promise<User> {
  return apiFetch<User>('/api/v1/auth/register', { method: 'POST', body, auth: false });
}

/** Выход: состояние очищается, даже если сервер не ответил (сессию на устройстве все равно забываем). */
export async function logout(): Promise<void> {
  try {
    await apiFetch('/api/v1/auth/logout', { method: 'POST', auth: false });
  } finally {
    clearSession();
  }
}

export function fetchAuthConfig(): Promise<AuthConfig> {
  return apiFetch<AuthConfig>('/api/v1/auth/config', { auth: false });
}

export function fetchProfile(): Promise<User> {
  return apiFetch<User>('/api/v1/users/me');
}

export function updateProfile(body: Schemas['RenameRequest']): Promise<User> {
  return apiFetch<User>('/api/v1/users/me', { method: 'PATCH', body });
}

/**
 * Смена пароля. В режиме `http` – POST /users/me/password (204; сервер завершает все сессии
 * пользователя; 401 `invalid_credentials` – неверный текущий пароль). В режиме `mock` пароль не
 * меняется: форма и проверки настоящие. Режим читается при вызове, а не при загрузке модуля.
 */
export async function changePassword(body: ChangePasswordRequest): Promise<void> {
  if (resolveApiMode(import.meta.env.VITE_API_MODE) === 'http') {
    await apiFetch('/api/v1/users/me/password', { method: 'POST', body });
    return;
  }
  await new Promise((resolve) => setTimeout(resolve, 400));
}
