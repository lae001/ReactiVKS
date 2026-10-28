import type { SnapshotParticipant } from '@/shared/api/types';
import { MOCK_EMOTION_SNAPSHOT } from '@/shared/mocks/data';

import type { RoomParticipant } from '../types';

/**
 * Панель эмоций и сводка пока на тестовых данных: realtime-сервис (WebSocket) еще не готов.
 * Участники берутся настоящие (из LiveKit), а значения эмоций – из тестового снимка: тем, кто дал
 * согласие, по кругу достаются тестовые карточки с вероятностями. Кто согласия не дал,
 * получает «Без анализа», как и должно быть. Удаляется вместе с `MOCK_EMOTION_SNAPSHOT`.
 */
export function mockEmotionSnapshot(people: RoomParticipant[]): SnapshotParticipant[] {
  const samples = Object.values(MOCK_EMOTION_SNAPSHOT).filter((s) => s.last !== null);
  let next = 0;
  return people
    .filter((p) => !p.isSelf)
    .map((p): SnapshotParticipant => {
      const base = { participant_id: p.id, display_name: p.name, role: p.role };
      if (p.consent !== 'granted' || samples.length === 0) {
        return { ...base, state: 'no_consent', last: null };
      }
      const sample = samples[next % samples.length]!;
      next += 1;
      return { ...base, state: 'analyzing', last: sample.last };
    });
}

export const EMOTIONS_MOCK_NOTICE =
  'Демонстрационные данные. Сервис распознавания эмоций еще не подключен: панель и сводка показывают тестовые значения, а не результат анализа ваших участников.';
