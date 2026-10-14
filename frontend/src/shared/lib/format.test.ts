import type { Meeting } from '@/shared/api/types';

import { formatDuration, formatMeetingWhen, formatPercent, initials } from './format';

describe('форматирование', () => {
  it('длительность', () => {
    expect(formatDuration(0)).toBe('0:00');
    expect(formatDuration(245)).toBe('4:05');
    expect(formatDuration(3723)).toBe('1:02:03');
  });

  it('инициалы', () => {
    expect(initials('Анна Смирнова')).toBe('АС');
    expect(initials('  олег  ')).toBe('О');
    expect(initials('Мария Ивановна Ким')).toBe('МК');
  });

  it('проценты', () => {
    expect(formatPercent(0.713)).toBe('71 %');
  });

  it('время встречи', () => {
    const base = { started_at: null, scheduled_at: null } as Meeting;
    expect(formatMeetingWhen({ ...base, status: 'scheduled' })).toBe('Без времени');
    expect(
      formatMeetingWhen(
        { ...base, status: 'active', started_at: '2026-10-01T07:02:00Z' },
        'Europe/Moscow',
      ),
    ).toMatch(/^Идет с 1 окт\.?, 10:02$/);
  });
});
