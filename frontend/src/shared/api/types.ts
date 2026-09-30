import type { EmotionLabel } from '@/shared/config/emotions';

/**
 * Типы по контрактам docs/api/rest-api.md и docs/api/websocket-protocol.md.
 * Написаны вручную на время работы на тестовых данных; в EMO-40 заменяются
 * типами, сгенерированными openapi-typescript (src/shared/api/schema.d.ts).
 */

/** Роль учетной записи (схема `User`); у гостя учетной записи нет. */
export type UserRole = 'organizer' | 'admin';

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: UserRole;
}

export type MeetingStatus = 'scheduled' | 'active' | 'ended' | 'cancelled';

export type ConsentState = 'granted' | 'denied' | 'revoked' | 'not_required';

export interface Meeting {
  id: string;
  title: string;
  status: MeetingStatus;
  invite_code: string;
  invite_url: string;
  analysis_enabled: boolean;
  analysis_fps: number;
  scheduled_at: string | null;
  started_at: string | null;
  ended_at: string | null;
  participants_count: number;
  created_at: string;
}

/** Ответ GET /join/{invite_code} – информация для лобби. */
export interface JoinInfo {
  title: string;
  organizer_name: string;
  status: MeetingStatus;
  scheduled_at: string | null;
  analysis_enabled: boolean;
  /** null, если анализ во встрече выключен */
  consent_notice: { version: string; text_md: string } | null;
}

export type ParticipantRole = 'organizer' | 'guest';

export interface Participant {
  id: string;
  display_name: string;
  role: ParticipantRole;
  consent_state: ConsentState;
  online: boolean;
  is_removed: boolean;
}

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
