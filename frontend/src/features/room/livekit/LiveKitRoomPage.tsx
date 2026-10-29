import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';

import { guestErrorMessage, meetingErrorMessage } from '@/features/meetings/errors';
import { meetingsApi } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';
import type { RoomEntry } from '@/shared/lib/room-entry';
import { Button } from '@/shared/ui/button';

import { CancelLink } from '../CancelLink';
import { RoomMessage } from '../RoomMessage';

import { exitLink } from './exit-link';
import { type LiveKitMeeting, LiveKitRoomView, type RoomConnection } from './LiveKitRoomView';

/**
 * Свежий токен LiveKit при каждом входе в комнату и при каждом «Подключиться снова»: гость через
 * rejoin (Participant-токен), организатор через вход. Токен из ответа лобби в state не передается:
 * иначе удаленный гость мог бы вернуться в комнату перезагрузкой страницы (удаление блокирует
 * именно rejoin, `participant_removed`).
 */
async function fetchConnection(meeting: LiveKitMeeting, entry: RoomEntry): Promise<RoomConnection> {
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
export function LiveKitRoomPage({ meeting, entry }: { meeting: LiveKitMeeting; entry: RoomEntry }) {
  // каждый номер попытки – новый запрос токена
  const [attempt, setAttempt] = useState(0);
  const query = useQuery({
    queryKey: ['room-connection', meeting.id, entry.role, attempt],
    queryFn: () => fetchConnection(meeting, entry),
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
  });

  if (query.isError) {
    const error = query.error;
    const code = error instanceof ApiError ? error.code : '';
    const removed = code === 'participant_removed';
    const ended = code === 'meeting_ended' || code === 'meeting_cancelled';
    // встреча чужая или удалена: `not_found` (контракт не различает эти случаи) – повтор не поможет
    const noAccess = entry.role === 'organizer' && (code === 'not_found' || code === 'forbidden');
    const retryable = !removed && !ended && !noAccess && code !== 'unauthorized';
    const exit = exitLink(entry);
    const exitButton = (
      <Button asChild variant="room">
        <Link to={exit.to}>{exit.label}</Link>
      </Button>
    );
    return (
      <RoomMessage
        title={
          removed
            ? 'Вас удалили из встречи'
            : ended
              ? 'Встреча завершена'
              : noAccess
                ? 'Встреча не найдена'
                : 'Не удалось подключиться к встрече'
        }
        text={
          noAccess
            ? 'Встреча не найдена или у вас нет к ней доступа.'
            : entry.role === 'guest'
              ? guestErrorMessage(error, 'подключиться к встрече')
              : meetingErrorMessage(error, 'подключиться к встрече')
        }
        action={
          retryable ? (
            <Button variant="room" onClick={() => setAttempt((n) => n + 1)}>
              Повторить
            </Button>
          ) : (
            exitButton
          )
        }
        secondary={retryable ? exitButton : undefined}
      />
    );
  }
  if (!query.data) {
    return (
      <RoomMessage
        title="Входим во встречу…"
        text="Подключаемся к видеосерверу."
        action={<CancelLink role={entry.role} />}
      />
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
