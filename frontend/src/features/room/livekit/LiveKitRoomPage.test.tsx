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

  it('из лобби: токен и адрес берутся из ответа входа, без нового запроса', async () => {
    const rejoin = vi.spyOn(meetingsApi, 'rejoin');
    renderPage({ ...guest, livekit: { url: 'ws://lobby', token: 'tok-lobby' } });
    expect(await screen.findByTestId('conn')).toHaveTextContent('ws://lobby tok-lobby');
    expect(rejoin).not.toHaveBeenCalled();
  });

  it('гость после перезагрузки (нет токена в state): rejoin по Participant-токену', async () => {
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

  it('«Подключиться снова» запрашивает новый токен, а не берет старый из лобби', async () => {
    const user = userEvent.setup();
    const rejoin = vi.spyOn(meetingsApi, 'rejoin').mockResolvedValue(joinResult('tok-fresh'));
    renderPage({ ...guest, livekit: { url: 'ws://lobby', token: 'tok-lobby' } });
    await screen.findByText(/tok-lobby/);

    await user.click(screen.getByRole('button', { name: 'reconnect' }));
    await waitFor(() => expect(screen.getByTestId('conn')).toHaveTextContent('tok-fresh'));
    expect(rejoin).toHaveBeenCalledTimes(1);
  });
});

describe('ошибки получения токена', () => {
  afterEach(() => vi.restoreAllMocks());

  it('participant_removed – экран «Вас удалили из встречи» без «Повторить»', async () => {
    vi.spyOn(meetingsApi, 'rejoin').mockRejectedValue(fail(409, 'participant_removed'));
    renderPage(guest);
    expect(await screen.findByRole('heading', { name: 'Вас удалили из встречи' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Повторить' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'К приглашению' })).toHaveAttribute('href', '/j/abc');
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
});
