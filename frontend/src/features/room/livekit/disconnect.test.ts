import {
  ConnectionError,
  ConnectionState,
  DisconnectReason,
  MediaDeviceFailure,
} from 'livekit-client';

import {
  describeDisconnect,
  isAbortedBeforeConnect,
  isCancelledConnect,
  isConnectionLost,
  roomEndText,
} from './disconnect';
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

  it('для обрыва в экран попадает техническая причина', () => {
    const lost = describeDisconnect(DisconnectReason.SERVER_SHUTDOWN);
    expect(lost).toEqual({ kind: 'lost', detail: 'SERVER_SHUTDOWN' });
    expect(roomEndText(lost, 'x').detail).toBe('SERVER_SHUTDOWN');
    expect(describeDisconnect(undefined)).toEqual({ kind: 'lost', detail: undefined });
    expect(roomEndText({ kind: 'left' }, 'x').detail).toBeUndefined();
  });

  it('тексты экранов по-русски; удаленный видит «Вас удалили из встречи»', () => {
    expect(roomEndText({ kind: 'removed' }, 'Планерка').title).toBe('Вас удалили из встречи');
    expect(roomEndText({ kind: 'meeting_ended' }, 'Планерка').text).toContain('Планерка');
    expect(roomEndText({ kind: 'lost' }, 'x').title).toBe('Соединение потеряно');
    expect(roomEndText({ kind: 'left' }, 'x').title).toBe('Вы вышли из встречи');
    expect(roomEndText({ kind: 'duplicate' }, 'x').title).toMatch(/другого устройства/);
  });
});

describe('отмена попытки подключения (StrictMode в dev) не считается обрывом', () => {
  it('«Client initiated disconnect» – отмена, остальные ошибки подключения – нет', () => {
    expect(isCancelledConnect(ConnectionError.cancelled('Client initiated disconnect'))).toBe(true);
    expect(isCancelledConnect(ConnectionError.serverUnreachable('нет сервера'))).toBe(false);
    expect(isCancelledConnect(ConnectionError.timeout('таймаут'))).toBe(false);
    expect(isCancelledConnect(new Error('прочее'))).toBe(false);
  });

  it('обрывом считается только настоящая ошибка подключения, отказ устройств – нет', () => {
    expect(isConnectionLost(ConnectionError.serverUnreachable('нет сервера'))).toBe(true);
    expect(isConnectionLost(ConnectionError.timeout('таймаут'))).toBe(true);
    expect(isConnectionLost(ConnectionError.cancelled('Client initiated disconnect'))).toBe(false);
    const denied = new Error('Permission denied');
    denied.name = 'NotAllowedError';
    expect(isConnectionLost(denied)).toBe(false);
    expect(isConnectionLost(new Error('прочее'))).toBe(false);
  });

  it('выход по инициативе клиента до подключения – отмена, после подключения – выход пользователя', () => {
    expect(isAbortedBeforeConnect(DisconnectReason.CLIENT_INITIATED, false)).toBe(true);
    expect(isAbortedBeforeConnect(DisconnectReason.CLIENT_INITIATED, true)).toBe(false);
    expect(isAbortedBeforeConnect(DisconnectReason.SERVER_SHUTDOWN, false)).toBe(false);
    expect(isAbortedBeforeConnect(undefined, false)).toBe(false);
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
