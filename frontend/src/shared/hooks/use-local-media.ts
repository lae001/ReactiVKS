import { useCallback, useEffect, useState } from 'react';

import { loadDevicePrefs, saveDevicePrefs } from '@/shared/lib/device-prefs';

/** Общее состояние: нет getUserMedia, идет первый запрос или хотя бы один запрос завершен. */
export type LocalMediaStatus = 'pending' | 'ready' | 'unsupported';
export type DeviceStatus = 'pending' | 'ready' | 'unavailable';

export interface DeviceOption {
  id: string;
  label: string;
}

export interface LocalMedia {
  status: LocalMediaStatus;
  /** Видео своей камеры для превью; null, пока камеры нет */
  stream: MediaStream | null;
  /** Звук микрофона для индикатора уровня; null, пока микрофона нет */
  micStream: MediaStream | null;
  cameraStatus: DeviceStatus;
  micStatus: DeviceStatus;
  /** Понятные пользователю сообщения о запрете доступа или отсутствии устройства */
  cameraError: string | null;
  micError: string | null;
  cameraOn: boolean;
  micOn: boolean;
  toggleCamera: () => void;
  toggleMic: () => void;
  cameras: DeviceOption[];
  mics: DeviceOption[];
  speakers: DeviceOption[];
  /** Идентификаторы выбранных устройств; '' – ничего не выбрано */
  cameraId: string;
  micId: string;
  speakerId: string;
  selectCamera: (id: string) => void;
  selectMic: (id: string) => void;
  selectSpeaker: (id: string) => void;
  /** Динамик выбирается через setSinkId, его нет в Firefox и Safari */
  speakerSupported: boolean;
  /** Повторить запрос доступа (после того как пользователь разрешил его в браузере) */
  retry: () => void;
}

type Kind = 'camera' | 'mic';

const SUBJECT: Record<Kind, { to: string; name: string }> = {
  camera: { to: 'камере', name: 'Камера' },
  mic: { to: 'микрофону', name: 'Микрофон' },
};

/** Сообщение по имени ошибки getUserMedia (docs/frontend/ui-kit.md, раздел 6). */
export function describeMediaError(name: string, kind: Kind): string {
  const s = SUBJECT[kind];
  switch (name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return `Браузер не дал доступ к ${s.to}. Разрешите доступ в настройках сайта (значок слева от адреса) и нажмите «Повторить».`;
    case 'NotFoundError':
    case 'OverconstrainedError':
      return `${s.name} не найден${kind === 'camera' ? 'а' : ''}. Подключите устройство и нажмите «Повторить» – или войдите без него.`;
    case 'NotReadableError':
    case 'AbortError':
      return `${s.name} занят${kind === 'camera' ? 'а' : ''} другим приложением. Закройте его и нажмите «Повторить».`;
    default:
      return `Не удалось включить ${kind === 'camera' ? 'камеру' : 'микрофон'}. Нажмите «Повторить» или попробуйте другой браузер.`;
  }
}

async function open(kind: Kind, deviceId: string): Promise<MediaStream> {
  const track = (exact: boolean) => (exact ? { deviceId: { exact: deviceId } } : true);
  const request = (exact: boolean): MediaStreamConstraints =>
    kind === 'camera' ? { video: track(exact) } : { audio: track(exact) };
  try {
    return await navigator.mediaDevices.getUserMedia(request(deviceId !== ''));
  } catch (e) {
    // сохраненное устройство отключили – берем устройство по умолчанию
    const missing =
      e instanceof Error && ['OverconstrainedError', 'NotFoundError'].includes(e.name);
    if (deviceId !== '' && missing) return navigator.mediaDevices.getUserMedia(request(false));
    throw e;
  }
}

function toOptions(list: MediaDeviceInfo[], kind: MediaDeviceKind, fallback: string) {
  return list
    .filter((d) => d.kind === kind && d.deviceId !== '')
    .map((d, i) => ({ id: d.deviceId, label: d.label || `${fallback} ${i + 1}` }));
}

/**
 * Локальные камера и микрофон для превью в лобби и своей плитки в комнате.
 * Камера и микрофон запрашиваются отдельно: если одного устройства нет или доступ к нему закрыт,
 * второе продолжает работать. Выбор устройства запоминается (localStorage). Выключение – через
 * `track.enabled`, без повторного запроса разрешения; в комнате на LiveKit управление перейдет
 * к localParticipant.
 */
