import { useEffect, useState } from 'react';

/** Текущее время (`Date.now()`), пока не наступит `until`: раз в 250 мс, чтобы «Подождите N с» убывало. */
export function useNow(until: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (until <= Date.now()) return;
    const timer = setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (current >= until) clearInterval(timer);
    }, 250);
    return () => clearInterval(timer);
  }, [until]);
  return now;
}

/** Сколько целых секунд осталось до `until`, но не больше `max`. */
export function secondsLeft(until: number, now: number, max = 10): number {
  return Math.min(max, Math.max(0, Math.ceil((until - now) / 1000)));
}
