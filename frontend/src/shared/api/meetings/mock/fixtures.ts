import type { Meeting, Participant } from '../types';

/**
 * Тестовые данные mock-реализации meeting-service (VITE_API_MODE=mock). Форма – как в ответах API.
 * Удаляется вместе с mock-режимом, когда появится meeting-service.
 */

export const MOCK_ORIGIN = 'https://vks.example.ru';
export const MOCK_ORGANIZER_NAME = 'Иван Петров';
export const MOCK_LIVEKIT_URL = 'ws://localhost:7880';

/** Предел участников встречи (docs/api/rest-api.md, `meeting_full`). */
export const MAX_PARTICIPANTS = 10;

/**
 * Черновик уведомления для лобби. Окончательный текст согласуется с заказчиком
 * в EMO-65 и хранится в src/shared/legal/consent-notice.v1.md.
 */
export const MOCK_CONSENT_NOTICE = {
  version: 'v1-draft',
  text_md:
    'Во время встречи Система распознает эмоции по выражению вашего лица и показывает их организатору. ' +
    'Видео не записывается и не сохраняется: хранятся только посекундные итоги распознавания для отчета организатора. ' +
    'Результаты носят вероятностный характер и не являются оценкой личности.',
};

function meeting(m: Omit<Meeting, 'invite_url' | 'analysis_fps' | 'created_at'>): Meeting {
  return {
    ...m,
    invite_url: `${MOCK_ORIGIN}/j/${m.invite_code}`,
    analysis_fps: 3,
    created_at: '2026-09-28T09:00:00Z',
  };
}

export function seedMeetings(): Meeting[] {
  return [
    meeting({
      id: 'm-active',
      title: 'Еженедельная планерка команды',
      status: 'active',
      invite_code: 'demoactive',
      analysis_enabled: true,
      scheduled_at: '2026-10-01T07:00:00Z',
      started_at: '2026-10-01T07:02:00Z',
      ended_at: null,
      participants_count: 4,
    }),
    meeting({
      id: 'm-noanal',
      title: 'Созвон с подрядчиком',
      status: 'active',
      invite_code: 'demonoanal',
      analysis_enabled: false,
      scheduled_at: null,
      started_at: '2026-10-01T08:15:00Z',
      ended_at: null,
      participants_count: 2,
    }),
    meeting({
      id: 'm-later',
      title: 'Интервью: frontend-разработчик',
      status: 'scheduled',
      invite_code: 'demolater2',
      analysis_enabled: true,
      scheduled_at: '2026-10-02T11:30:00Z',
      started_at: null,
      ended_at: null,
      participants_count: 0,
    }),
    meeting({
      id: 'm-ended',
      title: 'Демонстрация прототипа заказчику',
      status: 'ended',
      invite_code: 'demoended2',
      analysis_enabled: true,
      scheduled_at: '2026-09-29T12:00:00Z',
      started_at: '2026-09-29T12:01:00Z',
      ended_at: '2026-09-29T12:48:00Z',
      participants_count: 5,
    }),
    meeting({
      id: 'm-ended-2',
      title: 'Ретроспектива спринта 1',
      status: 'ended',
      invite_code: 'demoretro2',
      analysis_enabled: false,
      scheduled_at: '2026-09-27T15:00:00Z',
      started_at: '2026-09-27T15:00:00Z',
      ended_at: '2026-09-27T15:40:00Z',
      participants_count: 3,
    }),
    meeting({
      id: 'm-cancelled',
      title: 'Планирование релиза (отменена)',
      status: 'cancelled',
      invite_code: 'democancel',
      analysis_enabled: true,
      scheduled_at: '2026-09-30T09:00:00Z',
      started_at: null,
      ended_at: null,
      participants_count: 0,
    }),
    meeting({
      id: 'm-full',
      title: 'Общее собрание (комната заполнена)',
      status: 'active',
      invite_code: 'demofull22',
      analysis_enabled: false,
      scheduled_at: null,
      started_at: '2026-10-01T09:00:00Z',
      ended_at: null,
      participants_count: MAX_PARTICIPANTS,
    }),
  ];
}

function guest(id: string, name: string, consent: Participant['consent_state']): Participant {
  return {
    id,
    display_name: name,
    role: 'guest',
    consent_state: consent,
    online: true,
    is_removed: false,
    first_joined_at: '2026-10-01T07:03:00Z',
    last_left_at: null,
  };
}

export function seedParticipants(): Record<string, Participant[]> {
  return {
    'm-active': [
      guest('p-anna', 'Анна Смирнова', 'granted'),
      guest('p-oleg', 'Олег Иванов', 'denied'),
      guest('p-maria', 'Мария Ким', 'granted'),
      guest('p-dmitry', 'Дмитрий Орлов', 'granted'),
    ],
    'm-noanal': [
      guest('p-nina', 'Нина Белова', 'not_required'),
      guest('p-pavel', 'Павел Седов', 'not_required'),
    ],
    'm-full': Array.from({ length: MAX_PARTICIPANTS }, (_, i) =>
      guest(`p-full-${i + 1}`, `Участник ${i + 1}`, 'not_required'),
    ),
  };
}
