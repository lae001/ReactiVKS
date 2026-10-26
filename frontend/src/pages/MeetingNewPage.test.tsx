import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { MOCK_MEETINGS } from '@/shared/mocks/data';
import { organizer } from '@/test/api-mocks';
import { renderApp } from '@/test/render';

describe('создание встречи', () => {
  it('без названия не создается', async () => {
    renderApp('/meetings/new', { user: organizer });
    await userEvent.setup().click(await screen.findByRole('button', { name: /Создать/ }));
    expect(await screen.findByText('Укажите название встречи')).toBeInTheDocument();
  });

  it('по умолчанию анализ включен, 3 кадра в секунду; без анализа частота недоступна', async () => {
    renderApp('/meetings/new', { user: organizer });
    const user = userEvent.setup();
    const checkbox = await screen.findByRole('checkbox', { name: /Анализировать эмоции/ });
    expect(checkbox).toBeChecked();
    expect(screen.getByRole('radio', { name: '3' })).toBeChecked();

    await user.click(checkbox);
    expect(screen.getByRole('radio', { name: '3' })).toBeDisabled();
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
    expect(MOCK_MEETINGS[0]).toMatchObject({
      title: 'Планерка отдела',
      analysis_enabled: true,
      analysis_fps: 4,
      scheduled_at: null,
    });
    expect(screen.getByRole('link', { name: 'Открыть карточку' })).toBeInTheDocument();
  });

  it('со временем начала встреча запланирована', async () => {
    renderApp('/meetings/new', { user: organizer });
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText('Название'), 'Интервью');
    await user.type(screen.getByLabelText('Дата и время начала'), '2026-11-20T10:00');
    await user.click(screen.getByRole('button', { name: 'Создать встречу' }));
    await screen.findByText('Встреча создана');
    expect(MOCK_MEETINGS[0]).toMatchObject({ title: 'Интервью', status: 'scheduled' });
    expect(MOCK_MEETINGS[0]?.scheduled_at).toMatch(/^2026-11-20T/);
  });
});
