import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meetingsApi } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';
import { organizer } from '@/test/api-mocks';
import { renderApp } from '@/test/render';

function renderHome() {
  return renderApp('/meetings', { user: organizer });
}

const list = () => screen.findByRole('region', { name: 'Все встречи' });

describe('главная организатора', () => {
  afterEach(() => vi.restoreAllMocks());

  it('показывает плитки действий и список встреч со статусами', async () => {
    renderHome();
    expect(await screen.findByRole('button', { name: /Начать сейчас/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Запланировать/ })).toHaveAttribute(
      'href',
      '/meetings/new',
    );

    const all = await list();
    await within(all).findByText('Еженедельная планерка команды');
    expect(all).toHaveTextContent('Интервью: frontend-разработчик');
    expect(all).toHaveTextContent('Демонстрация прототипа заказчику');
    expect(all).toHaveTextContent('Отменена');
  });

  it('фильтр по статусу идет в запрос и меняет список', async () => {
    const spy = vi.spyOn(meetingsApi, 'listMeetings');
    const user = userEvent.setup();
    renderHome();
    await within(await list()).findByText('Еженедельная планерка команды');

    await user.click(screen.getByRole('button', { name: 'Завершены' }));
    await waitFor(() =>
      expect(spy).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: ['ended'] }),
        expect.anything(),
      ),
    );
    const all = await list();
    await waitFor(() => expect(all).not.toHaveTextContent('Еженедельная планерка команды'));
    expect(all).toHaveTextContent('Ретроспектива спринта 1');
    expect(screen.getByRole('button', { name: 'Завершены' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('поиск по названию (после паузы ввода) и пустой результат', async () => {
    const user = userEvent.setup();
    renderHome();
    await within(await list()).findByText('Еженедельная планерка команды');

    await user.type(screen.getByRole('searchbox', { name: 'Поиск по названию' }), 'интервью');
    const all = await list();
    await waitFor(() => expect(all).not.toHaveTextContent('Еженедельная планерка команды'));
    expect(await within(all).findByText('Интервью: frontend-разработчик')).toBeInTheDocument();

    await user.clear(screen.getByRole('searchbox'));
    await user.type(screen.getByRole('searchbox'), 'такого нет');
    expect(await screen.findByText(/Ничего не найдено/)).toBeInTheDocument();
  });

  it('«Ещё» подгружает следующую страницу по курсору, пока она есть', async () => {
    for (let i = 1; i <= 22; i += 1) {
      await meetingsApi.createMeeting({ title: `Массовая ${String(i).padStart(2, '0')}` });
    }
    const user = userEvent.setup();
    renderHome();
    const all = await list();
    await within(all).findByText('Массовая 22');
    expect(within(all).getAllByRole('listitem')).toHaveLength(20);

    await user.click(screen.getByRole('button', { name: 'Ещё' }));
    await waitFor(() => expect(within(all).getAllByRole('listitem')).toHaveLength(29));
    expect(screen.queryByRole('button', { name: 'Ещё' })).not.toBeInTheDocument();
  });

  it('сбой загрузки – сообщение и «Повторить»', async () => {
    vi.spyOn(meetingsApi, 'listMeetings').mockRejectedValueOnce(
      new ApiError({ status: 0, code: 'network_error', message: 'x' }),
    );
    const user = userEvent.setup();
    renderHome();
    expect(await screen.findByRole('alert')).toHaveTextContent(/Не удалось связаться с сервером/);
    await user.click(screen.getByRole('button', { name: 'Повторить' }));
    await within(await list()).findByText('Еженедельная планерка команды');
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
