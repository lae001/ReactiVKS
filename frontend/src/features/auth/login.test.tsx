import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';

import { useSessionStore } from '@/shared/api/session';
import {
  mockAuthConfig,
  mockNoSession,
  mockSession,
  organizer,
  problem,
  tokenResponse,
  validationIssue,
} from '@/test/api-mocks';
import { renderApp } from '@/test/render';
import { server } from '@/test/server';

async function openLogin() {
  mockNoSession();
  mockAuthConfig(true);
  const router = renderApp('/login');
  await screen.findByRole('heading', { level: 1, name: 'Вход' });
  return router;
}

async function submit(email = 'ivan@example.ru', password = 'Passw0rd1') {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Электронная почта'), email);
  await user.type(screen.getByLabelText('Пароль'), password);
  await user.click(screen.getByRole('button', { name: 'Войти' }));
}

describe('вход', () => {
  it('успешный вход: токен в памяти, переход на /meetings, имя в шапке', async () => {
    let body: unknown;
    server.use(
      http.post('/api/v1/auth/login', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(tokenResponse());
      }),
    );
    const router = await openLogin();
    await submit();

    await screen.findByRole('heading', { level: 1, name: 'Встречи' });
    expect(router.state.location.pathname).toBe('/meetings');
    expect(body).toEqual({ email: 'ivan@example.ru', password: 'Passw0rd1' });
    expect(useSessionStore.getState()).toMatchObject({
      status: 'authenticated',
      accessToken: 'access-1',
    });
    expect(screen.getByText('Иван Петров')).toBeInTheDocument();
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain('access-1');
  });

  it('после входа возвращает туда, куда пользователь шел', async () => {
    server.use(http.post('/api/v1/auth/login', () => HttpResponse.json(tokenResponse())));
    mockNoSession();
    mockAuthConfig();
    const router = renderApp('/settings');
    await screen.findByRole('heading', { level: 1, name: 'Вход' });
    await submit();
    await screen.findByRole('heading', { level: 1, name: 'Настройки' });
    expect(router.state.location.pathname).toBe('/settings');
  });

  it.each([
    [
      'invalid_credentials',
      401,
      {},
      'Неверная почта или пароль. Проверьте данные и попробуйте снова.',
    ],
    ['user_blocked', 403, {}, 'Аккаунт заблокирован. Обратитесь к администратору системы.'],
    [
      'too_many_requests',
      429,
      { headers: { 'Retry-After': '45' } },
      'Слишком много попыток войти. Повторите через 45 секунд.',
    ],
    [
      'too_many_requests',
      429,
      { headers: { 'Retry-After': '300' } },
      'Слишком много попыток войти. Повторите через 5 минут.',
    ],
    ['too_many_requests', 429, {}, 'Слишком много попыток войти. Подождите немного.'],
    [
      'internal_error',
      500,
      {},
      'Не удалось войти. Повторите попытку позже. Код обращения: req-123.',
    ],
  ])('%s (%i) → понятное сообщение', async (code, status, extra, message) => {
    server.use(http.post('/api/v1/auth/login', () => problem(status, code, extra)));
    await openLogin();
    await submit();
    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(screen.getByRole('heading', { level: 1, name: 'Вход' })).toBeInTheDocument();
    expect(useSessionStore.getState().status).toBe('anonymous');
  });

  it('validation_error: ошибки сервера ложатся на поля по loc', async () => {
    server.use(
      http.post('/api/v1/auth/login', () =>
        problem(422, 'validation_error', { errors: [validationIssue('email')] }),
      ),
    );
    await openLogin();
    await submit();
    const email = screen.getByLabelText('Электронная почта');
    await waitFor(() => expect(email).toHaveAttribute('aria-invalid', 'true'));
    expect(screen.getByText(/Проверьте адрес/)).toBeInTheDocument();
    expect(screen.getByLabelText('Пароль')).not.toHaveAttribute('aria-invalid');
  });

  it('сбой сети: просит проверить соединение', async () => {
    server.use(http.post('/api/v1/auth/login', () => HttpResponse.error()));
    await openLogin();
    await submit();
    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось связаться с сервером');
  });

  it('пустая форма и неверная почта не уходят на сервер', async () => {
    let calls = 0;
    server.use(
      http.post('/api/v1/auth/login', () => {
        calls += 1;
        return HttpResponse.json(tokenResponse());
      }),
    );
    await openLogin();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Войти' }));
    expect(await screen.findByText('Укажите электронную почту')).toBeInTheDocument();
    expect(screen.getByText('Введите пароль')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Электронная почта'), 'не-почта');
    await user.type(screen.getByLabelText('Пароль'), 'x');
    await user.click(screen.getByRole('button', { name: 'Войти' }));
    expect(await screen.findByText(/Проверьте адрес/)).toBeInTheDocument();
    expect(calls).toBe(0);
  });

  it('ссылка на регистрацию видна, пока регистрация включена', async () => {
    await openLogin();
    await waitFor(() =>
      expect(screen.getByRole('link', { name: 'Зарегистрироваться' })).toHaveAttribute(
        'href',
        '/register',
      ),
    );
  });

  it('registration_enabled=false скрывает ссылку на регистрацию', async () => {
    mockNoSession();
    mockAuthConfig(false);
    renderApp('/login');
    await screen.findByRole('heading', { level: 1, name: 'Вход' });
    await waitFor(() => expect(useSessionStore.getState().status).toBe('anonymous'));
    // конфиг приходит асинхронно: ждем, пока ссылка исчезнет
    await waitFor(() =>
      expect(screen.queryByRole('link', { name: 'Зарегистрироваться' })).not.toBeInTheDocument(),
    );
  });
});

