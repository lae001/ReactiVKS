import { act, cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

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
  it('404: «К списку встреч» всегда, «Назад» только если есть куда вернуться', async () => {
    mockNoSession();
    mockAuthConfig();
    const router = renderApp('/nope');
    await screen.findByRole('heading', { level: 1, name: 'Такой страницы нет' });
    expect(screen.getByRole('link', { name: 'К списку встреч' })).toHaveAttribute(
      'href',
      '/meetings',
    );
    expect(screen.queryByRole('button', { name: 'Назад' })).not.toBeInTheDocument();

    await act(() => router.navigate('/nope-2'));
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Назад' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/nope'));
    expect(screen.queryByRole('button', { name: 'Назад' })).not.toBeInTheDocument();
  });
  it('логотип на страницах входа и регистрации – ссылка на «/»', async () => {
    mockNoSession();
    mockAuthConfig();
    for (const path of ['/login', '/register']) {
      const router = renderApp(path);
      await screen.findByRole('heading', { level: 1 });
      expect(screen.getByRole('link', { name: 'ReactiVKS – на главную' })).toHaveAttribute(
        'href',
        '/',
      );
      router.dispose();
      cleanup();
    }
  });
});
