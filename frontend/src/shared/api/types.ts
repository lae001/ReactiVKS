import type { EmotionLabel } from '@/shared/config/emotions';

import type { components } from './schema';

/**
 * Типы по контрактам docs/api/rest-api.md и docs/api/websocket-protocol.md.
 * Типы auth-service берутся из сгенерированной схемы (pnpm gen:api); типы meeting-service
 * и WebSocket написаны вручную на время работы на тестовых данных, пока сервисов нет.
 */

/** Учетная запись (схема `User`); у гостя учетной записи нет. */
export type User = components['schemas']['UserResponse'];

/** Роль учетной записи. */
export type UserRole = User['role'];

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
