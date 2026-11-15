import { paths } from '@/shared/config/routes';
import type { RoomEntry } from '@/shared/lib/room-entry';

/**
 * Куда вести пользователя с экранов «вы вышли», «соединение потеряно» и им подобных, чтобы не было тупика:
 * организатору – к списку встреч, гостю – на главную («/»: оттуда для него путь на экран входа). Ссылка-приглашение
 * гостю не предлагается: после завершения встречи или удаления она уже не действует.
 */
export function exitLink(entry: Pick<RoomEntry, 'role'>): { to: string; label: string } {
  return entry.role === 'organizer'
    ? { to: paths.meetings, label: 'К встречам' }
    : { to: '/', label: 'На главную' };
}
