import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';

import { guestErrorMessage, meetingErrorMessage } from '@/features/meetings/errors';
import { meetingsApi } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';
import { paths } from '@/shared/config/routes';
import type { RoomEntry } from '@/shared/lib/room-entry';
import { Button } from '@/shared/ui/button';

import { RoomMessage } from '../RoomMessage';

import { type LiveKitMeeting, LiveKitRoomView, type RoomConnection } from './LiveKitRoomView';

/**
 * Токен LiveKit: при первом входе – из ответа лобби (`entry.livekit`), иначе и при каждом
 * «Подключиться снова» – новый: гость через rejoin (Participant-токен), организатор через вход.
 */
async function fetchConnection(
  meeting: LiveKitMeeting & { analysis_enabled: boolean },
  entry: RoomEntry,
): Promise<RoomConnection> {
  const result =
    entry.role === 'guest'
      ? await meetingsApi.rejoin()
      : await meetingsApi.joinAsOrganizer(
          meeting.id,
          meeting.analysis_enabled
            ? entry.consent === 'granted'
              ? 'granted'
              : 'denied'
            : undefined,
        );
  return { url: result.livekit_url, token: result.livekit_token };
}

/** Получает токен и открывает комнату на LiveKit; ошибки входа показывает отдельными экранами. */
export function LiveKitRoomPage({
  meeting,
  entry,
}: {
  meeting: LiveKitMeeting & { analysis_enabled: boolean };
  entry: RoomEntry;
}) {
  // 0 – первый вход (токен из лобби, если он есть); дальше каждый номер – новый запрос токена
  const [attempt, setAttempt] = useState(0);
  const query = useQuery({
    queryKey: ['room-connection', meeting.id, entry.role, attempt],
    queryFn: () =>
      attempt === 0 && entry.livekit
        ? Promise.resolve(entry.livekit)
        : fetchConnection(meeting, entry),
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
  });

  if (query.isError) {
    const error = query.error;
    const code = error instanceof ApiError ? error.code : '';
    const removed = code === 'participant_removed';
    const ended = code === 'meeting_ended' || code === 'meeting_cancelled';
    const retryable = !removed && !ended && code !== 'unauthorized';
    return (
      <RoomMessage
        title={
          removed
            ? 'Вас удалили из встречи'
            : ended
              ? 'Встреча завершена'
              : 'Не удалось подключиться к встрече'
        }
        text={
          entry.role === 'guest'
            ? guestErrorMessage(error, 'подключиться к встрече')
            : meetingErrorMessage(error, 'подключиться к встрече')
        }
        action={
          retryable ? (
            <Button variant="room" onClick={() => setAttempt((n) => n + 1)}>
              Повторить
            </Button>
          ) : (
            <Button asChild variant="room">
              <Link
                to={entry.role === 'guest' ? paths.join(entry.inviteCode ?? '') : paths.meetings}
              >
                {entry.role === 'guest' ? 'К приглашению' : 'К встречам'}
              </Link>
            </Button>
          )
        }
      />
    );
  }
  if (!query.data) {
    return (
      <RoomMessage title="Входим во встречу…" text="Подключаемся к видеосерверу." action={null} />
    );
  }
  return (
    <LiveKitRoomView
      meeting={meeting}
      entry={entry}
      connection={query.data}
      onReconnect={() => setAttempt((n) => n + 1)}
    />
  );
}
