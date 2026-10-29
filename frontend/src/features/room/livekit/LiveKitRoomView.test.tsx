import { act, render, screen } from '@testing-library/react';
import { ConnectionError, DisconnectReason } from 'livekit-client';
import { MemoryRouter } from 'react-router';

import type { RoomEntry } from '@/shared/lib/room-entry';

import { LiveKitRoomView } from './LiveKitRoomView';

// Само видео не нужно: проверяются экраны после выхода из комнаты. Подмена LiveKitRoom отдает наружу
// обработчики, чтобы тест мог «подключить» и «отключить» комнату по причине.
const handlers: {
  onConnected?: () => void;
  onDisconnected?: (reason?: DisconnectReason) => void;
  onError?: (error: Error) => void;
} = {};

vi.mock('@livekit/components-react', () => ({
  LiveKitRoom: (props: typeof handlers) => {
    Object.assign(handlers, props);
    return <div data-testid="room" />;
  },
}));
vi.mock('./RoomShell', () => ({ RoomShell: () => null }));

const meeting = { id: 'm-1', title: 'Планерка', analysis_enabled: true };
const guest: RoomEntry = {
  role: 'guest',
  displayName: 'Анна',
  consent: 'granted',
  cameraOn: true,
  micOn: true,
  inviteCode: 'abc2345678',
};
const organizer: RoomEntry = { ...guest, role: 'organizer', inviteCode: undefined };

function renderView(entry: RoomEntry) {
  return render(
    <MemoryRouter>
      <LiveKitRoomView
        meeting={meeting}
        entry={entry}
        connection={{ url: 'ws://x', token: 't' }}
        onReconnect={() => undefined}
      />
    </MemoryRouter>,
  );
}

/** Комната подключилась, затем отключилась по причине. */
function disconnectWith(reason: DisconnectReason) {
  act(() => handlers.onConnected?.());
  act(() => handlers.onDisconnected?.(reason));
}

const links = () =>
  screen.queryAllByRole('link').map((a) => [a.textContent, a.getAttribute('href')]);

describe('выход из комнаты: у каждого экрана есть выход наружу', () => {
  it('«Вы вышли»: «Вернуться во встречу» и выход – «К встречам» организатору', () => {
    renderView(organizer);
    disconnectWith(DisconnectReason.CLIENT_INITIATED);
    expect(screen.getByRole('heading', { name: 'Вы вышли из встречи' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Вернуться во встречу' })).toBeVisible();
    expect(links()).toEqual([['К встречам', '/meetings']]);
  });

  it('«Вы вышли»: гостю – «К приглашению» своей встречи', () => {
    renderView(guest);
    disconnectWith(DisconnectReason.CLIENT_INITIATED);
    expect(screen.getByRole('button', { name: 'Вернуться во встречу' })).toBeVisible();
    expect(links()).toEqual([['К приглашению', '/j/abc2345678']]);
  });

  it('«Соединение потеряно»: «Подключиться снова» и выход рядом', () => {
    renderView(guest);
    act(() => handlers.onError?.(ConnectionError.serverUnreachable('нет сервера')));
    expect(screen.getByRole('heading', { name: 'Соединение потеряно' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Подключиться снова' })).toBeVisible();
    expect(links()).toEqual([['К приглашению', '/j/abc2345678']]);
  });

  it.each([
    ['Вас удалили из встречи', DisconnectReason.PARTICIPANT_REMOVED],
    ['Вы вошли с другого устройства', DisconnectReason.DUPLICATE_IDENTITY],
  ])('«%s»: одна кнопка выхода без дубля', (title, reason) => {
    renderView(organizer);
    disconnectWith(reason);
    expect(screen.getByRole('heading', { name: title })).toBeVisible();
    expect(links()).toEqual([['К встречам', '/meetings']]);
  });

  it('«Встреча завершена»: организатору «К карточке встречи», гостю «К приглашению» – по одной кнопке', () => {
    const { unmount } = renderView(organizer);
    disconnectWith(DisconnectReason.ROOM_DELETED);
    expect(links()).toEqual([['К карточке встречи', '/meetings/m-1']]);
    unmount();

    renderView(guest);
    disconnectWith(DisconnectReason.ROOM_DELETED);
    expect(screen.getByRole('heading', { name: 'Встреча завершена' })).toBeVisible();
    expect(links()).toEqual([['К приглашению', '/j/abc2345678']]);
  });

  it('гость без кода приглашения: запасной выход «На главную» вместо битой ссылки', () => {
    renderView({ ...guest, inviteCode: undefined });
    disconnectWith(DisconnectReason.CLIENT_INITIATED);
    expect(links()).toEqual([['На главную', '/']]);
  });
});