export function useLocalMedia({
  initialCamera = true,
  initialMic = true,
}: { initialCamera?: boolean; initialMic?: boolean } = {}): LocalMedia {
  const supported = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia;
  const speakerSupported =
    typeof HTMLMediaElement !== 'undefined' && 'setSinkId' in HTMLMediaElement.prototype;

  const [prefs] = useState(loadDevicePrefs);
  // wanted – выбор пользователя (меняет запрос), actual – устройство, которое реально открылось
  const [wanted, setWanted] = useState({ camera: prefs.cameraId ?? '', mic: prefs.micId ?? '' });
  const [actual, setActual] = useState({ camera: '', mic: '' });
  const [speakerId, setSpeakerId] = useState(prefs.speakerId ?? '');
  const [attempt, setAttempt] = useState(0);

  const [videoStream, setVideoStream] = useState<MediaStream | null>(null);
  const [micStream, setMicStream] = useState<MediaStream | null>(null);
  const [cameraStatus, setCameraStatus] = useState<DeviceStatus>(
    supported ? 'pending' : 'unavailable',
  );
  const [micStatus, setMicStatus] = useState<DeviceStatus>(supported ? 'pending' : 'unavailable');
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [micError, setMicError] = useState<string | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [cameraOn, setCameraOn] = useState(initialCamera);
  const [micOn, setMicOn] = useState(initialMic);

  const refreshDevices = useCallback(async () => {
    try {
      setDevices(await navigator.mediaDevices.enumerateDevices());
    } catch {
      // список устройств недоступен – остаются только устройства по умолчанию
    }
  }, []);

  useEffect(() => {
    if (!supported) return;
    const md = navigator.mediaDevices;
    Promise.resolve()
      .then(() => md.enumerateDevices())
      .then(setDevices, () => undefined);
    md.addEventListener?.('devicechange', refreshDevices);
    return () => md.removeEventListener?.('devicechange', refreshDevices);
  }, [supported, refreshDevices]);

  // одна и та же логика для камеры и микрофона
  const acquire = useCallback(
    (
      kind: Kind,
      deviceId: string,
      set: {
        stream: (s: MediaStream | null) => void;
        status: (s: DeviceStatus) => void;
        error: (e: string | null) => void;
      },
    ) => {
      let cancelled = false;
      let acquired: MediaStream | null = null;
      open(kind, deviceId)
        .then((s) => {
          acquired = s;
          if (cancelled) {
            s.getTracks().forEach((t) => t.stop());
            return;
          }
          const track = (kind === 'camera' ? s.getVideoTracks() : s.getAudioTracks())[0];
          setActual((a) => ({ ...a, [kind]: track?.getSettings?.().deviceId ?? '' }));
          set.stream(s);
          set.error(null);
          set.status('ready');
          void refreshDevices(); // подписи устройств появляются только после выдачи доступа
        })
        .catch((e: unknown) => {
          if (cancelled) return;
          set.stream(null);
          set.error(describeMediaError(e instanceof Error ? e.name : '', kind));
          set.status('unavailable');
        });
      return () => {
        cancelled = true;
        acquired?.getTracks().forEach((t) => t.stop());
      };
    },
    [refreshDevices],
  );

  useEffect(() => {
    if (!supported) return;
    return acquire('camera', wanted.camera, {
      stream: setVideoStream,
      status: setCameraStatus,
      error: setCameraError,
    });
  }, [supported, acquire, wanted.camera, attempt]);

  useEffect(() => {
    if (!supported) return;
    return acquire('mic', wanted.mic, {
      stream: setMicStream,
      status: setMicStatus,
      error: setMicError,
    });
  }, [supported, acquire, wanted.mic, attempt]);

  useEffect(() => {
    videoStream?.getVideoTracks().forEach((t) => (t.enabled = cameraOn));
  }, [videoStream, cameraOn]);

  useEffect(() => {
    micStream?.getAudioTracks().forEach((t) => (t.enabled = micOn));
  }, [micStream, micOn]);

  const cameras = toOptions(devices, 'videoinput', 'Камера');
  const mics = toOptions(devices, 'audioinput', 'Микрофон');
  const speakers = toOptions(devices, 'audiooutput', 'Динамик');
  const pick = (list: DeviceOption[], ...ids: string[]) =>
    ids.find((id) => id !== '' && list.some((d) => d.id === id)) ?? list[0]?.id ?? '';

  const status: LocalMediaStatus = !supported
    ? 'unsupported'
    : cameraStatus === 'pending' || micStatus === 'pending'
      ? 'pending'
      : 'ready';

  return {
    status,
    stream: videoStream,
    micStream,
    cameraStatus,
    micStatus,
    cameraError,
    micError,
    cameraOn,
    micOn,
    toggleCamera: useCallback(() => setCameraOn((v) => !v), []),
    toggleMic: useCallback(() => setMicOn((v) => !v), []),
    cameras,
    mics,
    speakers,
    cameraId: pick(cameras, actual.camera, wanted.camera),
    micId: pick(mics, actual.mic, wanted.mic),
    speakerId: pick(speakers, speakerId),
    selectCamera: (id) => {
      saveDevicePrefs({ cameraId: id });
      setWanted((w) => ({ ...w, camera: id }));
    },
    selectMic: (id) => {
      saveDevicePrefs({ micId: id });
      setWanted((w) => ({ ...w, mic: id }));
    },
    selectSpeaker: (id) => {
      saveDevicePrefs({ speakerId: id });
      setSpeakerId(id);
    },
    speakerSupported,
    retry: () => {
      setCameraStatus('pending');
      setMicStatus('pending');
      setAttempt((n) => n + 1);
    },
  };
}
