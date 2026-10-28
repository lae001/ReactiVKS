/**
 * Подмена navigator.mediaDevices для тестов: список устройств, выдача треков с deviceId,
 * ошибки доступа по видам устройств. Реальные камеры и микрофоны в jsdom недоступны.
 */
export interface FakeDevice {
  deviceId: string;
  kind: MediaDeviceKind;
  label: string;
}

export const CAM_A: FakeDevice = {
  deviceId: 'cam-a',
  kind: 'videoinput',
  label: 'Камера FaceTime',
};
export const CAM_B: FakeDevice = { deviceId: 'cam-b', kind: 'videoinput', label: 'Камера USB' };
export const MIC_A: FakeDevice = {
  deviceId: 'mic-a',
  kind: 'audioinput',
  label: 'Микрофон встроенный',
};
export const MIC_B: FakeDevice = {
  deviceId: 'mic-b',
  kind: 'audioinput',
  label: 'Микрофон гарнитуры',
};
export const SPK_A: FakeDevice = { deviceId: 'spk-a', kind: 'audiooutput', label: 'Динамики' };
export const SPK_B: FakeDevice = { deviceId: 'spk-b', kind: 'audiooutput', label: 'Наушники' };

export interface FakeTrack {
  kind: 'video' | 'audio';
  enabled: boolean;
  stop: ReturnType<typeof vi.fn>;
  getSettings: () => { deviceId: string };
}

function fakeError(name: string) {
  const e = new Error(name);
  e.name = name;
  return e;
}

export function installFakeMediaDevices(
  options: {
    devices?: FakeDevice[];
    /** Ошибка getUserMedia по виду устройства; 'video' | 'audio' */
    fail?: Partial<Record<'video' | 'audio', string>>;
  } = {},
) {
  let devices = options.devices ?? [CAM_A, CAM_B, MIC_A, MIC_B, SPK_A, SPK_B];
  const fail = { ...options.fail };
  const tracks: FakeTrack[] = [];
  const listeners = new Set<() => void>();

  const getUserMedia = vi.fn((constraints: MediaStreamConstraints) => {
    const kind = constraints.video ? 'video' : 'audio';
    const wanted = constraints[kind === 'video' ? 'video' : 'audio'];
    const exact =
      typeof wanted === 'object' && wanted.deviceId && typeof wanted.deviceId === 'object'
        ? (wanted.deviceId as { exact?: string }).exact
        : undefined;
    const failure = fail[kind];
    if (failure) return Promise.reject(fakeError(failure));
    const list = devices.filter((d) => d.kind === (kind === 'video' ? 'videoinput' : 'audioinput'));
    const device = exact ? list.find((d) => d.deviceId === exact) : list[0];
    if (exact && !device) return Promise.reject(fakeError('OverconstrainedError'));
    if (!device) return Promise.reject(fakeError('NotFoundError'));
    const track: FakeTrack = {
      kind,
      enabled: true,
      stop: vi.fn(),
      getSettings: () => ({ deviceId: device.deviceId }),
    };
    tracks.push(track);
    return Promise.resolve({
      getTracks: () => [track],
      getVideoTracks: () => (kind === 'video' ? [track] : []),
      getAudioTracks: () => (kind === 'audio' ? [track] : []),
    } as unknown as MediaStream);
  });

  const mediaDevices = {
    getUserMedia,
    enumerateDevices: vi.fn(() => Promise.resolve(devices as MediaDeviceInfo[])),
    addEventListener: (_: string, fn: () => void) => listeners.add(fn),
    removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
  };

  vi.stubGlobal('RTCPeerConnection', class {});
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
  Object.defineProperty(navigator, 'mediaDevices', { value: mediaDevices, configurable: true });

  return {
    getUserMedia,
    tracks,
    fail,
    /** Подключили или отключили устройство: список меняется, браузер шлет devicechange */
    setDevices(next: FakeDevice[]) {
      devices = next;
      listeners.forEach((fn) => fn());
    },
  };
}

/** Делает так, будто браузер умеет выбирать динамик (Chrome, Edge). */
export function stubSinkIdSupport() {
  Object.defineProperty(HTMLMediaElement.prototype, 'setSinkId', {
    value: () => Promise.resolve(),
    configurable: true,
    writable: true,
  });
}

export function removeSinkIdSupport() {
  Reflect.deleteProperty(HTMLMediaElement.prototype, 'setSinkId');
}
