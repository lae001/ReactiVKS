import type { SnapshotParticipant } from '@/shared/api/types';

import { summarize } from './summary';

const base = { display_name: '', role: 'guest' } as const;

describe('сводка встречи', () => {
  it('усредняет только анализируемых участников', () => {
    const participants: SnapshotParticipant[] = [
      {
        ...base,
        participant_id: 'a',
        state: 'analyzing',
        last: { ts: '', dominant: 'happy', confidence: 0.6, p: [0, 0, 0, 0.6, 0.2, 0, 0.2] },
      },
      {
        ...base,
        participant_id: 'b',
        state: 'analyzing',
        last: { ts: '', dominant: 'angry', confidence: 0.4, p: [0.4, 0, 0, 0.2, 0, 0, 0.4] },
      },
      { ...base, participant_id: 'c', state: 'no_consent', last: null },
    ];
    const s = summarize(participants);
    expect(s?.analyzed).toBe(2);
    expect(s?.mean[0]).toBeCloseTo(0.2);
    expect(s?.mean[3]).toBeCloseTo(0.4);
    // angry 0.2 + sad 0.1
    expect(s?.negativeShare).toBeCloseTo(0.3);
  });

  it('нет анализируемых – нет сводки', () => {
    expect(summarize([{ ...base, participant_id: 'c', state: 'no_face', last: null }])).toBeNull();
  });
});
