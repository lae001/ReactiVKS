import { ConnectionError, ConnectionErrorReason, DisconnectReason } from 'livekit-client';

export type RoomEnd =
  | { kind: 'left' }
  | { kind: 'removed' }
  | { kind: 'meeting_ended' }
  | { kind: 'duplicate' }
  | { kind: 'lost' };

/**
 * Почему мы больше не в комнате. `lost` – обрыв, после которого LiveKit не смог переподключиться:
 * пользователю предлагается подключиться снова.
 */
export function describeDisconnect(reason: DisconnectReason | undefined): RoomEnd {
  switch (reason) {
    case DisconnectReason.CLIENT_INITIATED:
      return { kind: 'left' };
    case DisconnectReason.PARTICIPANT_REMOVED:
      return { kind: 'removed' };
    case DisconnectReason.ROOM_DELETED:
    case DisconnectReason.ROOM_CLOSED:
      return { kind: 'meeting_ended' };
    case DisconnectReason.DUPLICATE_IDENTITY:
      return { kind: 'duplicate' };
    default:
      return { kind: 'lost' };
  }
}

/**
 * Ошибка подключения, вызванная отменой самой попытки («Client initiated disconnect»): LiveKit отменяет
 * подключение, когда компонент размонтируется до его завершения. В dev-режиме так делает `StrictMode`
 * (монтирование – размонтирование – монтирование). Это не обрыв связи, показывать экран «Соединение
 * потеряно» не нужно: следующая попытка подключения идет своим чередом.
 */
export function isCancelledConnect(error: unknown): boolean {
  return error instanceof ConnectionError && error.reason === ConnectionErrorReason.Cancelled;
}

/**
 * Ошибка из `onError` комнаты, после которой связи нет. LiveKit передает туда не только ошибки подключения,
 * но и отказ устройств (`NotAllowedError: Permission denied`, камера занята и т. п.): с ними встреча
 * продолжается без камеры или микрофона, а причину показывает `onMediaDeviceFailure`. Поэтому обрывом
 * считается только настоящая ошибка подключения, кроме отмены самой попытки.
 */
export function isConnectionLost(error: unknown): boolean {
  return error instanceof ConnectionError && !isCancelledConnect(error);
}

/**
 * Отключение, которое пришло раньше, чем комната подключилась, по инициативе клиента: это отмена
 * попытки (см. `isCancelledConnect`), а не выход пользователя.
 */
export function isAbortedBeforeConnect(
  reason: DisconnectReason | undefined,
  wasConnected: boolean,
): boolean {
  return !wasConnected && reason === DisconnectReason.CLIENT_INITIATED;
}

/** Заголовок и пояснение экрана по причине выхода (кнопки – у вызывающего). */
export function roomEndText(end: RoomEnd, meetingTitle: string): { title: string; text: string } {
  switch (end.kind) {
    case 'left':
      return {
        title: 'Вы вышли из встречи',
        text: 'Камера и микрофон выключены. Если вышли случайно, вернитесь во встречу.',
      };
    case 'removed':
      return {
        title: 'Вас удалили из встречи',
        text: `Организатор удалил вас из встречи «${meetingTitle}». Вернуться по этой ссылке нельзя.`,
      };
    case 'meeting_ended':
      return {
        title: 'Встреча завершена',
        text: `Организатор завершил встречу «${meetingTitle}».`,
      };
    case 'duplicate':
      return {
        title: 'Вы вошли с другого устройства',
        text: 'С вашим именем в эту встречу вошли еще раз (другая вкладка или устройство), поэтому здесь связь закрыта.',
      };
    case 'lost':
      return {
        title: 'Соединение потеряно',
        text: 'Связь с видеосервером оборвалась, и восстановить ее автоматически не получилось. Проверьте интернет и подключитесь снова.',
      };
  }
}
