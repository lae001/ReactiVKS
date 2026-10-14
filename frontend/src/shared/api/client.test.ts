import { HttpResponse, http } from 'msw';

import {
  admin,
  mockNoSession,
  organizer,
  problem,
  tokenResponse,
  validationIssue,
} from '@/test/api-mocks';
import { server } from '@/test/server';

import { apiFetch } from './client';
import { ApiError } from './problem';
import {
  clearSession,
  refreshSession,
  restoreSession,
  setSession,
  useSessionStore,
} from './session';

function signIn(token = 'access-1', expiresIn = 900) {
  setSession(tokenResponse(organizer, token, expiresIn));
}

describe('apiFetch', () => {
  it('подставляет Bearer-токен из сессии', async () => {
    signIn('tok-A');
    let seen: string | null = null;
    server.use(
      http.get('/api/v1/users/me', ({ request }) => {
        seen = request.headers.get('Authorization');
        return HttpResponse.json(organizer);
      }),
    );
    await expect(apiFetch('/api/v1/users/me')).resolves.toEqual(organizer);
    expect(seen).toBe('Bearer tok-A');
  });

  it('разбирает problem+json: код, поля, request_id, Retry-After', async () => {
    server.use(
      http.post('/api/v1/auth/login', () =>
        problem(429, 'too_many_requests', {
          headers: { 'Retry-After': '45' },
          errors: [validationIssue('email')],
        }),
      ),
    );
    const error = await apiFetch('/api/v1/auth/login', {
      method: 'POST',
      body: {},
      auth: false,
    }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 429,
      code: 'too_many_requests',
      requestId: 'req-123',
      retryAfter: 45,
    });
    expect((error as ApiError).errors[0]?.loc).toEqual(['body', 'email']);
  });

  it('тело не JSON (ответ прокси) – unknown_error со статусом', async () => {
    server.use(
      http.get('/api/v1/users/me', () => new HttpResponse('Bad Gateway', { status: 502 })),
    );
    await expect(apiFetch('/api/v1/users/me')).rejects.toMatchObject({
      status: 502,
      code: 'unknown_error',
    });
  });

  it('сбой сети – network_error', async () => {
    server.use(http.get('/api/v1/users/me', () => HttpResponse.error()));
    await expect(apiFetch('/api/v1/users/me')).rejects.toMatchObject({ code: 'network_error' });
  });

  it('204 без тела возвращает undefined', async () => {
    server.use(http.post('/api/v1/x', () => new HttpResponse(null, { status: 204 })));
    await expect(apiFetch('/api/v1/x', { method: 'POST' })).resolves.toBeUndefined();
  });
});

