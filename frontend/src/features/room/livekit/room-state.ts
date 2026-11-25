/**
 * Состояние комнаты, которое переживает обновление страницы (и только его): в `sessionStorage` вкладки, по
 * встрече. Другая вкладка и другой браузер его не видят. Ключи с идентификатором встречи, чтобы встречи не
 * смешивались. Все чтения и записи защищены: хранилище может быть недоступно или повреждено.
 */

const PREFIX = 'vks.room';

export const roomKey = {
  devices: (meetingId: string) => `${PREFIX}.devices.${meetingId}`,
  chat: (meetingId: string) => `${PREFIX}.chat.${meetingId}`,
  startedAt: (meetingId: string) => `${PREFIX}.startedAt.${meetingId}`,
};

export function readJson(key: string): unknown {
  try {
    const raw = sessionStorage.getItem(key);
    return raw === null ? null : (JSON.parse(raw) as unknown);
  } catch {
    return null;
  }
}

export function writeJson(key: string, value: unknown) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // хранилище недоступно или переполнено: состояние просто не переживет обновление
  }
}

export interface DeviceState {
  mic: boolean;
  camera: boolean;
}

/** Последнее состояние микрофона и камеры в этой вкладке; `null`, если записи нет (первый вход). */
export function loadDevices(meetingId: string): DeviceState | null {
  const data = readJson(roomKey.devices(meetingId));
  if (typeof data !== 'object' || data === null) return null;
  const { mic, camera } = data as { mic?: unknown; camera?: unknown };
  return typeof mic === 'boolean' && typeof camera === 'boolean' ? { mic, camera } : null;
}

export function saveDevices(meetingId: string, state: DeviceState) {
  writeJson(roomKey.devices(meetingId), state);
}

/** Забыть всё сохраненное по встрече: явный выход, завершение встречи, удаление участника. */
export function clearRoomState(meetingId: string) {
  try {
    for (const key of Object.values(roomKey)) sessionStorage.removeItem(key(meetingId));
  } catch {
    // нечего очищать
  }
}
