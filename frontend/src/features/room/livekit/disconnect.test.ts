import { ConnectionState, DisconnectReason, MediaDeviceFailure } from 'livekit-client';

import { describeDisconnect, roomEndText } from './disconnect';
import { connectionNotice, deviceFailureText } from './notice';

describe('причины выхода из комнаты', () => {
  it.each([
    [DisconnectReason.CLIENT_INITIATED, 'left'],
    [DisconnectReason.PARTICIPANT_REMOVED, 'removed'],
    [DisconnectReason.ROOM_DELETED, 'meeting_ended'],
    [DisconnectReason.DUPLICATE_IDENTITY, 'duplicate'],
    [DisconnectReason.SERVER_SHUTDOWN, 'lost'],
    [DisconnectReason.JOIN_FAILURE, 'lost'],
    [undefined, 'lost'],
  ])('%s → %s', (reason, kind) => {
    expect(describeDisconnect(reason).kind).toBe(kind);
  });

  it('тексты экранов по-русски; удаленный видит «Вас удалили из встречи»', () => {
    expect(roomEndText({ kind: 'removed' }, 'Планерка').title).toBe('Вас удалили из встречи');
    expect(roomEndText({ kind: 'meeting_ended' }, 'Планерка').text).toContain('Планерка');
    expect(roomEndText({ kind: 'lost' }, 'x').title).toBe('Соединение потеряно');
    expect(roomEndText({ kind: 'left' }, 'x').title).toBe('Вы вышли из встречи');
    expect(roomEndText({ kind: 'duplicate' }, 'x').title).toMatch(/другого устройства/);
  });
});

describe('состояния соединения и сбои устройств', () => {
  it('подключение и переподключение – сообщения, соединенное состояние – без сообщения', () => {
    expect(connectionNotice(ConnectionState.Connecting)).toBe('Подключаемся к встрече…');
    expect(connectionNotice(ConnectionState.Reconnecting)).toMatch(/Переподключаемся/);
    expect(connectionNotice(ConnectionState.SignalReconnecting)).toMatch(/Переподключаемся/);
    expect(connectionNotice(ConnectionState.Connected)).toBeNull();
    expect(connectionNotice(ConnectionState.Disconnected)).toBeNull();
  });

  it.each([
    [MediaDeviceFailure.PermissionDenied, 'audioinput', /не дал доступ к микрофону/],
    [MediaDeviceFailure.PermissionDenied, 'videoinput', /не дал доступ к камере/],
    [MediaDeviceFailure.NotFound, 'videoinput', /Камера не найдена/],
    [MediaDeviceFailure.DeviceInUse, 'audioinput', /Микрофон занят другим приложением/],
    [MediaDeviceFailure.Other, 'audioinput', /Не удалось включить микрофон/],
  ] as const)('%s, %s', (failure, kind, text) => {
    expect(deviceFailureText(failure, kind)).toMatch(text);
  });
});
