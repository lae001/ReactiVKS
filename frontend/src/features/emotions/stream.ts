import { z } from 'zod';

import type { AnalysisState, SnapshotParticipant } from '@/shared/api/types';
import { EMOTION_LABELS } from '@/shared/config/emotions';

const state = z.enum(['analyzing', 'no_face', 'camera_off', 'no_consent', 'left']);
const sample = z.object({
  ts: z.string().datetime(),
  dominant: z.enum(EMOTION_LABELS),
  confidence: z.number().min(0).max(1),
  p: z.array(z.number().min(0).max(1)).length(7),
});
const participant = z.object({
  participant_id: z.string(),
  display_name: z.string(),
  role: z.enum(['organizer', 'guest']),
  state,
  last: sample.nullable(),
});
const analysis = z.enum(['active', 'degraded', 'unavailable', 'off']);
const message = z.discriminatedUnion('type', [
  z.object({
    type: z.literal('subscribed'),
    meeting_id: z.string(),
    snapshot: z.object({
      labels: z.array(z.string()),
      analysis: z.object({ state: analysis }),
      participants: z.array(participant),
    }),
  }),
  z.object({
    type: z.literal('emotion.update'),
    meeting_id: z.string(),
    items: z.array(
      z.object({
        participant_id: z.string(),
        state,
        ts: z.string().datetime(),
        dominant: z.enum(EMOTION_LABELS).optional(),
        confidence: z.number().min(0).max(1).optional(),
        p: z.array(z.number().min(0).max(1)).length(7).optional(),
      }),
    ),
  }),
  z.object({
    type: z.literal('participant.status'),
    meeting_id: z.string(),
    participant_id: z.string(),
    display_name: z.string(),
    state,
  }),
  z.object({ type: z.literal('analysis.status'), meeting_id: z.string(), state: analysis }),
]);
export interface EmotionData {
  analysis: AnalysisState;
  participants: SnapshotParticipant[];
  history: Record<string, { ts: string; confidence: number }[]>;
  lastTs?: string;
}
export const emptyEmotions = (): EmotionData => ({
  analysis: 'unavailable',
  participants: [],
  history: {},
});

/** Чужая встреча, неверный порядок меток и некорректные пакеты не изменяют данные. */
export function reduceEmotions(
  current: EmotionData,
  input: unknown,
  meetingId: string,
): EmotionData {
  const parsed = message.safeParse(input);
  if (!parsed.success || parsed.data.meeting_id !== meetingId) return current;
  const m = parsed.data;
  if (m.type === 'subscribed') {
    if (m.snapshot.labels.join() !== EMOTION_LABELS.join()) return emptyEmotions();
    return {
      ...current,
      analysis: m.snapshot.analysis.state,
      participants: m.snapshot.participants,
    };
  }
  if (m.type === 'analysis.status')
    return {
      ...current,
      analysis: m.state,
      participants: current.participants.map((p) => ({ ...p, last: null })),
    };
  if (m.type === 'participant.status')
    return {
      ...current,
      participants: current.participants.some((p) => p.participant_id === m.participant_id)
        ? current.participants.map((p) =>
            p.participant_id === m.participant_id
              ? { ...p, display_name: m.display_name, state: m.state, last: null }
              : p,
          )
        : [
            ...current.participants,
            {
              participant_id: m.participant_id,
              display_name: m.display_name,
              role: 'guest',
              state: m.state,
              last: null,
            },
          ],
    };
  if (current.analysis === 'off' || current.analysis === 'unavailable') return current;
  const next = {
    ...current,
    participants: [...current.participants],
    history: { ...current.history },
  };
  for (const item of m.items) {
    const index = next.participants.findIndex((p) => p.participant_id === item.participant_id);
    const previous = next.participants[index];
    if (!previous || (previous.last && item.ts <= previous.last.ts)) continue;
    if (
      (previous.state === 'no_consent' || previous.state === 'left') &&
      item.state === 'analyzing'
    )
      continue;
    const last = item.state === 'analyzing' ? sample.safeParse(item) : null;
    next.participants[index] = {
      ...previous,
      state: item.state,
      last: last?.success ? last.data : null,
    };
    if (last?.success) {
      const cutoff = Date.parse(item.ts) - 300000;
      next.history[item.participant_id] = [
        ...(next.history[item.participant_id] ?? []),
        { ts: item.ts, confidence: last.data.confidence },
      ]
        .filter((p) => Date.parse(p.ts) >= cutoff)
        .slice(-1500);
    }
    if (!next.lastTs || item.ts > next.lastTs) next.lastTs = item.ts;
  }
  return next;
}
