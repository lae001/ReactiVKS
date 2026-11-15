import { EMOTION_LABELS } from '@/shared/config/emotions';
import { emptyEmotions, reduceEmotions } from './stream';

const snapshot = {
  type: 'subscribed',
  meeting_id: 'm',
  snapshot: {
    labels: EMOTION_LABELS,
    analysis: { state: 'active' },
    participants: [
      { participant_id: 'p', display_name: 'Гость', role: 'guest', state: 'analyzing', last: null },
    ],
  },
};
const update = {
  type: 'emotion.update',
  meeting_id: 'm',
  items: [
    {
      participant_id: 'p',
      state: 'analyzing',
      ts: '2026-11-12T10:00:00.000Z',
      dominant: 'happy',
      confidence: 0.7,
      p: [0, 0, 0, 0.7, 0, 0, 0.3],
    },
  ],
};
it('применяет snapshot и обновления по идентификатору, отзыв очищает текущую эмоцию', () => {
  const initial = reduceEmotions(emptyEmotions(), snapshot, 'm');
  const live = reduceEmotions(initial, update, 'm');
  expect(live.participants[0]?.last?.dominant).toBe('happy');
  const revoked = reduceEmotions(
    live,
    {
      type: 'participant.status',
      meeting_id: 'm',
      participant_id: 'p',
      display_name: 'Гость',
      state: 'no_consent',
    },
    'm',
  );
  expect(revoked.participants[0]?.last).toBeNull();
  expect(revoked.participants[0]?.state).toBe('no_consent');
  expect(reduceEmotions(revoked, update, 'm').participants[0]?.last).toBeNull();
});
it('игнорирует другую встречу, неизвестный тип и неверные вероятности', () => {
  const initial = reduceEmotions(emptyEmotions(), snapshot, 'm');
  expect(reduceEmotions(initial, update, 'other')).toBe(initial);
  expect(reduceEmotions(initial, { type: 'future' }, 'm')).toBe(initial);
  expect(reduceEmotions(initial, { ...update, items: [{ ...update.items[0], p: [9] }] }, 'm')).toBe(
    initial,
  );
});
it('сбой ML очищает актуальные эмоции', () => {
  const live = reduceEmotions(reduceEmotions(emptyEmotions(), snapshot, 'm'), update, 'm');
  const failed = reduceEmotions(
    live,
    { type: 'analysis.status', meeting_id: 'm', state: 'unavailable' },
    'm',
  );
  expect(failed.analysis).toBe('unavailable');
  expect(failed.participants[0]?.last).toBeNull();
});
