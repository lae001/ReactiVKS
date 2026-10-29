import { screen } from '@testing-library/react';

import { admin, mockAuthConfig, mockNoSession, organizer } from '@/test/api-mocks';
import { renderApp } from '@/test/render';

describe('маршруты-заглушки', () => {
  it.each([
    ['/meetings', 'Встречи'],
    ['/meetings/new', 'Новая встреча'],
    ['/meetings/m-later', 'Интервью: frontend-разработчик'],
    ['/settings', 'Настройки'],
  ])('%s открывается организатору', async (path, heading) => {
    renderApp(path, { user: organizer });
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument();
  });

  it('/admin открывается администратору', async () => {
    renderApp('/admin', { user: admin });
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Администрирование' }),
    ).toBeInTheDocument();
  });

  it.each([
    ['/login', 'Вход'],
    ['/register', 'Регистрация'],
    ['/j/abc123', 'Приглашение не найдено'],
    ['/nope', 'Такой страницы нет'],
  ])('%s открывается без входа', async (path, heading) => {
    mockNoSession();
    mockAuthConfig();
    renderApp(path);
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument();
  });

  it('корень перенаправляет на /meetings', async () => {
    const router = renderApp('/', { user: organizer });
    await screen.findByRole('heading', { level: 1, name: 'Встречи' });
    expect(router.state.location.pathname).toBe('/meetings');
  });

  it('комната загружается лениво', async () => {
    renderApp('/room/m-active', { user: organizer });
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Еженедельная планерка команды' }),
    ).toBeInTheDocument();
  });
});
