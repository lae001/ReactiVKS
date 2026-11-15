import { meetingsApi } from '@/shared/api/meetings';
import type { ConsentState, Meeting } from '@/shared/api/meetings';

/** Повторный вход получает актуальное решение сервера вместо начального значения из навигации. */
export async function joinOrganizer(
  meeting: Pick<Meeting, 'id' | 'analysis_enabled'>,
  initialConsent: ConsentState = 'denied',
) {
  if (!meeting.analysis_enabled) return meetingsApi.joinAsOrganizer(meeting.id);
  const participants = await meetingsApi.listParticipants(meeting.id);
  const organizer = participants.find((participant) => participant.role === 'organizer');
  const consent = organizer?.consent_state ?? initialConsent;
  // POST join принимает granted/denied. Отзыв сохраняет выключенное состояние анализа.
  return meetingsApi.joinAsOrganizer(meeting.id, consent === 'granted' ? 'granted' : 'denied');
}
