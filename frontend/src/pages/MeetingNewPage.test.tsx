import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meetingsApi } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';
import { organizer } from '@/test/api-mocks';
import { renderApp } from '@/test/render';

const newest = async () => (await meetingsApi.listMeetings({ limit: 1 })).items[0];

describe('создание встречи', () => {
  afterEach(() => vi.restoreAllMocks());

  it('без названия не создается', async () => {
    renderApp('/meetings/new', { user: organizer });
    await userEvent.setup().click(await screen.findByRole('button', { name: /Создать/ }));
    expect(await screen.findByText('Укажите название встречи')).toBeInTheDocument();
  });

  it('значения по умолчанию – из GET /settings; без анализа частота недоступна', async () => {
    await meetingsApi.putSettings({ analysis_enabled_default: true, analysis_fps_default: 4 });
    renderApp('/meetings/new', { user: organizer });
    const user = userEvent.setup();
    const checkbox = await screen.findByRole('checkbox', { name: /Анализировать эмоции/ });
    expect(checkbox).toBeChecked();
    expect(screen.getByRole('radio', { name: '4' })).toBeChecked();

    await user.click(checkbox);
    expect(screen.getByRole('radio', { name: '4' })).toBeDisabled();
  });

  it('настройки не загрузились – значения по контракту (анализ включен, 3 кадра)', async () => {
    vi.spyOn(meetingsApi, 'getSettings').mockRejectedValueOnce(
      new ApiError({ status: 0, code: 'network_error', message: 'x' }),
    );
    renderApp('/meetings/new', { user: organizer });
    expect(await screen.findByRole('checkbox', { name: /Анализировать эмоции/ })).toBeChecked();
    expect(screen.getByRole('radio', { name: '3' })).toBeChecked();
  });

  it('создает встречу и показывает ссылку-приглашение', async () => {
    renderApp('/meetings/new', { user: organizer });
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText('Название'), 'Планерка отдела');
    await user.click(screen.getByRole('radio', { name: '4' }));
    await user.click(screen.getByRole('button', { name: 'Создать и получить ссылку' }));

    expect(await screen.findByText('Встреча создана')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Планерка отдела' })).toBeInTheDocument();
    expect(screen.getByText(/https:\/\/vks\.example\.ru\/j\/[a-z2-7]{10}/)).toBeInTheDocument();
    expect(await newest()).toMatchObject({
      title: 'Планерка отдела',
      analysis_enabled: true,
      analysis_fps: 4,
      scheduled_at: null,
    });
    expect(screen.getByRole('link', { name: 'Открыть карточку' })).toBeInTheDocument();
  });

  it('создать встречу и скопировать ссылку – три действия', async () => {
    renderApp('/meetings/new', { user: organizer });
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText('Название'), 'Планерка'); // 1. название
    await user.click(screen.getByRole('button', { name: 'Создать и получить ссылку' })); // 2. создать
    await user.click(await screen.findByRole('button', { name: 'Копировать ссылку' })); // 3. копировать

    expect(await screen.findByText('Ссылка скопирована')).toBeInTheDocument();
    await expect(navigator.clipboard.readText()).resolves.toMatch(
      /^https:\/\/vks\.example\.ru\/j\/[a-z2-7]{10}$/,
    );
  });

  it('со временем начала встреча запланирована', async () => {
    renderApp('/meetings/new', { user: organizer });
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText('Название'), 'Интервью');
    await user.type(screen.getByLabelText('Дата и время начала'), '2026-11-20T10:00');
    await user.click(screen.getByRole('button', { name: 'Создать встречу' }));
    await screen.findByText('Встреча создана');
    const created = await newest();
    expect(created).toMatchObject({ title: 'Интервью', status: 'scheduled' });
    expect(created?.scheduled_at).toMatch(/^2026-11-20T/);
  });

  it('повтор после сбоя идет с тем же Idempotency-Key и не создает дубль', async () => {
    const spy = vi
      .spyOn(meetingsApi, 'createMeeting')
      .mockRejectedValueOnce(new ApiError({ status: 0, code: 'network_error', message: 'x' }));
    renderApp('/meetings/new', { user: organizer });
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText('Название'), 'Планерка');
    await user.click(screen.getByRole('button', { name: 'Создать и получить ссылку' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/Не удалось связаться/);

    await user.click(screen.getByRole('button', { name: 'Создать и получить ссылку' }));
    await screen.findByText('Встреча создана');
    const [first, second] = spy.mock.calls;
    expect(first?.[1]).toBeTruthy();
    expect(second?.[1]).toBe(first?.[1]);
  });

  it('422 от сервера по полю title – ошибка у поля', async () => {
    vi.spyOn(meetingsApi, 'createMeeting').mockRejectedValueOnce(
      new ApiError({
        status: 422,
        code: 'validation_error',
        message: 'v',
        errors: [{ loc: ['body', 'title'], msg: 'Такое название нельзя', type: 'x' }],
      }),
    );
    renderApp('/meetings/new', { user: organizer });
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText('Название'), 'Планерка');
    await user.click(screen.getByRole('button', { name: 'Создать и получить ссылку' }));
    expect(await screen.findByText('Такое название нельзя')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('Встреча создана')).not.toBeInTheDocument());
  });
});