describe('сессия при старте', () => {
  it('живая cookie: страница открывается без повторного входа', async () => {
    const calls = mockSession(organizer);
    const router = renderApp('/settings');
    expect(await screen.findByRole('heading', { level: 1, name: 'Настройки' })).toBeInTheDocument();
    expect(calls.refresh).toBe(1);
    expect(router.state.location.pathname).toBe('/settings');
  });

  it('cookie нет: защищенная страница ведет на /login', async () => {
    mockNoSession();
    mockAuthConfig();
    const router = renderApp('/meetings');
    await screen.findByRole('heading', { level: 1, name: 'Вход' });
    expect(router.state.location.pathname).toBe('/login');
  });

  it('сервер недоступен: сообщение и кнопка «Повторить»', async () => {
    server.use(http.post('/api/v1/auth/refresh', () => HttpResponse.error()));
    renderApp('/meetings');
    expect(
      await screen.findByRole('heading', { name: 'Нет связи с сервером' }),
    ).toBeInTheDocument();

    mockSession(organizer);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Повторить' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Встречи' })).toBeInTheDocument();
  });
});

describe('выход', () => {
  it('POST /auth/logout, очистка сессии и переход на /login', async () => {
    const calls = mockSession(organizer);
    mockAuthConfig();
    const router = renderApp('/meetings');
    await screen.findByRole('heading', { level: 1, name: 'Встречи' });

    await userEvent.setup().click(screen.getByRole('button', { name: 'Выйти' }));
    await screen.findByRole('heading', { level: 1, name: 'Вход' });
    expect(calls.logout).toBe(1);
    expect(router.state.location.pathname).toBe('/login');
    expect(useSessionStore.getState()).toMatchObject({ status: 'anonymous', accessToken: null });
  });

  it('выходит, даже если сервер не ответил', async () => {
    mockSession(organizer);
    mockAuthConfig();
    server.use(http.post('/api/v1/auth/logout', () => HttpResponse.error()));
    renderApp('/meetings');
    await screen.findByRole('heading', { level: 1, name: 'Встречи' });
    await userEvent.setup().click(screen.getByRole('button', { name: 'Выйти' }));
    await screen.findByRole('heading', { level: 1, name: 'Вход' });
    expect(useSessionStore.getState().accessToken).toBeNull();
  });
});
