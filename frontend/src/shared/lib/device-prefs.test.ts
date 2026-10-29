import { loadDevicePrefs, saveDevicePrefs } from './device-prefs';

describe('запомненные устройства', () => {
  afterEach(() => vi.restoreAllMocks());

  it('сохраняет и читает выбор, новые поля дополняют прежние', () => {
    saveDevicePrefs({ cameraId: 'cam-1' });
    saveDevicePrefs({ micId: 'mic-2' });
    expect(loadDevicePrefs()).toEqual({ cameraId: 'cam-1', micId: 'mic-2' });
  });

  it('пусто, если ничего не сохраняли', () => {
    expect(loadDevicePrefs()).toEqual({});
  });

  it('битый JSON и чужие значения игнорируются', () => {
    localStorage.setItem('vks_device_prefs', '{oops');
    expect(loadDevicePrefs()).toEqual({});
    localStorage.setItem('vks_device_prefs', JSON.stringify({ cameraId: 5, micId: 'ok', x: 'y' }));
    expect(loadDevicePrefs()).toEqual({ micId: 'ok' });
  });

  it('недоступное хранилище не роняет приложение', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota', 'QuotaExceededError');
    });
    expect(loadDevicePrefs()).toEqual({});
    expect(() => saveDevicePrefs({ cameraId: 'a' })).not.toThrow();
  });
});
