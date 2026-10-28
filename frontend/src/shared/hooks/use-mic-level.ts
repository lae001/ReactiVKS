import { useEffect, useState } from 'react';

/**
 * Уровень звука микрофона от 0 до 1 для индикатора в лобби (AnalyserNode, ~15 обновлений в секунду).
 * Выключенный микрофон (`track.enabled = false`) отдает тишину, и индикатор стоит на нуле.
 * Без Web Audio API (старые браузеры, jsdom) уровень всегда 0.
 */
export function useMicLevel(stream: MediaStream | null): number {
  const [level, setLevel] = useState(0);

  useEffect(() => {
    if (!stream || stream.getAudioTracks().length === 0 || typeof AudioContext === 'undefined') {
      return;
    }
    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const data = new Uint8Array(analyser.fftSize);

    const timer = setInterval(() => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (const v of data) sum += ((v - 128) / 128) ** 2;
      // RMS растет медленно: речь обычно дает 0.05–0.3, поэтому усиливаем
      setLevel(Math.min(1, Math.sqrt(sum / data.length) * 3));
    }, 66);

    return () => {
      clearInterval(timer);
      setLevel(0);
      void ctx.close();
    };
  }, [stream]);

  return level;
}
