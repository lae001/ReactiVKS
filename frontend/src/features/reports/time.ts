/** Секунды от начала встречи для метки времени. */
export function secondsFromStart(ts: string, startedAt: string): number {
  return (Date.parse(ts) - Date.parse(startedAt)) / 1000;
}
