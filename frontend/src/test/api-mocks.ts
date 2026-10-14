import { HttpResponse, http } from 'msw';

import type { User } from '@/shared/api/types';

import { server } from './server';

export const organizer: User = {
  id: '0192a000-0000-7000-8000-000000000001',
  email: 'ivan@example.ru',
  display_name: 'Иван Петров',
  role: 'organizer',
};
export const admin: User = {
  ...organizer,
  id: '0192a000-0000-7000-8000-000000000002',
  role: 'admin',
};

export function tokenResponse(user: User = organizer, accessToken = 'access-1', expiresIn = 900) {
  return { access_token: accessToken, token_type: 'Bearer' as const, expires_in: expiresIn, user };
}

/** Ответ application/problem+json, как у сервера. */
export function problem(
  status: number,
  code: string,
  extra: { errors?: unknown[]; headers?: Record<string, string> } = {},
) {
  return HttpResponse.json(
    {
      type: `https://vks.example.ru/errors/${code}`,
      title: code,
      status,
      detail: `detail: ${code}`,
      code,
      request_id: 'req-123',
      errors: extra.errors ?? null,
    },
    { status, headers: { 'Content-Type': 'application/problem+json', ...extra.headers } },
  );
}

export const validationIssue = (field: string) => ({
  loc: ['body', field],
  msg: 'invalid',
  type: 'value_error',
});

/** Сессия есть: refresh отвечает пользователем. Возвращает журнал вызовов refresh. */
export function mockSession(user: User = organizer) {
  const calls = { refresh: 0, logout: 0 };
  server.use(
    http.post('/api/v1/auth/refresh', () => {
      calls.refresh += 1;
      return HttpResponse.json(tokenResponse(user, `access-${calls.refresh + 1}`));
    }),
    http.post('/api/v1/auth/logout', () => {
      calls.logout += 1;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return calls;
}

/** Сессии нет: refresh отвечает 401. */
export function mockNoSession() {
  server.use(http.post('/api/v1/auth/refresh', () => problem(401, 'unauthorized')));
}

export function mockAuthConfig(registrationEnabled = true) {
  server.use(
    http.get('/api/v1/auth/config', () =>
      HttpResponse.json({
        registration_enabled: registrationEnabled,
        password_reset_enabled: false,
      }),
    ),
  );
}
