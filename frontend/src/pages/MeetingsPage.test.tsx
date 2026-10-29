import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meetingsApi } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';
import { organizer } from '@/test/api-mocks';
import { renderApp } from '@/test/render';

function renderHome() {
  return renderApp('/meetings', { user: organizer });
}

const upcoming = () => screen.findByRole('region', { name: 'Ближайшие' });
const past = () => screen.findByRole('region', { name: 'Прошедшие' });

describe('главная организатора', () => {
  afterEach(() => vi.restoreAllMocks());

  it('показывает плитки действий и два раздела со статусами', async () => {
    renderHome();
    expect(await screen.findByRole('button', { name: /Начать сейчас/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Запланировать/ })).toHaveAttribute(
      'href',
      '/meetings/new',
    );

    const next = await upcoming();
    await within(next).findByText('Еженедельная планерка команды');
    expect(next).toHaveTextContent('Интервью: frontend-разработчик');
    expect(next).not.toHaveTextContent('Ретроспектива спринта 1');

    const done = await past();
    await within(done).findByText('Ретроспектива спринта 1');
    expect(done).toHaveTextContent('Демонстрация прототипа заказчику');
    expect(done).toHaveTextContent('Отменена');
    expect(done).not.toHaveTextContent('Еженедельная планерка команды');
  });

  it('каждый раздел шлет свой запрос со статусами через запятую', async () => {
    const spy = vi.spyOn(meetingsApi, 'listMeetings');
    renderHome();
    await within(await upcoming()).findByText('Еженедельная планерка команды');
    await within(await past()).findByText('Ретроспектива спринта 1');

    const statuses = spy.mock.calls.map(([params]) => params?.status);
    expect(statuses).toContainEqual(['scheduled', 'active']);
    expect(statuses).toContainEqual(['ended', 'cancelled']);
  });

  it('поиск по названию (после паузы ввода) применяется к обоим разделам', async () => {
    const user = userEvent.setup();
    renderHome();
    await within(await upcoming()).findByText('Еженедельная планерка команды');

    await user.type(screen.getByRole('searchbox', { name: 'Поиск по названию' }), 'ретро');
    const done = await past();
    await waitFor(() => expect(done).not.toHaveTextContent('Демонстрация прототипа'));
    expect(await within(done).findByText('Ретроспектива спринта 1')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole('region', { name: 'Ближайшие' })).toHaveTextContent(
        'Ничего не найдено',
      ),
    );

    await user.clear(screen.getByRole('searchbox'));
    await user.type(screen.getByRole('searchbox'), 'такого нет');
    await waitFor(() => expect(screen.getAllByText(/Ничего не найдено/)).toHaveLength(2));
  });

  it('«Ещё» в разделе подгружает его страницу по курсору, второй раздел не трогает', async () => {
    for (let i = 1; i <= 22; i += 1) {
      await meetingsApi.createMeeting({ title: `Массовая ${String(i).padStart(2, '0')}` });
    }
    const user = userEvent.setup();
    renderHome();
    const next = await upcoming();
    await within(next).findByText('Массовая 22');
    expect(within(next).getAllByRole('listitem')).toHaveLength(20);
    const done = await past();
    await within(done).findByText('Ретроспектива спринта 1');
    expect(within(done).getAllByRole('listitem')).toHaveLength(3);
    expect(within(done).queryByRole('button', { name: 'Ещё' })).not.toBeInTheDocument();

    await user.click(within(next).getByRole('button', { name: 'Ещё' }));
    await waitFor(() => expect(within(next).getAllByRole('listitem')).toHaveLength(26));
    expect(screen.queryByRole('button', { name: 'Ещё' })).not.toBeInTheDocument();
    expect(within(done).getAllByRole('listitem')).toHaveLength(3);
  });

  it('сбой загрузки раздела – сообщение и «Повторить», второй раздел работает', async () => {
    vi.spyOn(meetingsApi, 'listMeetings').mockRejectedValueOnce(
      new ApiError({ status: 0, code: 'network_error', message: 'x' }),
    );
    const user = userEvent.setup();
    renderHome();
    expect(await screen.findByRole('alert')).toHaveTextContent(/Не удалось связаться с сервером/);
    await user.click(screen.getByRole('button', { name: 'Повторить' }));
    await within(await upcoming()).findByText('Еженедельная планерка команды');
    await within(await past()).findByText('Ретроспектива спринта 1');
  });

  it('«Начать сейчас» создает встречу, начинает ее и открывает комнату', async () => {
    const user = userEvent.setup();
    const router = renderHome();
    await user.click(await screen.findByRole('button', { name: /Начать сейчас/ }));

    await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/room\/m-new-/));
    const id = router.state.location.pathname.split('/').pop() ?? '';
    await expect(meetingsApi.getMeeting(id)).resolves.toMatchObject({
      title: 'Быстрая встреча',
      status: 'active',
    });
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
