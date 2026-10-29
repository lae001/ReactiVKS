import { CameraOff, LoaderCircle, Mic, MicOff, Video, VideoOff, Volume2 } from 'lucide-react';
import { useState } from 'react';

import type { LocalMedia } from '@/shared/hooks/use-local-media';
import { initials } from '@/shared/lib/format';
import { playTestTone } from '@/shared/lib/test-tone';
import { Button } from '@/shared/ui/button';
import { LocalVideo } from '@/shared/ui/local-video';

import { DeviceSelect } from './DeviceSelect';
import { MicLevel } from './MicLevel';

/** Левая колонка лобби: превью камеры, переключатели, выбор устройств и уровень микрофона. */
export function DevicePreview({ media, displayName }: { media: LocalMedia; displayName: string }) {
  const { stream, cameraStatus, micStatus, cameraOn, micOn } = media;
  const showVideo = cameraStatus === 'ready' && stream && cameraOn;
  const [toneError, setToneError] = useState(false);
  const errors = [media.cameraError, media.micError].filter((e): e is string => e !== null);

  async function checkSpeaker() {
    setToneError(false);
    try {
      await playTestTone(media.speakerId);
    } catch {
      setToneError(true);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="relative aspect-video overflow-hidden rounded-xl bg-room text-room-muted">
        {showVideo ? (
          <LocalVideo stream={stream} />
        ) : (
          <div className="flex size-full flex-col items-center justify-center gap-3 text-sm">
            {cameraStatus === 'pending' ? (
              <>
                <LoaderCircle className="size-6 animate-spin" aria-hidden />
                Включаем камеру…
              </>
            ) : displayName.trim() && cameraStatus === 'ready' ? (
              <span className="flex size-20 items-center justify-center rounded-full bg-room-surface text-2xl font-medium text-room-foreground">
                {initials(displayName)}
              </span>
            ) : (
              <>
                <CameraOff className="size-6" aria-hidden />
                {cameraStatus === 'ready' ? 'Камера выключена' : 'Камера недоступна'}
              </>
            )}
          </div>
        )}

        <div className="absolute inset-x-0 bottom-0 flex justify-center gap-2 bg-gradient-to-t from-room/80 to-transparent p-3">
          <Button
            type="button"
            variant={micOn ? 'room' : 'destructive'}
            size="icon"
            onClick={media.toggleMic}
            disabled={micStatus !== 'ready'}
            aria-pressed={micOn}
            aria-label={micOn ? 'Выключить микрофон' : 'Включить микрофон'}
          >
            {micOn ? <Mic /> : <MicOff />}
          </Button>
          <Button
            type="button"
            variant={cameraOn ? 'room' : 'destructive'}
            size="icon"
            onClick={media.toggleCamera}
            disabled={cameraStatus !== 'ready'}
            aria-pressed={cameraOn}
            aria-label={cameraOn ? 'Выключить камеру' : 'Включить камеру'}
          >
            {cameraOn ? <Video /> : <VideoOff />}
          </Button>
        </div>
      </div>

      {errors.length > 0 && (
        <div role="alert" className="flex flex-col items-start gap-2 text-sm text-destructive">
          {errors.map((e) => (
            <p key={e}>{e}</p>
          ))}
          <Button type="button" variant="outline" size="sm" onClick={media.retry}>
            Повторить
          </Button>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <DeviceSelect
          label="Камера"
          options={media.cameras}
          value={media.cameraId}
          onChange={media.selectCamera}
          disabled={cameraStatus !== 'ready'}
          emptyText="Камера не найдена"
        />
        <div className="flex flex-col gap-1.5">
          <DeviceSelect
            label="Микрофон"
            options={media.mics}
            value={media.micId}
            onChange={media.selectMic}
            disabled={micStatus !== 'ready'}
            emptyText="Микрофон не найден"
          />
          {micStatus === 'ready' && <MicLevel stream={media.micStream} />}
        </div>
        {media.speakerSupported ? (
          <div className="flex items-end gap-2 sm:col-span-2">
            <div className="flex-1">
              <DeviceSelect
                label="Динамик"
                options={media.speakers}
                value={media.speakerId}
                onChange={media.selectSpeaker}
                emptyText="Динамик по умолчанию"
              />
            </div>
            <Button type="button" variant="outline" onClick={() => void checkSpeaker()}>
              <Volume2 /> Проверить звук
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground sm:col-span-2">
            Выбрать динамик можно только в Chrome и Edge. В вашем браузере звук идет в динамик,
            выбранный в настройках системы.
          </p>
        )}
        {toneError && (
          <p role="alert" className="text-sm text-destructive sm:col-span-2">
            Не удалось воспроизвести тестовый звук. Проверьте, что динамик подключен и звук не
            выключен.
          </p>
        )}
      </div>

      {media.status === 'ready' && errors.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Так вас увидят участники. Камеру и микрофон можно выключить и позже, во время встречи.
        </p>
      )}
    </div>
  );
}
