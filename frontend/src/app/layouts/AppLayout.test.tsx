import { render, screen, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';

import { routes } from '@/app/routes';

async function renderNav() {
  const router = createMemoryRouter(routes, { initialEntries: ['/settings'] });
  render(<RouterProvider router={router} />);
  return within(await screen.findByRole('navigation', { name: 'Основная навигация' }));
}

describe('меню приложения по тестовой роли', () => {
  afterEach(() => vi.unstubAllEnvs());

  it('организатор не видит «Администрирование»', async () => {
    vi.stubEnv('VITE_MOCK_ROLE', 'organizer');
    const nav = await renderNav();
    expect(nav.getByRole('link', { name: 'Встречи' })).toBeInTheDocument();
    expect(nav.getByRole('link', { name: 'Настройки' })).toBeInTheDocument();
    expect(nav.queryByRole('link', { name: 'Администрирование' })).not.toBeInTheDocument();
  });

  it('роль не задана – как у организатора', async () => {
    vi.stubEnv('VITE_MOCK_ROLE', undefined);
    const nav = await renderNav();
    expect(nav.queryByRole('link', { name: 'Администрирование' })).not.toBeInTheDocument();
  });

  it('администратор видит «Администрирование»', async () => {
    vi.stubEnv('VITE_MOCK_ROLE', 'admin');
    const nav = await renderNav();
    expect(nav.getByRole('link', { name: 'Администрирование' })).toHaveAttribute('href', '/admin');
  });
});
