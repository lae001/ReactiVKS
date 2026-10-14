import type { EmotionState, SnapshotParticipant } from '@/shared/api/types';
import { EMOTION_LABELS, type EmotionLabel } from '@/shared/config/emotions';

/** Классы, которые сводка встречи считает негативными. */
export const NEGATIVE_EMOTIONS: readonly EmotionLabel[] = ['angry', 'disgust', 'fear', 'sad'];

export interface MeetingSummary {
  /** Средние вероятности по анализируемым участникам, в порядке EMOTION_LABELS */
  mean: number[];
  negativeShare: number;
  analyzed: number;
}

/** Сводка встречи для панели организатора; null – нет ни одного анализируемого участника. */
export function summarize(participants: SnapshotParticipant[]): MeetingSummary | null {
  const samples = participants.flatMap((p) => (p.state === 'analyzing' && p.last ? [p.last] : []));
  if (samples.length === 0) return null;

  const mean = EMOTION_LABELS.map(
    (_, i) => samples.reduce((sum, s) => sum + (s.p[i] ?? 0), 0) / samples.length,
  );
  const negativeShare = NEGATIVE_EMOTIONS.reduce(
    (sum, e) => sum + (mean[EMOTION_LABELS.indexOf(e)] ?? 0),
    0,
  );
  return { mean, negativeShare, analyzed: samples.length };
}

/** Подписи состояний участника (docs/api/websocket-protocol.md, «Состояния участника»). */
export const STATE_LABEL: Record<Exclude<EmotionState, 'analyzing'>, string> = {
  no_face: 'Лицо не обнаружено',
  camera_off: 'Камера выключена',
  no_consent: 'Без анализа',
  left: 'Вышел из встречи',
};
