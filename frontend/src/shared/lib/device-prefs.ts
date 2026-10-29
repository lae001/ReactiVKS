/**
 * Выбранные устройства (камера, микрофон, динамик) в localStorage: при следующем входе лобби
 * подставит их заново. Хранится только идентификатор устройства. Любая ошибка хранилища
 * (приватный режим, запрет cookies, битый JSON) – просто работаем без запомненного выбора.
 */
const KEY = 'vks_device_prefs';

export interface DevicePrefs {
  cameraId?: string;
  micId?: string;
  speakerId?: string;
}

const FIELDS = ['cameraId', 'micId', 'speakerId'] as const;

export function loadDevicePrefs(): DevicePrefs {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(KEY) ?? 'null');
    if (typeof raw !== 'object' || raw === null) return {};
    const prefs: DevicePrefs = {};
    for (const field of FIELDS) {
      const value = (raw as Record<string, unknown>)[field];
      if (typeof value === 'string' && value !== '') prefs[field] = value;
    }
    return prefs;
  } catch {
    return {};
  }
}

export function saveDevicePrefs(patch: DevicePrefs) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...loadDevicePrefs(), ...patch }));
  } catch {
    // хранилище недоступно: выбор останется только до закрытия вкладки
  }
}
