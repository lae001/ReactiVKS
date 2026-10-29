/**
 * Типы meeting-service по docs/api/rest-api.md, раздел 3.
 * Написаны вручную: заменить на сгенерированные (`pnpm gen:api`), когда появится OpenAPI meeting-service.
 */

export type MeetingStatus = 'scheduled' | 'active' | 'ended' | 'cancelled';

export type ConsentState = 'granted' | 'denied' | 'revoked' | 'not_required';

export type ParticipantRole = 'organizer' | 'guest';

export interface Meeting {
  id: string;
  title: string;
  status: MeetingStatus;
  invite_code: string;
  invite_url: string;
  analysis_enabled: boolean;
  /** 2–5 */
  analysis_fps: number;
  scheduled_at: string | null;
  started_at: string | null;
  ended_at: string | null;
  participants_count: number;
  created_at: string;
}

export interface Participant {
  id: string;
  display_name: string;
  role: ParticipantRole;
  consent_state: ConsentState;
  online: boolean;
  is_removed: boolean;
  first_joined_at: string | null;
  last_left_at: string | null;
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

/** Краткие сведения о встрече в ответе на вход. */
export interface JoinedMeeting {
  id: string;
  title: string;
  status: MeetingStatus;
  analysis_enabled: boolean;
}

/** Ответ на вход организатора и на rejoin. */
export interface JoinResult {
  participant_id: string;
  livekit_url: string;
  livekit_token: string;
  meeting: JoinedMeeting;
}

/** Ответ на вход гостя: к JoinResult добавлен токен гостя для REST-вызовов. */
export interface GuestJoinResult extends JoinResult {
  participant_token: string;
}

export interface ConsentResult {
  consent_state: ConsentState;
  /** Атрибут vks.consent в LiveKit уже обновлен (false – синхронизация в очереди, HTTP 202) */
  synced: boolean;
}

export interface Settings {
  analysis_enabled_default: boolean;
  /** 2–5 */
  analysis_fps_default: number;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export type ConsentDecision = 'granted' | 'denied';
export type ConsentChange = 'granted' | 'revoked';
export type MuteKind = 'audio' | 'video';

export interface ListMeetingsParams {
  status?: MeetingStatus[];
  /** подстрока названия, до 100 символов */
  q?: string;
  from?: string;
  to?: string;
  limit?: number;
  cursor?: string;
}

export interface CreateMeetingRequest {
  title: string;
  scheduled_at?: string | null;
  analysis_enabled?: boolean;
  analysis_fps?: number;
}

export interface UpdateMeetingRequest {
  title?: string;
  scheduled_at?: string | null;
  analysis_enabled?: boolean;
  analysis_fps?: number;
}

export interface GuestJoinRequest {
  display_name: string;
  consent?: ConsentDecision;
  notice_version?: string;
}

/**
 * Реестр кодов ошибок (docs/api/rest-api.md, «Реестр кодов ошибок»): те из них, что отдает
 * meeting-service, и общие для всех сервисов. Для сбоя сети и неожиданного ответа клиент
 * использует `network_error` и `unknown_error` (см. ApiError).
 */
export const MEETING_ERROR_CODES = {
  validation_error: 422,
  unauthorized: 401,
  forbidden: 403,
  not_found: 404,
  too_many_requests: 429,
  user_blocked: 403,
  meeting_not_started: 409,
  meeting_ended: 409,
  meeting_cancelled: 409,
  meeting_full: 409,
  meeting_not_editable: 409,
  consent_required: 409,
  notice_outdated: 409,
  analysis_disabled: 409,
  participant_removed: 409,
  idempotency_key_reused: 409,
  livekit_unavailable: 503,
  internal_error: 500,
} as const;

export type MeetingErrorCode = keyof typeof MEETING_ERROR_CODES;
