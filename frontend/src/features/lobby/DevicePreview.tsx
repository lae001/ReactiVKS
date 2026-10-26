import { CameraOff, LoaderCircle, Mic, MicOff, Video, VideoOff } from 'lucide-react';

import type { LocalMedia } from '@/shared/hooks/use-local-media';
import { initials } from '@/shared/lib/format';
import { Button } from '@/shared/ui/button';
import { LocalVideo } from '@/shared/ui/local-video';

/** Левая колонка лобби: превью камеры и переключатели устройств. */
export function DevicePreview({ media, displayName }: { media: LocalMedia; displayName: string }) {
  const { status, stream, error, cameraOn, micOn, toggleCamera, toggleMic } = media;
  const showVideo = status === 'ready' && stream && cameraOn;
  const canToggle = status === 'ready';

  return (
    <div className="flex flex-col gap-3">
      <div className="relative aspect-video overflow-hidden rounded-xl bg-room text-room-muted">
        {showVideo ? (
          <LocalVideo stream={stream} />
        ) : (
          <div className="flex size-full flex-col items-center justify-center gap-3 text-sm">
            {status === 'pending' ? (
              <>
                <LoaderCircle className="size-6 animate-spin" aria-hidden />
                Включаем камеру…
              </>
            ) : displayName.trim() && status === 'ready' ? (
              <span className="flex size-20 items-center justify-center rounded-full bg-room-surface text-2xl font-medium text-room-foreground">
                {initials(displayName)}
              </span>
            ) : (
              <>
                <CameraOff className="size-6" aria-hidden />
                {status === 'ready' ? 'Камера выключена' : 'Камера недоступна'}
              </>
            )}
          </div>
        )}

        <div className="absolute inset-x-0 bottom-0 flex justify-center gap-2 bg-gradient-to-t from-room/80 to-transparent p-3">
          <Button
            type="button"
            variant={micOn ? 'room' : 'destructive'}
            size="icon"
            onClick={toggleMic}
            disabled={!canToggle}
            aria-pressed={micOn}
            aria-label={micOn ? 'Выключить микрофон' : 'Включить микрофон'}
          >
            {micOn ? <Mic /> : <MicOff />}
          </Button>
          <Button
            type="button"
            variant={cameraOn ? 'room' : 'destructive'}
            size="icon"
            onClick={toggleCamera}
            disabled={!canToggle}
            aria-pressed={cameraOn}
            aria-label={cameraOn ? 'Выключить камеру' : 'Включить камеру'}
          >
            {cameraOn ? <Video /> : <VideoOff />}
          </Button>
        </div>
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {status === 'ready' && (
        <p className="text-sm text-muted-foreground">
          Так вас увидят участники. Камеру и микрофон можно выключить и позже, во время встречи.
        </p>
      )}
    </div>
  );
}
