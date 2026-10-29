import { paths } from '@/shared/config/routes';
import type { RoomEntry } from '@/shared/lib/room-entry';

/**
 * Куда вести пользователя с экранов «вы вышли», «соединение потеряно» и им подобных, чтобы не было тупика:
 * организатору – к списку встреч, гостю – к приглашению. Если у гостя нет кода приглашения (в state лобби он
 * есть всегда, но state могли потерять), запасной вариант – корень приложения: он ведет на список встреч
 * или на экран входа.
 */
export function exitLink(
  entry: Pick<RoomEntry, 'role' | 'inviteCode'>,
  meeting: { invite_code?: string },
): { to: string; label: string } {
  if (entry.role === 'organizer') return { to: paths.meetings, label: 'К встречам' };
  const code = entry.inviteCode ?? meeting.invite_code;
  return code ? { to: paths.join(code), label: 'К приглашению' } : { to: '/', label: 'На главную' };
}
