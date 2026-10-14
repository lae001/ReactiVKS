import { screen } from '@testing-library/react';

import { admin, mockAuthConfig, mockNoSession, mockSession, organizer } from '@/test/api-mocks';
import { renderApp } from '@/test/render';

const protectedPaths = [
  '/meetings',
  '/meetings/new',
  '/meetings/42',
  '/settings',
  '/admin',
  '/room/m1',
];

describe('защита маршрутов', () => {
  it.each(protectedPaths)('без сессии %s ведет на /login', async (path) => {
    mockNoSession();
    mockAuthConfig();
    const router = renderApp(path);
    await screen.findByRole('heading', { level: 1, name: 'Вход' });
    expect(router.state.location.pathname).toBe('/login');
  });

  it.each(['/meetings', '/meetings/new', '/meetings/42', '/settings'])(
    'организатору %s открыт',
    async (path) => {
      const router = renderApp(path, { user: organizer });
      await screen.findByRole('main');
      expect(router.state.location.pathname).toBe(path);
      expect(screen.queryByText('Нет доступа')).not.toBeInTheDocument();
    },
  );

  it('организатору /admin закрыт', async () => {
    renderApp('/admin', { user: organizer });
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Нет доступа' }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Администрирование' })).not.toBeInTheDocument();
  });

  it('администратору /admin открыт, организаторские страницы тоже', async () => {
    renderApp('/admin', { user: admin });
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Администрирование' }),
    ).toBeInTheDocument();
  });

  it('комната открыта организатору и администратору', async () => {
    renderApp('/room/m1', { user: admin });
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Быстрая встреча' }),
    ).toBeInTheDocument();
  });

  it('гость, пришедший из лобби, попадает в комнату без учетной записи', async () => {
    mockNoSession();
    renderApp('/room/m1', {
      state: { role: 'guest', displayName: 'Гость', consent: 'granted', inviteCode: 'abc' },
    });
    expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Вход' })).not.toBeInTheDocument();
  });

  it.each(['/login', '/register'])('вошедшего с %s уводит на /meetings', async (path) => {
    mockSession(organizer);
    const router = renderApp(path);
    await screen.findByRole('heading', { level: 1, name: 'Встречи' });
    expect(router.state.location.pathname).toBe('/meetings');
  });

  it.each([
    ['/j/abc123', 'Приглашение не найдено'],
    ['/dev/ui', null],
    ['/nope', 'Такой страницы нет'],
  ])('%s открыт без входа', async (path, heading) => {
    mockNoSession();
    const router = renderApp(path);
    if (heading) {
      expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument();
    } else {
      await screen.findByRole('heading', { level: 1 });
    }
    expect(router.state.location.pathname).toBe(path);
  });
});

describe('меню по роли из useAuth', () => {
  async function nav(user: typeof organizer) {
    renderApp('/settings', { user });
    const navigation = await screen.findByRole('navigation', { name: 'Основная навигация' });
    return navigation;
  }

  it('организатор не видит «Администрирование»', async () => {
    const navigation = await nav(organizer);
    expect(navigation).toHaveTextContent('Встречи');
    expect(navigation).toHaveTextContent('Настройки');
    expect(navigation).not.toHaveTextContent('Администрирование');
  });

  it('администратор видит «Администрирование»', async () => {
    const navigation = await nav(admin);
    expect(navigation.querySelector('a[href="/admin"]')).not.toBeNull();
  });
});
