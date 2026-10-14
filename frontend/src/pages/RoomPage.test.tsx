import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { setParticipantToken } from '@/shared/lib/participant-session';
import type { RoomEntry } from '@/shared/lib/room-entry';
import { mockNoSession, organizer } from '@/test/api-mocks';
import { renderApp } from '@/test/render';

const guest: RoomEntry = {
  role: 'guest',
  displayName: 'Анна Гостева',
  consent: 'granted',
  cameraOn: true,
  micOn: true,
  inviteCode: 'demoactive',
};

/** Организатор входит по сессии, гость – из лобби без учетной записи. */
function renderRoom(meetingId: string, state?: RoomEntry) {
  if (state) {
    mockNoSession();
    setParticipantToken('pt_test');
  }
  return renderApp(`/room/${meetingId}`, { user: state ? undefined : organizer, state });
}

describe('комната организатора', () => {
  it('видит эмоции на плитках и панель эмоций', async () => {
    const user = userEvent.setup();
    renderRoom('m-active');

    const gallery = await screen.findByRole('region', { name: 'Галерея участников' });
    expect(within(gallery).getByText('Радость')).toBeInTheDocument();
    expect(within(gallery).getByText('Без анализа')).toBeInTheDocument();
    expect(screen.getByText('Идет анализ эмоций')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Эмоции' }));
    const panel = screen.getByRole('tabpanel');
    expect(within(panel).getByText('Сводка встречи')).toBeInTheDocument();
    expect(within(panel).getByText(/рекомендательный характер/)).toBeInTheDocument();
  });

  it('модерация: удаление только после подтверждения', async () => {
    const user = userEvent.setup();
    renderRoom('m-active');
    await user.click(await screen.findByRole('button', { name: 'Участники' }));
    const remove = () =>
      user.click(screen.getByRole('button', { name: 'Удалить из встречи: Олег Иванов' }));

    await remove();
    let dialog = screen.getByRole('alertdialog', { name: 'Удалить из встречи: Олег Иванов?' });
    await user.click(within(dialog).getByRole('button', { name: 'Отмена' }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(screen.getAllByText('Олег Иванов').length).toBeGreaterThan(0);

    await remove();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();

    await remove();
    dialog = screen.getByRole('alertdialog', { name: 'Удалить из встречи: Олег Иванов?' });
    await user.click(within(dialog).getByRole('button', { name: 'Удалить из встречи' }));
    expect(screen.queryByText('Олег Иванов')).not.toBeInTheDocument();
  });

  it('«Завершить встречу» – подтверждение и переход в карточку', async () => {
    const user = userEvent.setup();
    const router = renderRoom('m-active');
    await user.click(await screen.findByRole('button', { name: 'Завершить встречу' }));
    const dialog = screen.getByRole('alertdialog', { name: 'Завершить встречу для всех?' });
    await user.click(within(dialog).getByRole('button', { name: 'Завершить встречу' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/meetings/m-active'));
  });

  it('встреча без анализа – ни индикатора, ни кнопок анализа', async () => {
    renderRoom('m-noanal');
    await screen.findByRole('heading', { level: 1, name: 'Созвон с подрядчиком' });
    expect(screen.queryByText('Идет анализ эмоций')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Эмоции' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Анализ моих эмоций' })).not.toBeInTheDocument();
  });
});

describe('комната участника', () => {
  it('не видит чужих эмоций, но видит индикатор анализа', async () => {
    renderRoom('m-active', guest);
    const gallery = await screen.findByRole('region', { name: 'Галерея участников' });
    expect(within(gallery).queryByText('Радость')).not.toBeInTheDocument();
    expect(screen.getByText('Идет анализ эмоций')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Эмоции' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Удалить из встречи/ })).not.toBeInTheDocument();
  });

  it('отзывает и возвращает согласие', async () => {
    const user = userEvent.setup();
    renderRoom('m-active', guest);
    const toggle = await screen.findByRole('button', { name: 'Анализ моих эмоций' });
    expect(toggle).toHaveAttribute('aria-pressed', 'true');

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText('Ваши эмоции не анализируются')).toBeInTheDocument();

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
  });

  it('«Выйти» – экран выхода со ссылкой обратно в лобби', async () => {
    const user = userEvent.setup();
    renderRoom('m-active', guest);
    await user.click(await screen.findByRole('button', { name: 'Выйти' }));
    expect(screen.getByRole('heading', { name: 'Вы вышли из встречи' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Вернуться во встречу' })).toHaveAttribute(
      'href',
      '/j/demoactive',
    );
  });
});
