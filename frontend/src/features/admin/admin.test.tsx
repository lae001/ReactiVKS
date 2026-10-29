import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';

import { admin, organizer, problem } from '@/test/api-mocks';
import { renderApp } from '@/test/render';
import { server } from '@/test/server';

import type { AdminUser } from './api';

const user = (n: number, extra: Partial<AdminUser> = {}): AdminUser => ({
  id: `u${n}`,
  email: `user${n}@example.ru`,
  display_name: `Пользователь ${n}`,
  role: 'organizer',
  status: 'active',
  created_at: '2026-09-15T10:00:00Z',
  last_login_at: null,
  ...extra,
});

const self: AdminUser = { ...user(0), id: admin.id, display_name: 'Иван Петров', role: 'admin' };

function listHandler(items: AdminUser[], next: string | null = null) {
  return http.get('/api/v1/admin/users', () => HttpResponse.json({ items, next_cursor: next }));
}

beforeEach(() => vi.stubEnv('VITE_API_MODE', 'http'));
afterEach(() => vi.unstubAllEnvs());

describe('админка: пользователи (режим http)', () => {
  it('таблица с ролями, статусами и «вы»; свою строку заблокировать нельзя', async () => {
    server.use(listHandler([self, user(1), user(2, { status: 'blocked' })]));
    renderApp('/admin', { user: admin });

    const table = await screen.findByRole('table', { name: 'Пользователи Системы' });
    expect(within(table).getByText('Иван Петров')).toBeInTheDocument();
    expect(within(table).getByText('(вы)')).toBeInTheDocument();
    expect(within(table).getByText('Заблокирован')).toBeInTheDocument();
    expect(
      within(table).getByRole('button', { name: 'Заблокировать: Иван Петров' }),
    ).toBeDisabled();
    expect(
      within(table).getByRole('button', { name: 'Разблокировать: Пользователь 2' }),
    ).toBeEnabled();
  });

  it('загрузка, затем пустой список', async () => {
    server.use(listHandler([]));
    renderApp('/admin', { user: admin });
    expect(await screen.findByText('Пользователей пока нет.')).toBeInTheDocument();
  });

  it('поиск и фильтр статуса уходят в запрос', async () => {
    const queries: Record<string, string>[] = [];
    server.use(
      http.get('/api/v1/admin/users', ({ request }) => {
        queries.push(Object.fromEntries(new URL(request.url).searchParams));
        return HttpResponse.json({ items: [user(1)], next_cursor: null });
      }),
    );
    renderApp('/admin', { user: admin });
    await screen.findByRole('table');
    const u = userEvent.setup();
    await u.type(screen.getByLabelText('Поиск по почте или имени'), 'anna');
    await u.click(screen.getByRole('button', { name: 'Заблокированные' }));

    await waitFor(() => expect(queries.at(-1)).toMatchObject({ q: 'anna', status: 'blocked' }));
    expect(queries[0]).toEqual({ limit: '20' });
  });

  it('пустой результат поиска', async () => {
    server.use(listHandler([]));
    renderApp('/admin', { user: admin });
    await u().type(await screen.findByLabelText('Поиск по почте или имени'), 'zzz');
    expect(await screen.findByText(/Никого не нашли/)).toBeInTheDocument();
  });

  it('«Ещё» подгружает страницу по курсору', async () => {
    server.use(
      http.get('/api/v1/admin/users', ({ request }) => {
        const cursor = new URL(request.url).searchParams.get('cursor');
        return cursor
          ? HttpResponse.json({ items: [user(2)], next_cursor: null })
          : HttpResponse.json({ items: [user(1)], next_cursor: 'c2' });
      }),
    );
    renderApp('/admin', { user: admin });
    await u().click(await screen.findByRole('button', { name: 'Ещё' }));
    expect(await screen.findByText('Пользователь 2')).toBeInTheDocument();
    expect(screen.getByText('Пользователь 1')).toBeInTheDocument();
  });

  it('блокировка: подтверждение, PATCH, список обновляется', async () => {
    let blocked = false;
    let body: unknown;
    server.use(
      http.get('/api/v1/admin/users', () =>
        HttpResponse.json({
          items: [user(1, { status: blocked ? 'blocked' : 'active' })],
          next_cursor: null,
        }),
      ),
      http.patch('/api/v1/admin/users/u1', async ({ request }) => {
        body = await request.json();
        blocked = true;
        return HttpResponse.json(user(1, { status: 'blocked' }));
      }),
    );
    renderApp('/admin', { user: admin });
    const ui = u();
    await ui.click(await screen.findByRole('button', { name: 'Заблокировать: Пользователь 1' }));
    // без подтверждения запрос не уходит
    expect(body).toBeUndefined();
    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveTextContent('Заблокировать Пользователь 1');
    await ui.click(within(dialog).getByRole('button', { name: 'Заблокировать' }));

    expect(await screen.findByText('Заблокирован')).toBeInTheDocument();
    expect(body).toEqual({ status: 'blocked' });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('отмена подтверждения не шлет запрос; разблокировка шлет active', async () => {
    const bodies: unknown[] = [];
    server.use(
      listHandler([user(1, { status: 'blocked' })]),
      http.patch('/api/v1/admin/users/u1', async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(user(1));
      }),
    );
    renderApp('/admin', { user: admin });
    const ui = u();
    await ui.click(await screen.findByRole('button', { name: 'Разблокировать: Пользователь 1' }));
    await ui.click(screen.getByRole('button', { name: 'Отмена' }));
    expect(bodies).toEqual([]);

    await ui.click(screen.getByRole('button', { name: 'Разблокировать: Пользователь 1' }));
    await ui.click(
      within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Разблокировать' }),
    );
    await waitFor(() => expect(bodies).toEqual([{ status: 'active' }]));
  });

  it.each([
    [409, 'last_admin', /не может заблокировать себя или последнего/],
    [409, 'conflict', /уже изменилось/],
    [404, 'not_found', /уже нет в списке/],
    [403, 'forbidden', /только администратору/],
  ])('PATCH %i %s: понятное сообщение, диалог остается', async (status, code, text) => {
    server.use(
      listHandler([user(1)]),
      http.patch('/api/v1/admin/users/u1', () => problem(status, code)),
    );
    renderApp('/admin', { user: admin });
    const ui = u();
    await ui.click(await screen.findByRole('button', { name: 'Заблокировать: Пользователь 1' }));
    await ui.click(
      within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Заблокировать' }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(text);
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
  });

  it('403 при загрузке списка: сообщение и «Повторить»', async () => {
    server.use(http.get('/api/v1/admin/users', () => problem(403, 'forbidden')));
    renderApp('/admin', { user: admin });
    expect(await screen.findByRole('alert')).toHaveTextContent('только администратору');
    server.use(listHandler([user(1)]));
    await u().click(screen.getByRole('button', { name: 'Повторить' }));
    expect(await screen.findByText('Пользователь 1')).toBeInTheDocument();
  });

  it('сбой сети при загрузке: сообщение о связи', async () => {
    server.use(http.get('/api/v1/admin/users', () => HttpResponse.error()));
    renderApp('/admin', { user: admin });
    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось связаться с сервером');
  });

  it('организатор страницу не видит и список не запрашивает', async () => {
    let requested = false;
    server.use(
      http.get('/api/v1/admin/users', () => {
        requested = true;
        return HttpResponse.json({ items: [], next_cursor: null });
      }),
    );
    renderApp('/admin', { user: organizer });
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'Администрирование' })).not.toBeInTheDocument(),
    );
    expect(requested).toBe(false);
  });

  it('встречи и состояние сервисов помечены как «Скоро»', async () => {
    server.use(listHandler([]));
    renderApp('/admin', { user: admin });
    expect(await screen.findByRole('heading', { name: /Активные встречи/ })).toHaveTextContent(
      'Скоро',
    );
    expect(screen.getByRole('heading', { name: /Состояние сервисов/ })).toHaveTextContent('Скоро');
  });
});

function u() {
  return userEvent.setup();
}