describe('обновление сессии на 401', () => {
  it('один refresh и повтор запроса с новым токеном', async () => {
    signIn('old');
    const seen: (string | null)[] = [];
    let refreshes = 0;
    server.use(
      http.post('/api/v1/auth/refresh', () => {
        refreshes += 1;
        return HttpResponse.json(tokenResponse(organizer, 'new'));
      }),
      http.get('/api/v1/users/me', ({ request }) => {
        const header = request.headers.get('Authorization');
        seen.push(header);
        return header === 'Bearer new'
          ? HttpResponse.json(organizer)
          : problem(401, 'unauthorized');
      }),
    );
    await expect(apiFetch('/api/v1/users/me')).resolves.toEqual(organizer);
    expect(refreshes).toBe(1);
    expect(seen).toEqual(['Bearer old', 'Bearer new']);
    expect(useSessionStore.getState().accessToken).toBe('new');
  });

  it('гонка: параллельные 401 делят один refresh, все запросы повторяются', async () => {
    signIn('old');
    let refreshes = 0;
    server.use(
      http.post('/api/v1/auth/refresh', async () => {
        refreshes += 1;
        await new Promise((r) => setTimeout(r, 30));
        return HttpResponse.json(tokenResponse(organizer, 'new'));
      }),
      http.get('/api/v1/users/me', ({ request }) =>
        request.headers.get('Authorization') === 'Bearer new'
          ? HttpResponse.json(organizer)
          : problem(401, 'unauthorized'),
      ),
    );
    const results = await Promise.all([
      apiFetch('/api/v1/users/me'),
      apiFetch('/api/v1/users/me'),
      apiFetch('/api/v1/users/me'),
      apiFetch('/api/v1/users/me'),
    ]);
    expect(results).toHaveLength(4);
    expect(refreshes).toBe(1);
  });

  it('если токен уже обновили, пока запрос был в пути, новый refresh не делается', async () => {
    signIn('old');
    let refreshes = 0;
    server.use(
      http.post('/api/v1/auth/refresh', () => {
        refreshes += 1;
        return HttpResponse.json(tokenResponse(organizer, 'new'));
      }),
      http.get('/api/v1/slow', async ({ request }) => {
        if (request.headers.get('Authorization') === 'Bearer old') {
          await new Promise((r) => setTimeout(r, 50));
          return problem(401, 'unauthorized');
        }
        return HttpResponse.json({ ok: true });
      }),
    );
    const slow = apiFetch('/api/v1/slow');
    await refreshSession(); // другой запрос уже обновил токен
    await expect(slow).resolves.toEqual({ ok: true });
    expect(refreshes).toBe(1);
  });

  it('refresh вернул 401 – ошибка наружу, сессия очищена', async () => {
    signIn('old');
    mockNoSession();
    server.use(http.get('/api/v1/users/me', () => problem(401, 'unauthorized')));
    await expect(apiFetch('/api/v1/users/me')).rejects.toMatchObject({
      status: 401,
      code: 'unauthorized',
    });
    expect(useSessionStore.getState()).toMatchObject({ status: 'anonymous', accessToken: null });
  });

  it('повтор делается один раз: второй 401 не зацикливает запросы', async () => {
    signIn('old');
    let gets = 0;
    server.use(
      http.post('/api/v1/auth/refresh', () => HttpResponse.json(tokenResponse(organizer, 'new'))),
      http.get('/api/v1/users/me', () => {
        gets += 1;
        return problem(401, 'unauthorized');
      }),
    );
    await expect(apiFetch('/api/v1/users/me')).rejects.toMatchObject({ status: 401 });
    expect(gets).toBe(2);
  });

  it('запросы /auth/* (auth: false) refresh не запускают', async () => {
    signIn('old');
    let refreshes = 0;
    server.use(
      http.post('/api/v1/auth/refresh', () => {
        refreshes += 1;
        return problem(401, 'unauthorized');
      }),
      http.post('/api/v1/auth/login', () => problem(401, 'invalid_credentials')),
    );
    await expect(
      apiFetch('/api/v1/auth/login', { method: 'POST', body: {}, auth: false }),
    ).rejects.toMatchObject({ code: 'invalid_credentials' });
    expect(refreshes).toBe(0);
  });
});

describe('сессия', () => {
  afterEach(() => vi.useRealTimers());

  it('токен хранится только в памяти', () => {
    signIn('secret-token');
    expect(JSON.stringify({ ...localStorage })).not.toContain('secret-token');
    expect(JSON.stringify({ ...sessionStorage })).not.toContain('secret-token');
    expect(useSessionStore.getState().accessToken).toBe('secret-token');
  });

  it('упреждающее обновление за 60 с до конца срока', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    let refreshes = 0;
    server.use(
      http.post('/api/v1/auth/refresh', () => {
        refreshes += 1;
        return HttpResponse.json(tokenResponse(admin, 'renewed', 900));
      }),
    );
    signIn('first', 900);

    await vi.advanceTimersByTimeAsync(839_000);
    expect(refreshes).toBe(0);
    await vi.advanceTimersByTimeAsync(2_000);
    await vi.waitFor(() => expect(useSessionStore.getState().accessToken).toBe('renewed'));
    expect(refreshes).toBe(1);
    // и планирует следующее обновление по новому сроку
    expect(useSessionStore.getState().user?.role).toBe('admin');
  });

  it('выход отменяет запланированное обновление', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    let refreshes = 0;
    server.use(
      http.post('/api/v1/auth/refresh', () => {
        refreshes += 1;
        return HttpResponse.json(tokenResponse());
      }),
    );
    signIn('first', 900);
    clearSession();
    await vi.advanceTimersByTimeAsync(900_000);
    expect(refreshes).toBe(0);
  });

  it('restoreSession: нет cookie – anonymous, сбой сервера – unavailable', async () => {
    mockNoSession();
    await restoreSession();
    expect(useSessionStore.getState().status).toBe('anonymous');

    server.use(http.post('/api/v1/auth/refresh', () => problem(500, 'internal_error')));
    await restoreSession();
    expect(useSessionStore.getState().status).toBe('unavailable');
  });
});
