import { ConnectionState, MediaDeviceFailure } from 'livekit-client';

/** Текст о состоянии соединения; null, когда все в порядке. */
export function connectionNotice(state: ConnectionState): string | null {
  switch (state) {
    case ConnectionState.Connecting:
      return 'Подключаемся к встрече…';
    case ConnectionState.Reconnecting:
    case ConnectionState.SignalReconnecting:
      return 'Связь пропала. Переподключаемся, это займет несколько секунд…';
    default:
      return null;
  }
}

/** Сообщение пользователю по сбою устройства, о котором сообщил LiveKit. */
export function deviceFailureText(
  failure: MediaDeviceFailure | undefined,
  kind?: MediaDeviceKind,
): string {
  const what = kind === 'videoinput' ? 'камере' : 'микрофону';
  const thing = kind === 'videoinput' ? 'Камера' : 'Микрофон';
  switch (failure) {
    case MediaDeviceFailure.PermissionDenied:
      return `Браузер не дал доступ к ${what}. Разрешите доступ в настройках сайта и включите устройство снова.`;
    case MediaDeviceFailure.NotFound:
      return `${thing} не найден${kind === 'videoinput' ? 'а' : ''}. Подключите устройство.`;
    case MediaDeviceFailure.DeviceInUse:
      return `${thing} занят${kind === 'videoinput' ? 'а' : ''} другим приложением.`;
    default:
      return `Не удалось включить ${kind === 'videoinput' ? 'камеру' : 'микрофон'}.`;
  }
}
