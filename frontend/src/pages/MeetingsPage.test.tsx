import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router';

import { routes } from '@/app/routes';

function renderHome() {
  const router = createMemoryRouter(routes, { initialEntries: ['/meetings'] });
  render(<RouterProvider router={router} />);
  return router;
}

describe('главная организатора', () => {
  it('показывает плитки действий и встречи по разделам', async () => {
    renderHome();
    expect(await screen.findByRole('button', { name: /Начать сейчас/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Запланировать/ })).toHaveAttribute(
      'href',
      '/meetings/new',
    );

    const upcoming = screen.getByRole('region', { name: 'Ближайшие' });
    expect(upcoming).toHaveTextContent('Еженедельная планерка команды');
    expect(upcoming).toHaveTextContent('Интервью: frontend-разработчик');
    expect(upcoming).not.toHaveTextContent('Демонстрация прототипа заказчику');

    const past = screen.getByRole('region', { name: 'Прошедшие' });
    expect(past).toHaveTextContent('Демонстрация прототипа заказчику');
  });

  it('неверная ссылка – подсказка, верная – переход в лобби', async () => {
    const user = userEvent.setup();
    const router = renderHome();
    const input = await screen.findByLabelText('Войти по ссылке');

    await user.type(input, 'что-то не то');
    await user.click(screen.getByRole('button', { name: 'Перейти в лобби' }));
    expect(screen.getByText(/Не похоже на ссылку-приглашение/)).toBeInTheDocument();

    await user.clear(input);
    await user.type(input, 'https://vks.example.ru/j/demoactive');
    await user.click(screen.getByRole('button', { name: 'Перейти в лобби' }));
    expect(router.state.location.pathname).toBe('/j/demoactive');
  });
});
