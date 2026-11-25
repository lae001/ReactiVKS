import { act, render, screen } from '@testing-library/react';
import { ConnectionError, DisconnectReason } from 'livekit-client';
import { MemoryRouter } from 'react-router';

import type { RoomEntry } from '@/shared/lib/room-entry';

import { LiveKitRoomView } from './LiveKitRoomView';

// Само видео не нужно: проверяются экраны после выхода из комнаты. Подмена LiveKitRoom отдает наружу
// обработчики, чтобы тест мог «подключить» и «отключить» комнату по причине.
const handlers: {
  video?: boolean;
  audio?: boolean;
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

describe('микрофон и камера после обновления страницы', () => {
  beforeEach(() => sessionStorage.clear());

  it('первый вход – значения из лобби; дальше последнее сохраненное состояние вкладки', () => {
    const { unmount } = renderView({ ...guest, micOn: true, cameraOn: false });
    expect([handlers.audio, handlers.video]).toEqual([true, false]);
    unmount();

    sessionStorage.setItem('vks.room.devices.m-1', '{"mic":false,"camera":true}');
    renderView({ ...guest, micOn: true, cameraOn: false });
    expect([handlers.audio, handlers.video]).toEqual([false, true]);
  });

  it.each([
    ['завершение встречи', DisconnectReason.ROOM_DELETED],
    ['удаление участника', DisconnectReason.PARTICIPANT_REMOVED],
  ])('%s очищает сохраненное состояние', (_name, reason) => {
    sessionStorage.setItem('vks.room.devices.m-1', '{"mic":false,"camera":true}');
    sessionStorage.setItem('vks.room.chat.m-1', '[]');
    renderView(guest);
    disconnectWith(reason);
    expect(sessionStorage.length).toBe(0);
  });

  it('отключение по инициативе клиента (в том числе при обновлении страницы, beforeunload) состояние сохраняет', () => {
    sessionStorage.setItem('vks.room.devices.m-1', '{"mic":false,"camera":true}');
    sessionStorage.setItem('vks.room.chat.m-1', '[]');
    renderView(guest);
    disconnectWith(DisconnectReason.CLIENT_INITIATED);
    expect(sessionStorage.length).toBe(2);
  });

  it('обрыв связи оставляет состояние для «Подключиться снова»', () => {
    sessionStorage.setItem('vks.room.devices.m-1', '{"mic":false,"camera":true}');
    renderView(guest);
    act(() => handlers.onError?.(ConnectionError.serverUnreachable('нет сервера')));
    expect(sessionStorage.getItem('vks.room.devices.m-1')).not.toBeNull();
  });
});

describe('выход из комнаты: у каждого экрана есть выход наружу', () => {
  it('«Вы вышли»: «Вернуться во встречу» и выход – «К встречам» организатору', () => {
    renderView(organizer);
    disconnectWith(DisconnectReason.CLIENT_INITIATED);
    expect(screen.getByRole('heading', { name: 'Вы вышли из встречи' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Вернуться во встречу' })).toBeVisible();
    expect(links()).toEqual([['К встречам', '/meetings']]);
  });

  it('«Вы вышли»: гостю – «На главную»', () => {
    renderView(guest);
    disconnectWith(DisconnectReason.CLIENT_INITIATED);
    expect(screen.getByRole('button', { name: 'Вернуться во встречу' })).toBeVisible();
    expect(links()).toEqual([['На главную', '/']]);
  });

  it('«Соединение потеряно»: «Подключиться снова» и выход рядом', () => {
    renderView(guest);
    act(() => handlers.onError?.(ConnectionError.serverUnreachable('нет сервера')));
    expect(screen.getByRole('heading', { name: 'Соединение потеряно' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Подключиться снова' })).toBeVisible();
    expect(links()).toEqual([['На главную', '/']]);
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

  it('«Встреча завершена»: организатору «К карточке встречи», гостю «На главную» – по одной кнопке', () => {
    const { unmount } = renderView(organizer);
    disconnectWith(DisconnectReason.ROOM_DELETED);
    expect(links()).toEqual([['К карточке встречи', '/meetings/m-1']]);
    unmount();

    renderView(guest);
    disconnectWith(DisconnectReason.ROOM_DELETED);
    expect(screen.getByRole('heading', { name: 'Встреча завершена' })).toBeVisible();
    expect(links()).toEqual([['На главную', '/']]);
  });
});
