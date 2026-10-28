import type {
  ConsentChange,
  ConsentResult,
  CreateMeetingRequest,
  GuestJoinRequest,
  GuestJoinResult,
  JoinInfo,
  JoinResult,
  ListMeetingsParams,
  Meeting,
  MuteKind,
  Page,
  Participant,
  Settings,
  UpdateMeetingRequest,
  ConsentDecision,
} from './types';

/**
 * Клиентский интерфейс meeting-service (docs/api/rest-api.md, раздел 3). Две реализации:
 * `http` (настоящий сервис) и `mock` (в памяти), выбор – VITE_API_MODE. Ошибки – всегда ApiError
 * с кодом из реестра (`MEETING_ERROR_CODES`).
 */
export interface MeetingsApi {
  // Организатор (Bearer)
  listMeetings(params?: ListMeetingsParams, signal?: AbortSignal): Promise<Page<Meeting>>;
  /** `idempotencyKey` – заголовок Idempotency-Key: повтор запроса не создает вторую встречу. */
  createMeeting(body: CreateMeetingRequest, idempotencyKey?: string): Promise<Meeting>;
  getMeeting(id: string, signal?: AbortSignal): Promise<Meeting>;
  updateMeeting(id: string, body: UpdateMeetingRequest): Promise<Meeting>;
  deleteMeeting(id: string): Promise<void>;
  /** Первый вход активирует встречу. `consent` обязателен, если анализ включен. */
  joinAsOrganizer(id: string, consent?: ConsentDecision): Promise<JoinResult>;
  endMeeting(id: string): Promise<Meeting>;
  listParticipants(id: string, signal?: AbortSignal): Promise<Participant[]>;
  muteParticipant(id: string, participantId: string, kind: MuteKind): Promise<void>;
  removeParticipant(id: string, participantId: string): Promise<void>;
  getSettings(signal?: AbortSignal): Promise<Settings>;
  putSettings(settings: Settings): Promise<Settings>;

  // Гость (без аутентификации) и участник (Participant-токен из sessionStorage)
  getJoinInfo(inviteCode: string, signal?: AbortSignal): Promise<JoinInfo>;
  joinMeeting(inviteCode: string, body: GuestJoinRequest): Promise<GuestJoinResult>;
  /**
   * PUT /participants/me/consent. Гость – по Participant-токену; организатор передает
   * `meetingId` и идет по Bearer.
   */
  setConsent(decision: ConsentChange, options?: { meetingId?: string }): Promise<ConsentResult>;
  /** Новый токен LiveKit гостю после перезагрузки вкладки (по Participant-токену). */
  rejoin(): Promise<JoinResult>;
}
