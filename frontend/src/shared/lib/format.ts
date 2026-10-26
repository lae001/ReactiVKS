import type { Meeting } from '@/shared/api/types';

/** Дата и время встречи для списков: «2 окт., 14:30». */
export function formatDateTime(iso: string, timeZone?: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone,
  }).format(new Date(iso));
}

/** Когда встреча: для идущей – время начала, для запланированной – плановое, «без времени» – если нет ни того ни другого. */
export function formatMeetingWhen(m: Meeting, timeZone?: string): string {
  const at = m.started_at ?? m.scheduled_at;
  if (m.status === 'active' && at) return `Идет с ${formatDateTime(at, timeZone)}`;
  if (!at) return 'Без времени';
  return formatDateTime(at, timeZone);
}

/** Длительность в секундах: «4:05», «1:02:03». */
export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, '0');
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
}

/** Инициалы для аватара на плитке: «Анна Смирнова» → «АС». */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : parts;
  return letters
    .map((p) => p?.[0] ?? '')
    .join('')
    .toUpperCase();
}

/** Вероятность в проценты без дробной части: 0.713 → «71 %». */
export function formatPercent(p: number): string {
  return `${Math.round(p * 100)} %`;
}
