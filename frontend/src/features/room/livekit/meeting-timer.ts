import { useEffect, useState } from 'react';

import { readJson, roomKey, writeJson } from './room-state';

/**
 * Момент начала встречи в миллисекундах. Источник – `started_at` из данных встречи (у организатора это ответ
 * `GET /meetings/{id}`). В ответе на вход гостя (`JoinResult.meeting`) этого поля по контракту нет, поэтому у
 * гостя начало оценивается по самому раннему входу участника в комнату LiveKit (`joinedAt`: первым в комнату
 * входит организатор) и запоминается во вкладке: после обновления страницы берется более раннее значение.
 */
export function estimateStart(input: {
  startedAt?: string | null;
  joinedAt: (Date | undefined)[];
  stored: number | null;
  /** Если больше ничего не известно – момент открытия страницы */
  fallback: number;
}): number {
  const server = input.startedAt ? Date.parse(input.startedAt) : Number.NaN;
  if (Number.isFinite(server)) return server;
  const candidates = input.joinedAt
    .map((date) => date?.getTime())
    .filter((t): t is number => t !== undefined && Number.isFinite(t));
  if (input.stored !== null) candidates.push(input.stored);
  return candidates.length > 0 ? Math.min(...candidates) : input.fallback;
}

function loadStored(meetingId: string): number | null {
  const value = readJson(roomKey.startedAt(meetingId));
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** Сколько секунд идет встреча: считается от начала встречи, а не от открытия страницы. */
export function useMeetingElapsed(
  meetingId: string,
  startedAt: string | null | undefined,
  joinedAt: (Date | undefined)[],
): number {
  const [stored] = useState(() => loadStored(meetingId));
  const [mountedAt] = useState(() => Date.now());
  const [now, setNow] = useState(mountedAt);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const start = estimateStart({ startedAt, joinedAt, stored, fallback: mountedAt });
  // Начало, выведенное из участников комнаты, запоминается: после обновления страницы оно не «сбросится»
  useEffect(() => {
    if (!startedAt) writeJson(roomKey.startedAt(meetingId), start);
  }, [meetingId, startedAt, start]);

  return Math.max(0, Math.floor((now - start) / 1000));
}
