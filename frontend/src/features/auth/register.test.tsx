import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';

import {
  mockAuthConfig,
  mockNoSession,
  organizer,
  problem,
  tokenResponse,
  validationIssue,
} from '@/test/api-mocks';
import { renderApp } from '@/test/render';
import { server } from '@/test/server';

async function openRegister(registrationEnabled = true) {
  mockNoSession();
  mockAuthConfig(registrationEnabled);
  const router = renderApp('/register');
  await screen.findByRole('heading', { level: 1, name: 'Регистрация' });
  return router;
}

async function fill(values: { name?: string; email?: string; password?: string } = {}) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Имя'), values.name ?? 'Иван Петров');
  await user.type(screen.getByLabelText('Электронная почта'), values.email ?? 'ivan@example.ru');
  await user.type(screen.getByLabelText('Пароль'), values.password ?? 'Passw0rd1');
  await user.click(screen.getByRole('button', { name: 'Создать аккаунт' }));
}

describe('регистрация', () => {
  it('регистрирует и сразу входит', async () => {
    const order: string[] = [];
    let registerBody: unknown;
    server.use(
      http.post('/api/v1/auth/register', async ({ request }) => {
        order.push('register');
        registerBody = await request.json();
        return HttpResponse.json(organizer, { status: 201 });
      }),
      http.post('/api/v1/auth/login', () => {
        order.push('login');
        return HttpResponse.json(tokenResponse());
      }),
    );
    const router = await openRegister();
    await fill();
    await screen.findByRole('heading', { level: 1, name: 'Встречи' });
    expect(order).toEqual(['register', 'login']);
    expect(registerBody).toEqual({
      display_name: 'Иван Петров',
      email: 'ivan@example.ru',
      password: 'Passw0rd1',
    });
    expect(router.state.location.pathname).toBe('/meetings');
  });

  it('email_taken – ошибка у поля почты, без входа', async () => {
    let logins = 0;
    server.use(
      http.post('/api/v1/auth/register', () => problem(409, 'email_taken')),
      http.post('/api/v1/auth/login', () => {
        logins += 1;
        return HttpResponse.json(tokenResponse());
      }),
    );
    await openRegister();
    await fill();
    expect(await screen.findByText(/Эта почта уже зарегистрирована/)).toBeInTheDocument();
    expect(screen.getByLabelText('Электронная почта')).toHaveAttribute('aria-invalid', 'true');
    expect(logins).toBe(0);
  });

  it('validation_error – ошибки по полям из errors[].loc', async () => {
    server.use(
      http.post('/api/v1/auth/register', () =>
        problem(422, 'validation_error', {
          errors: [validationIssue('password'), validationIssue('display_name')],
        }),
      ),
    );
    await openRegister();
    await fill();
    await waitFor(() =>
      expect(screen.getByLabelText('Пароль')).toHaveAttribute('aria-invalid', 'true'),
    );
    expect(screen.getByLabelText('Имя')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Электронная почта')).not.toHaveAttribute('aria-invalid');
  });

  it('404 при выключенной регистрации – сообщение, без падения', async () => {
    server.use(http.post('/api/v1/auth/register', () => problem(404, 'not_found')));
    await openRegister();
    await fill();
    expect(await screen.findByRole('alert')).toHaveTextContent('Регистрация сейчас закрыта');
  });

  it('429 показывает время из Retry-After', async () => {
    server.use(
      http.post('/api/v1/auth/register', () =>
        problem(429, 'too_many_requests', { headers: { 'Retry-After': '120' } }),
      ),
    );
    await openRegister();
    await fill();
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Слишком много попыток зарегистрироваться. Повторите через 2 минуты.',
    );
  });

  it('если вход после регистрации не удался, показывает ошибку и остается на форме', async () => {
    server.use(
      http.post('/api/v1/auth/register', () => HttpResponse.json(organizer, { status: 201 })),
      http.post('/api/v1/auth/login', () => problem(500, 'internal_error')),
    );
    await openRegister();
    await fill();
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Регистрация' })).toBeInTheDocument();
  });

  it.each([
    ['короткий', 'a1', 'Минимум 8 символов'],
    ['без цифры', 'Password', 'Добавьте хотя бы одну цифру'],
    ['без буквы', '12345678', 'Добавьте хотя бы одну букву'],
    ['пробел в конце', 'Passw0rd1 ', 'Уберите пробелы в начале и в конце пароля'],
    ['длиннее 128', `a1${'x'.repeat(127)}`, 'Максимум 128 символов'],
  ])('политика пароля на клиенте: %s', async (_name, password, message) => {
    let calls = 0;
    server.use(
      http.post('/api/v1/auth/register', () => {
        calls += 1;
        return HttpResponse.json(organizer, { status: 201 });
      }),
    );
    await openRegister();
    await fill({ password });
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(calls).toBe(0);
  });

  it('registration_enabled=false: формы нет, есть ссылка на вход', async () => {
    await openRegister(false);
    await waitFor(() => expect(screen.getByText(/регистрация закрыта/i)).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Создать аккаунт' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Войти' })).toHaveAttribute('href', '/login');
  });
});
