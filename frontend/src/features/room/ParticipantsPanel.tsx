import { Mic, MicOff, UserX, VideoOff } from 'lucide-react';

import type { ConsentState } from '@/shared/api/types';
import { initials } from '@/shared/lib/format';
import { cn } from '@/shared/lib/utils';
import { Button } from '@/shared/ui/button';

import type { RoomParticipant } from './types';

const CONSENT_LABEL: Record<ConsentState, string | null> = {
  granted: 'Анализ разрешен',
  denied: 'Без анализа',
  revoked: 'Анализ отключен',
  not_required: null,
};

/**
 * Вкладка «Участники». Организатор видит статус согласия каждого и модерирует
 * (REST meeting-service – EMO-75); участник видит только свой статус.
 */
export function ParticipantsPanel({
  participants,
  canModerate,
  onMute,
  onMuteCamera,
  onRemove,
}: {
  participants: RoomParticipant[];
  canModerate: boolean;
  onMute: (id: string) => void;
  /** Кнопка «Выключить камеру» – только в комнате на LiveKit */
  onMuteCamera?: (id: string) => void;
  onRemove: (id: string) => void;
}) {
  return (
    <ul className="flex flex-col gap-1">
      {participants.map((p) => {
        const consent = canModerate || p.isSelf ? CONSENT_LABEL[p.consent] : null;
        return (
          <li key={p.id} className="flex items-center gap-3 rounded-lg px-2 py-2">
            <span
              className="flex size-9 shrink-0 items-center justify-center rounded-full bg-room-border text-sm font-medium"
              aria-hidden
            >
              {initials(p.name)}
            </span>
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-sm font-medium">
                {p.name}
                {p.isSelf && <span className="font-normal text-room-muted"> (вы)</span>}
              </span>
              <span className="truncate text-xs text-room-muted">
                {[p.role === 'organizer' ? 'Организатор' : null, consent]
                  .filter(Boolean)
                  .join(' · ') || 'Участник'}
              </span>
            </span>
            {p.micOn ? (
              <Mic className="size-4 shrink-0 text-room-muted" aria-label="Микрофон включен" />
            ) : (
              <MicOff className="size-4 shrink-0 text-destructive" aria-label="Микрофон выключен" />
            )}
            {canModerate && !p.isSelf && (
              <span className="flex shrink-0 gap-1">
                <Button
                  variant="room"
                  size="icon"
                  className={cn('size-8', !p.micOn && 'invisible')}
                  onClick={() => onMute(p.id)}
                  aria-label={`Выключить микрофон: ${p.name}`}
                  title="Выключить микрофон"
                >
                  <MicOff />
                </Button>
                {onMuteCamera && (
                  <Button
                    variant="room"
                    size="icon"
                    className={cn('size-8', !p.cameraOn && 'invisible')}
                    onClick={() => onMuteCamera(p.id)}
                    aria-label={`Выключить камеру: ${p.name}`}
                    title="Выключить камеру"
                  >
                    <VideoOff />
                  </Button>
                )}
                <Button
                  variant="room"
                  size="icon"
                  className="size-8 hover:bg-destructive hover:text-destructive-foreground"
                  onClick={() => onRemove(p.id)}
                  aria-label={`Удалить из встречи: ${p.name}`}
                  title="Удалить из встречи"
                >
                  <UserX />
                </Button>
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
