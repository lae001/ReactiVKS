import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';

import { routes } from '@/app/routes';

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

describe('маршруты-заглушки', () => {
  it.each([
    ['/login', 'Вход'],
    ['/register', 'Регистрация'],
    ['/meetings', 'Встречи'],
    ['/meetings/new', 'Новая встреча'],
    ['/meetings/42', 'Карточка встречи'],
    ['/settings', 'Настройки'],
    ['/admin', 'Администрирование'],
    ['/j/abc123', 'Встреча еще не загружена'],
    ['/nope', 'Такой страницы нет'],
  ])('%s открывается', async (path, heading) => {
    renderAt(path);
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument();
  });

  it('корень перенаправляет на /meetings', async () => {
    const router = renderAt('/');
    await screen.findByRole('heading', { level: 1, name: 'Встречи' });
    expect(router.state.location.pathname).toBe('/meetings');
  });

  it('комната загружается лениво', async () => {
    renderAt('/room/m1');
    expect(await screen.findByText('Встреча m1')).toBeInTheDocument();
  });
});
