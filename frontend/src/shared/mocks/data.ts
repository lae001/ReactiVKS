import type { SnapshotParticipant } from '@/shared/api/types';

/**
 * Тестовые данные панели эмоций и чата комнаты, пока нет realtime-сервиса (панель эмоций, WebSocket)
 * и чата на LiveKit. Данные meeting-service (встречи, участники, вход) – в слое API
 * `shared/api/meetings` (mock-режим). Удаляется вместе с панелью на моках.
 */

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

export const MOCK_CHAT = [
  {
    id: 'c1',
    author: 'Анна Смирнова',
    text: 'Всем привет! Слайды пришлю после встречи.',
    at: '0:12',
  },
  { id: 'c2', author: 'Олег Иванов', text: 'Меня слышно?', at: '0:40' },
];
