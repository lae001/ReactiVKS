import { useCallback, useEffect, useState } from 'react';

export type LocalMediaStatus = 'pending' | 'ready' | 'unsupported' | 'error';

export interface LocalMedia {
  status: LocalMediaStatus;
  stream: MediaStream | null;
  /** Понятное пользователю сообщение при status = error */
  error: string | null;
  cameraOn: boolean;
  micOn: boolean;
  toggleCamera: () => void;
  toggleMic: () => void;
}

/** Сообщение по имени ошибки getUserMedia (docs/frontend/ui-kit.md, раздел 6). */
export function describeMediaError(name: string): string {
  switch (name) {
    case 'NotAllowedError':
      return 'Браузер не дал доступ к камере и микрофону. Разрешите доступ в настройках сайта и обновите страницу.';
    case 'NotFoundError':
      return 'Камера или микрофон не найдены. Подключите устройство – или войдите без него.';
    case 'NotReadableError':
      return 'Камера или микрофон заняты другим приложением. Закройте его и обновите страницу.';
    default:
      return 'Не удалось включить камеру и микрофон. Обновите страницу или попробуйте другой браузер.';
  }
}

/**
 * Локальные камера и микрофон для превью в лобби и своей плитки в комнате.
 * Выключение – через `track.enabled`, без повторного запроса разрешения;
 * в комнате на LiveKit (EMO-75) управление перейдет к localParticipant.
 */
export function useLocalMedia({
  initialCamera = true,
  initialMic = true,
}: { initialCamera?: boolean; initialMic?: boolean } = {}): LocalMedia {
  const supported = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia;
  const [status, setStatus] = useState<LocalMediaStatus>(supported ? 'pending' : 'unsupported');
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cameraOn, setCameraOn] = useState(initialCamera);
  const [micOn, setMicOn] = useState(initialMic);

  useEffect(() => {
    if (!supported) return;
    let cancelled = false;
    let acquired: MediaStream | null = null;

    navigator.mediaDevices
      .getUserMedia({ video: true, audio: true })
      .then((s) => {
        acquired = s;
        if (cancelled) {
          s.getTracks().forEach((t) => t.stop());
          return;
        }
        setStream(s);
        setStatus('ready');
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(describeMediaError(e instanceof Error ? e.name : ''));
        setStatus('error');
      });

    return () => {
      cancelled = true;
      acquired?.getTracks().forEach((t) => t.stop());
    };
  }, [supported]);

  useEffect(() => {
    stream?.getVideoTracks().forEach((t) => (t.enabled = cameraOn));
  }, [stream, cameraOn]);

  useEffect(() => {
    stream?.getAudioTracks().forEach((t) => (t.enabled = micOn));
  }, [stream, micOn]);

  const toggleCamera = useCallback(() => setCameraOn((v) => !v), []);
  const toggleMic = useCallback(() => setMicOn((v) => !v), []);

  return { status, stream, error, cameraOn, micOn, toggleCamera, toggleMic };
}
