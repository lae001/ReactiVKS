import type { JoinInfo, Meeting, Participant, SnapshotParticipant } from '@/shared/api/types';

/**
 * Тестовые данные экранов главной, лобби и комнаты, пока не подключен бэкенд
 * (docs/frontend/site-structure.md, раздел 5). Форма – как в ответах API;
 * при подключении API (EMO-40, EMO-90) удаляется вместе с src/shared/mocks/.
 */

const ORIGIN = 'https://vks.example.ru';

function meeting(m: Omit<Meeting, 'invite_url' | 'analysis_fps' | 'created_at'>): Meeting {
  return {
    ...m,
    invite_url: `${ORIGIN}/j/${m.invite_code}`,
    analysis_fps: 3,
    created_at: '2026-09-28T09:00:00Z',
  };
}

export const MOCK_MEETINGS: Meeting[] = [
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
];

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

export function findMeetingById(id: string): Meeting | undefined {
  return MOCK_MEETINGS.find((m) => m.id === id);
}

export function findMeetingByInvite(code: string): Meeting | undefined {
  return MOCK_MEETINGS.find((m) => m.invite_code === code);
}

/** Аналог GET /join/{invite_code}; undefined – приглашение не найдено (404). */
export function getJoinInfo(code: string): JoinInfo | undefined {
  const m = findMeetingByInvite(code);
  if (!m) return undefined;
  return {
    title: m.title,
    organizer_name: 'Иван Петров',
    status: m.status,
    scheduled_at: m.scheduled_at,
    analysis_enabled: m.analysis_enabled,
    consent_notice: m.analysis_enabled ? MOCK_CONSENT_NOTICE : null,
  };
}

export type JoinError = 'not_found' | 'meeting_not_started' | 'meeting_ended' | 'consent_required';

/**
 * Аналог POST /join/{invite_code}: те же проверки и коды ошибок, что у meeting-service.
 * Возвращает id встречи для перехода в комнату.
 */
export function joinMeeting(
  code: string,
  body: { display_name: string; consent?: 'granted' | 'denied' },
): { meetingId: string } | { error: JoinError } {
  const m = findMeetingByInvite(code);
  if (!m) return { error: 'not_found' };
  if (m.analysis_enabled && !body.consent) return { error: 'consent_required' };
  if (m.status === 'scheduled') return { error: 'meeting_not_started' };
  if (m.status !== 'active') return { error: 'meeting_ended' };
  return { meetingId: m.id };
}

/** Остальные участники комнаты (без текущего пользователя). */
export const MOCK_ROOM_PARTICIPANTS: Participant[] = [
  {
    id: 'p-anna',
    display_name: 'Анна Смирнова',
    role: 'guest',
    consent_state: 'granted',
    online: true,
    is_removed: false,
  },
  {
    id: 'p-oleg',
    display_name: 'Олег Иванов',
    role: 'guest',
    consent_state: 'denied',
    online: true,
    is_removed: false,
  },
  {
    id: 'p-maria',
    display_name: 'Мария Ким',
    role: 'guest',
    consent_state: 'granted',
    online: true,
    is_removed: false,
  },
  {
    id: 'p-dmitry',
    display_name: 'Дмитрий Орлов',
    role: 'guest',
    consent_state: 'granted',
    online: true,
    is_removed: false,
  },
];

/** Снимок панели эмоций (сообщение `subscribed.snapshot` протокола WebSocket). */
export const MOCK_EMOTION_SNAPSHOT: Record<string, SnapshotParticipant> = {
  'p-anna': {
    participant_id: 'p-anna',
    display_name: 'Анна Смирнова',
    role: 'guest',
    state: 'analyzing',
    last: {
      ts: '2026-10-01T07:12:03.310Z',
      dominant: 'happy',
      confidence: 0.71,
      p: [0.02, 0.01, 0.03, 0.71, 0.05, 0.08, 0.1],
    },
  },
  'p-oleg': {
    participant_id: 'p-oleg',
    display_name: 'Олег Иванов',
    role: 'guest',
    state: 'no_consent',
    last: null,
  },
  'p-maria': {
    participant_id: 'p-maria',
    display_name: 'Мария Ким',
    role: 'guest',
    state: 'analyzing',
    last: {
      ts: '2026-10-01T07:12:03.643Z',
      dominant: 'neutral',
      confidence: 0.58,
      p: [0.03, 0.01, 0.02, 0.21, 0.07, 0.08, 0.58],
    },
  },
  'p-dmitry': {
    participant_id: 'p-dmitry',
    display_name: 'Дмитрий Орлов',
    role: 'guest',
    state: 'no_face',
    last: null,
  },
};
