import { act, renderHook, waitFor } from '@testing-library/react';

import { loadDevicePrefs } from '@/shared/lib/device-prefs';
import {
  CAM_A,
  CAM_B,
  installFakeMediaDevices,
  MIC_A,
  MIC_B,
  removeSinkIdSupport,
  SPK_A,
  stubSinkIdSupport,
} from '@/test/fake-media';

import { describeMediaError, useLocalMedia } from './use-local-media';

afterEach(() => {
  vi.unstubAllGlobals();
  removeSinkIdSupport();
});

describe('локальные устройства', () => {
  it('открывает камеру и микрофон по умолчанию и показывает списки устройств', async () => {
    installFakeMediaDevices();
    const { result } = renderHook(() => useLocalMedia());
    expect(result.current.status).toBe('pending');
    await waitFor(() => expect(result.current.status).toBe('ready'));
    await waitFor(() => expect(result.current.cameras).toHaveLength(2));

    expect(result.current.cameras.map((d) => d.label)).toEqual(['Камера FaceTime', 'Камера USB']);
    expect(result.current.mics.map((d) => d.id)).toEqual(['mic-a', 'mic-b']);
    expect(result.current.cameraId).toBe('cam-a');
    expect(result.current.micId).toBe('mic-a');
  });

  it('выбор камеры переоткрывает поток, останавливает прежний и запоминается', async () => {
    const fake = installFakeMediaDevices();
    const { result } = renderHook(() => useLocalMedia());
    await waitFor(() => expect(result.current.cameraStatus).toBe('ready'));
    const first = fake.tracks.find((t) => t.kind === 'video');

    act(() => result.current.selectCamera(CAM_B.deviceId));
    await waitFor(() => expect(result.current.cameraId).toBe('cam-b'));
    expect(fake.getUserMedia).toHaveBeenCalledWith({ video: { deviceId: { exact: 'cam-b' } } });
    expect(first?.stop).toHaveBeenCalled();
    expect(loadDevicePrefs()).toEqual({ cameraId: 'cam-b' });
  });

  it('выбор микрофона и динамика запоминается', async () => {
    installFakeMediaDevices();
    const { result } = renderHook(() => useLocalMedia());
    await waitFor(() => expect(result.current.mics).toHaveLength(2));

    act(() => result.current.selectMic(MIC_B.deviceId));
    act(() => result.current.selectSpeaker(SPK_A.deviceId));
    await waitFor(() => expect(result.current.micId).toBe('mic-b'));
    expect(result.current.speakerId).toBe('spk-a');
    expect(loadDevicePrefs()).toEqual({ micId: 'mic-b', speakerId: 'spk-a' });
  });

  it('запомненный выбор применяется при следующем входе', async () => {
    localStorage.setItem('vks_device_prefs', JSON.stringify({ cameraId: 'cam-b', micId: 'mic-b' }));
    const fake = installFakeMediaDevices();
    const { result } = renderHook(() => useLocalMedia());
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(fake.getUserMedia).toHaveBeenCalledWith({ video: { deviceId: { exact: 'cam-b' } } });
    expect(fake.getUserMedia).toHaveBeenCalledWith({ audio: { deviceId: { exact: 'mic-b' } } });
    await waitFor(() => expect(result.current.cameraId).toBe('cam-b'));
  });

  it('запомненное устройство отключили – берется устройство по умолчанию', async () => {
    localStorage.setItem('vks_device_prefs', JSON.stringify({ cameraId: 'cam-gone' }));
    installFakeMediaDevices();
    const { result } = renderHook(() => useLocalMedia());
    await waitFor(() => expect(result.current.cameraStatus).toBe('ready'));
    await waitFor(() => expect(result.current.cameraId).toBe('cam-a'));
    expect(result.current.cameraError).toBeNull();
  });

  it('запрет доступа к камере не мешает микрофону', async () => {
    installFakeMediaDevices({ fail: { video: 'NotAllowedError' } });
    const { result } = renderHook(() => useLocalMedia());
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.cameraStatus).toBe('unavailable');
    expect(result.current.cameraError).toMatch(/не дал доступ к камере/);
    expect(result.current.micStatus).toBe('ready');
    expect(result.current.micError).toBeNull();
  });

  it('микрофона нет – понятное сообщение, камера работает', async () => {
    installFakeMediaDevices({ devices: [CAM_A], fail: {} });
    const { result } = renderHook(() => useLocalMedia());
    await waitFor(() => expect(result.current.micStatus).toBe('unavailable'));
    expect(result.current.micError).toMatch(/Микрофон не найден/);
    expect(result.current.cameraStatus).toBe('ready');
    expect(result.current.mics).toEqual([]);
  });

  it('«Повторить» запрашивает доступ заново, когда пользователь его разрешил', async () => {
    const fake = installFakeMediaDevices({ fail: { audio: 'NotAllowedError' } });
    const { result } = renderHook(() => useLocalMedia());
    await waitFor(() => expect(result.current.micStatus).toBe('unavailable'));

    delete fake.fail.audio;
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.micStatus).toBe('ready'));
    expect(result.current.micError).toBeNull();
  });

  it('подключили устройство – список обновляется по devicechange', async () => {
    const fake = installFakeMediaDevices({ devices: [CAM_A, MIC_A] });
    const { result } = renderHook(() => useLocalMedia());
    await waitFor(() => expect(result.current.cameras).toHaveLength(1));

    act(() => fake.setDevices([CAM_A, CAM_B, MIC_A]));
    await waitFor(() => expect(result.current.cameras).toHaveLength(2));
  });

  it('выключение камеры и микрофона меняет track.enabled без нового запроса', async () => {
    const fake = installFakeMediaDevices();
    const { result } = renderHook(() => useLocalMedia());
    await waitFor(() => expect(result.current.status).toBe('ready'));
    const calls = fake.getUserMedia.mock.calls.length;

    act(() => result.current.toggleCamera());
    act(() => result.current.toggleMic());
    expect(fake.tracks.find((t) => t.kind === 'video')?.enabled).toBe(false);
    expect(fake.tracks.find((t) => t.kind === 'audio')?.enabled).toBe(false);
    expect(fake.getUserMedia.mock.calls).toHaveLength(calls);
  });

  it('при размонтировании треки останавливаются', async () => {
    const fake = installFakeMediaDevices();
    const { result, unmount } = renderHook(() => useLocalMedia());
    await waitFor(() => expect(result.current.status).toBe('ready'));
    unmount();
    expect(fake.tracks.every((t) => t.stop.mock.calls.length > 0)).toBe(true);
  });

  it('без getUserMedia – status unsupported', () => {
    Object.defineProperty(navigator, 'mediaDevices', { value: undefined, configurable: true });
    const { result } = renderHook(() => useLocalMedia());
    expect(result.current.status).toBe('unsupported');
  });

  it('выбор динамика доступен только при поддержке setSinkId (нет в Firefox и Safari)', () => {
    installFakeMediaDevices();
    expect(renderHook(() => useLocalMedia()).result.current.speakerSupported).toBe(false);
    stubSinkIdSupport();
    expect(renderHook(() => useLocalMedia()).result.current.speakerSupported).toBe(true);
  });
});

describe('сообщения об ошибках устройств', () => {
  it.each([
    ['NotAllowedError', 'camera', /не дал доступ к камере/],
    ['NotAllowedError', 'mic', /не дал доступ к микрофону/],
    ['NotFoundError', 'camera', /Камера не найдена/],
    ['NotFoundError', 'mic', /Микрофон не найден/],
    ['NotReadableError', 'camera', /Камера занята другим приложением/],
    ['NotReadableError', 'mic', /Микрофон занят другим приложением/],
    ['Странное', 'mic', /Не удалось включить микрофон/],
  ] as const)('%s, %s', (name, kind, text) => {
    expect(describeMediaError(name, kind)).toMatch(text);
  });
});
