import type { EmotionLabel } from '@/shared/config/emotions';

import type { ParticipantRole } from './meetings/types';
import type { components } from './schema';
import type { ConsentState } from './meetings/types';

/**
 * Типы по контрактам docs/api/rest-api.md и docs/api/websocket-protocol.md.
 * Типы auth-service берутся из сгенерированной схемы (pnpm gen:api); типы meeting-service
 * (`meetings/types.ts`) и WebSocket написаны вручную, пока нет их OpenAPI.
 */

/** Учетная запись (схема `User`); у гостя учетной записи нет. */
export type User = components['schemas']['UserResponse'];

/** Роль учетной записи. */
export type UserRole = User['role'];

export type {
  ConsentState,
  JoinInfo,
  Meeting,
  MeetingStatus,
  Participant,
  ParticipantRole,
} from './meetings/types';

/** Состояние участника в панели эмоций (поле `state` протокола WebSocket). */
export type EmotionState = 'analyzing' | 'no_face' | 'camera_off' | 'no_consent' | 'left';

export interface EmotionSample {
  ts: string;
  dominant: EmotionLabel;
  confidence: number;
  /** Вероятности в порядке EMOTION_LABELS */
  p: number[];
}

export interface SnapshotParticipant {
  participant_id: string;
  display_name: string;
  role: ParticipantRole;
  state: EmotionState;
  last: EmotionSample | null;
}

export type AnalysisState = 'active' | 'degraded' | 'unavailable' | 'off';

/** Распределение вероятностей по классам эмоций (сумма ≈ 1). */
export type EmotionDistribution = Record<EmotionLabel, number>;

export interface Marker {
  id: string;
  ts: string;
  kind: 'auto_shift' | 'manual';
  participant_id: string | null;
  label: string;
  details: Record<string, unknown>;
}

export interface ReportParticipant {
  participant_id: string;
  display_name: string;
  consent: ConsentState;
  distribution: EmotionDistribution | null;
  dominant: EmotionLabel | null;
  face_detected_ratio: number | null;
  analyzed_seconds: number;
}

/** Ответ GET /reports/{meeting_id} (docs/api/rest-api.md, раздел analytics-service). */
export interface Report {
  meeting_id: string;
  status: 'pending' | 'ready' | 'failed';
  model_version: string | null;
  meeting: { title: string; started_at: string; ended_at: string; duration_s: number };
  summary: {
    overall: {
      distribution: EmotionDistribution;
      face_detected_ratio: number;
      negative_share: number;
    };
    participants: ReportParticipant[];
  };
  markers: Marker[];
  disclaimer: string;
}

export interface SeriesPoint {
  ts: string;
  /** Вероятности в порядке EMOTION_LABELS; null – лица не было весь интервал */
  p: number[] | null;
  face_ratio: number;
}

/** Ответ GET /reports/{meeting_id}/series для одного ряда «вся встреча». */
export interface Series {
  resolution: '1s' | '5s' | '30s';
  points: SeriesPoint[];
}
