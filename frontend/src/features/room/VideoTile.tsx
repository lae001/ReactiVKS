import { MicOff } from 'lucide-react';
import type { ReactNode } from 'react';

import { initials } from '@/shared/lib/format';
import { LocalVideo } from '@/shared/ui/local-video';

import type { RoomParticipant } from './types';

/** Плитка участника: видео или инициалы, имя в углу, индикатор эмоции сверху (только у организатора). */
export function VideoTile({
  participant,
  stream,
  overlay,
}: {
  participant: RoomParticipant;
  /** Своя камера; видео остальных участников – с LiveKit (EMO-75) */
  stream?: MediaStream | null;
  overlay?: ReactNode;
}) {
  const showVideo = participant.isSelf && participant.cameraOn && stream;

  return (
    <figure className="relative flex min-h-32 items-center justify-center overflow-hidden rounded-lg border border-room-border bg-room-surface">
      {showVideo ? (
        <LocalVideo stream={stream} className="absolute inset-0" />
      ) : (
        <span
          className="flex size-16 items-center justify-center rounded-full bg-room-border text-xl font-medium md:size-20 md:text-2xl"
          aria-hidden
        >
          {initials(participant.name)}
        </span>
      )}

      {overlay && <div className="absolute top-2 left-2">{overlay}</div>}

      <figcaption className="absolute bottom-2 left-2 flex max-w-[calc(100%-1rem)] items-center gap-1.5 rounded-md bg-room/85 px-2 py-1 text-xs">
        {!participant.micOn && (
          <MicOff className="size-3.5 shrink-0 text-destructive" aria-label="Микрофон выключен" />
        )}
        <span className="truncate">
          {participant.name}
          {participant.isSelf && ' (вы)'}
        </span>
      </figcaption>
    </figure>
  );
}
