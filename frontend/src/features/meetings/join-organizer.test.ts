import { meetingsApi } from '@/shared/api/meetings';
import type { ConsentState, Participant } from '@/shared/api/meetings';
import { joinOrganizer } from './join-organizer';

const meeting = { id: 'meeting', analysis_enabled: true };
function organizer(consent_state: ConsentState): Participant {
  return {
    id: 'organizer',
    display_name: 'Организатор',
    role: 'organizer',
    consent_state,
    online: false,
    is_removed: false,
    first_joined_at: null,
    last_left_at: null,
  };
}
afterEach(() => vi.restoreAllMocks());
it.each(['granted', 'denied', 'revoked'] as const)(
  'при повторном входе использует серверное %s, а не устаревшее значение навигации',
  async (state) => {
    vi.spyOn(meetingsApi, 'listParticipants').mockResolvedValue([organizer(state)]);
    const join = vi.spyOn(meetingsApi, 'joinAsOrganizer').mockResolvedValue({
      participant_id: 'organizer',
      livekit_url: 'ws://test',
      livekit_token: 'fixture',
      meeting: { ...meeting, title: 'Тест', status: 'active' },
    });
    await joinOrganizer(meeting, state === 'granted' ? 'denied' : 'granted');
    expect(join).toHaveBeenCalledWith('meeting', state === 'granted' ? 'granted' : 'denied');
  },
);
it('первый вход по умолчанию без согласия', async () => {
  vi.spyOn(meetingsApi, 'listParticipants').mockResolvedValue([]);
  const join = vi.spyOn(meetingsApi, 'joinAsOrganizer').mockResolvedValue({
    participant_id: 'organizer',
    livekit_url: 'ws://test',
    livekit_token: 'fixture',
    meeting: { ...meeting, title: 'Тест', status: 'active' },
  });
  await joinOrganizer(meeting);
  expect(join).toHaveBeenCalledWith('meeting', 'denied');
});
it('при ошибке чтения решения не перезаписывает его значением по умолчанию', async () => {
  vi.spyOn(meetingsApi, 'listParticipants').mockRejectedValue(new Error('unavailable'));
  const join = vi.spyOn(meetingsApi, 'joinAsOrganizer');
  await expect(joinOrganizer(meeting)).rejects.toThrow('unavailable');
  expect(join).not.toHaveBeenCalled();
});
