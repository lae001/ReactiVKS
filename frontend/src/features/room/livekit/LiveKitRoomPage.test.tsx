import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';

import { meetingsApi } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';
import type { RoomEntry } from '@/shared/lib/room-entry';

import { LiveKitRoomPage } from './LiveKitRoomPage';

// Само видео не нужно: проверяется, какой токен получает комната и что видит пользователь при ошибках
vi.mock('./LiveKitRoomView', () => ({
  LiveKitRoomView: ({
    connection,
    onReconnect,
  }: {
    connection: { url: string; token: string };
    onReconnect: () => void;
  }) => (
    <div>
      <p data-testid="conn">
        {connection.url} {connection.token}
      </p>
      <button onClick={onReconnect}>reconnect</button>
    </div>
  ),
}));

const meeting = { id: 'm-1', title: 'Планерка', analysis_enabled: true };
const guest: RoomEntry = {
  role: 'guest',
  displayName: 'Анна',
  consent: 'granted',
  cameraOn: true,
  micOn: true,
  inviteCode: 'abc',
};
const organizer: RoomEntry = { ...guest, role: 'organizer', consent: 'denied' };
const joinResult = (token: string) => ({
  participant_id: 'p',
  livekit_url: 'ws://new',
  livekit_token: token,
  meeting: { id: 'm-1', title: 'Планерка', status: 'active' as const, analysis_enabled: true },
});

function renderPage(entry: RoomEntry) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <LiveKitRoomPage meeting={meeting} entry={entry} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const fail = (status: number, code: string) =>
  new ApiError({ status, code, message: code, requestId: 'r' });

describe('токен комнаты', () => {
  afterEach(() => vi.restoreAllMocks());

  it('гость: каждый вход в комнату – rejoin по Participant-токену (удаленный не вернется перезагрузкой)', async () => {
    const rejoin = vi.spyOn(meetingsApi, 'rejoin').mockResolvedValue(joinResult('tok-rejoin'));
    renderPage(guest);
    expect(await screen.findByTestId('conn')).toHaveTextContent('ws://new tok-rejoin');
    expect(rejoin).toHaveBeenCalledTimes(1);
  });

  it('организатор: вход через /meetings/{id}/join, согласие по умолчанию – denied', async () => {
    const join = vi.spyOn(meetingsApi, 'joinAsOrganizer').mockResolvedValue(joinResult('tok-org'));
    renderPage(organizer);
    expect(await screen.findByTestId('conn')).toHaveTextContent('tok-org');
    expect(join).toHaveBeenCalledWith('m-1', 'denied');
  });

  it('«Подключиться снова» запрашивает новый токен', async () => {
    const user = userEvent.setup();
    const rejoin = vi
      .spyOn(meetingsApi, 'rejoin')
      .mockResolvedValueOnce(joinResult('tok-first'))
      .mockResolvedValueOnce(joinResult('tok-fresh'));
    renderPage(guest);
    await screen.findByText(/tok-first/);

    await user.click(screen.getByRole('button', { name: 'reconnect' }));
    await waitFor(() => expect(screen.getByTestId('conn')).toHaveTextContent('tok-fresh'));
    expect(rejoin).toHaveBeenCalledTimes(2);
  });
});

describe('ошибки получения токена', () => {
  afterEach(() => vi.restoreAllMocks());

  it('participant_removed – экран «Вас удалили из встречи» без «Повторить»', async () => {
    vi.spyOn(meetingsApi, 'rejoin').mockRejectedValue(fail(409, 'participant_removed'));
    renderPage(guest);
    expect(await screen.findByRole('heading', { name: 'Вас удалили из встречи' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Повторить' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'На главную' })).toHaveAttribute('href', '/');
  });

  it('401 по Participant-токену – сообщение guestErrorMessage', async () => {
    vi.spyOn(meetingsApi, 'rejoin').mockRejectedValue(fail(401, 'unauthorized'));
    renderPage(guest);
    expect(
      await screen.findByText('Вас удалили из встречи или сессия недействительна.'),
    ).toBeVisible();
  });

  it('встреча завершена – экран «Встреча завершена»', async () => {
    vi.spyOn(meetingsApi, 'rejoin').mockRejectedValue(fail(409, 'meeting_ended'));
    renderPage(guest);
    expect(await screen.findByRole('heading', { name: 'Встреча завершена' })).toBeVisible();
  });

  it('сеть и видеосервер: сообщение и «Повторить» запрашивает токен заново', async () => {
    const user = userEvent.setup();
    vi.spyOn(meetingsApi, 'joinAsOrganizer')
      .mockRejectedValueOnce(fail(503, 'livekit_unavailable'))
      .mockResolvedValueOnce(joinResult('tok-ok'));
    renderPage(organizer);
    expect(await screen.findByText(/Видеосервер сейчас недоступен/)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Повторить' }));
    expect(await screen.findByTestId('conn')).toHaveTextContent('tok-ok');
  });
  it.each(['not_found', 'forbidden'])(
    'организатор, чужая или удаленная встреча (%s): понятное сообщение и «К встречам» без «Повторить»',
    async (code) => {
      vi.spyOn(meetingsApi, 'joinAsOrganizer').mockRejectedValue(
        fail(code === 'forbidden' ? 403 : 404, code),
      );
      renderPage(organizer);
      expect(await screen.findByRole('heading', { name: 'Встреча не найдена' })).toBeVisible();
      expect(screen.getByText('Встреча не найдена или у вас нет к ней доступа.')).toBeVisible();
      expect(screen.getByRole('link', { name: 'К встречам' })).toHaveAttribute('href', '/meetings');
      expect(screen.queryByRole('button', { name: 'Повторить' })).not.toBeInTheDocument();
    },
  );
  it('ошибка с «Повторить»: рядом выход – гостю «На главную», организатору «К встречам»', async () => {
    vi.spyOn(meetingsApi, 'rejoin').mockRejectedValue(fail(503, 'livekit_unavailable'));
    vi.spyOn(meetingsApi, 'joinAsOrganizer').mockRejectedValue(fail(503, 'livekit_unavailable'));
    const { unmount } = renderPage(guest);
    expect(await screen.findByRole('button', { name: 'Повторить' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'На главную' })).toHaveAttribute('href', '/');
    unmount();

    renderPage(organizer);
    expect(await screen.findByRole('button', { name: 'Повторить' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'К встречам' })).toHaveAttribute('href', '/meetings');
  });
  it('загрузочный экран «Входим во встречу…»: «Отмена» – организатору к встречам, гостю на главную', async () => {
    const never = new Promise<never>(() => undefined);
    vi.spyOn(meetingsApi, 'rejoin').mockReturnValue(never);
    vi.spyOn(meetingsApi, 'joinAsOrganizer').mockReturnValue(never);
    const { unmount } = renderPage(guest);
    expect(await screen.findByRole('heading', { name: 'Входим во встречу…' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Отмена' })).toHaveAttribute('href', '/');
    unmount();

    renderPage(organizer);
    expect(await screen.findByRole('heading', { name: 'Входим во встречу…' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Отмена' })).toHaveAttribute('href', '/meetings');
  });
});
