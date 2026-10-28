import { useMutation } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';

import { type GuestJoinResult, meetingsApi } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';

type JoinBody = Parameters<typeof meetingsApi.joinMeeting>[1];

/** Как часто повторяем вход, пока встреча не началась (docs/architecture/03-scenarios.md, UC-3). */
export const POLL_INTERVAL_MS = 5_000;
/** Сколько ждем начала встречи, потом просим пользователя решить самому. */
export const WAIT_LIMIT_MS = 10 * 60_000;

/**
 * Ошибки, после которых повторять вход бессмысленно: показываем отдельный экран вместо формы.
 * Остальные коды показываются сообщением под формой.
 */
const TERMINAL_CODES = new Set([
  'meeting_ended',
  'meeting_cancelled',
  'participant_removed',
  'not_found',
  'forbidden',
  'user_blocked',
]);

/** Временные сбои: при ожидании не прерываем опрос, а пробуем еще раз. */
function isTransient(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.code === 'network_error' ||
      error.code === 'too_many_requests' ||
      error.code === 'livekit_unavailable' ||
      error.status >= 500)
  );
}

export type JoinPhase = 'idle' | 'waiting' | 'timed_out';

interface Poll {
  body: JoinBody;
  since: number;
  delay: number;
}

/**
 * Вход в лобби: `POST /join/{code}`. Если встреча еще не началась (`meeting_not_started`),
 * повторяет вход каждые 5 секунд, но не дольше 10 минут. Ожидание можно отменить – ответ уже
 * отправленного запроса тогда игнорируется. Клиент не зависит от порядка проверок на сервере:
 * любой код ответа на любом шаге приводит либо к экрану (`terminal`), либо к `onFailed`.
 */
export function useJoinFlow({
  inviteCode,
  onJoined,
  onFailed,
}: {
  inviteCode: string;
  onJoined: (result: GuestJoinResult) => void;
  onFailed: (error: unknown) => void;
}) {
  const [phase, setPhase] = useState<JoinPhase>('idle');
  const [terminal, setTerminal] = useState<ApiError | null>(null);
  const [poll, setPoll] = useState<Poll | null>(null);
  // номер «прогона»: отмена и новая отправка делают ответы старых запросов недействительными
  const run = useRef(0);

  // колбэки страницы всегда свежие, а сам вход от их смены не пересоздается
  const handlers = useRef({ onJoined, onFailed });
  useEffect(() => {
    handlers.current = { onJoined, onFailed };
  });

  const join = useMutation({
    mutationFn: (body: JoinBody) => meetingsApi.joinMeeting(inviteCode, body),
  });
  const { mutate } = join;

  const attempt = useCallback(
    (body: JoinBody, since: number | null) => {
      const id = run.current;
      mutate(body, {
        onSuccess: (result) => {
          if (id !== run.current) return;
          setPoll(null);
          setPhase('idle');
          handlers.current.onJoined(result);
        },
        onError: (error) => {
          if (id !== run.current) return;
          if (error instanceof ApiError && error.code === 'meeting_not_started') {
            setPhase('waiting');
            setPoll({ body, since: since ?? Date.now(), delay: POLL_INTERVAL_MS });
            return;
          }
          if (since !== null && isTransient(error)) {
            const wait = error instanceof ApiError ? (error.retryAfter ?? 0) * 1000 : 0;
            setPoll({ body, since, delay: Math.max(POLL_INTERVAL_MS, wait) });
            return;
          }
          setPoll(null);
          setPhase('idle');
          if (error instanceof ApiError && TERMINAL_CODES.has(error.code)) setTerminal(error);
          else handlers.current.onFailed(error);
        },
      });
    },
    [mutate],
  );

  useEffect(() => {
    if (!poll) return;
    const timer = setTimeout(() => {
      if (Date.now() - poll.since >= WAIT_LIMIT_MS) {
        setPoll(null);
        setPhase('timed_out');
        return;
      }
      attempt(poll.body, poll.since);
    }, poll.delay);
    return () => clearTimeout(timer);
  }, [poll, attempt]);

  return {
    phase,
    terminal,
    pending: join.isPending,
    submit(body: JoinBody) {
      run.current += 1;
      setTerminal(null);
      setPhase('idle');
      attempt(body, null);
    },
    cancel() {
      run.current += 1;
      setPoll(null);
      setPhase('idle');
    },
  };
}
