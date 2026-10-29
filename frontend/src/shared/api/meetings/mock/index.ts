import { getParticipantToken } from '@/shared/lib/participant-session';

import { ApiError, type ValidationIssue } from '../../problem';
import type { MeetingsApi } from '../api';
import {
  type ConsentChange,
  type ConsentDecision,
  type CreateMeetingRequest,
  type GuestJoinResult,
  type JoinResult,
  type ListMeetingsParams,
  MEETING_ERROR_CODES,
  type MeetingErrorCode,
  type Meeting,
  type Participant,
  type Settings,
  type UpdateMeetingRequest,
} from '../types';

import {
  MAX_PARTICIPANTS,
  MOCK_CONSENT_NOTICE,
  MOCK_LIVEKIT_URL,
  MOCK_ORGANIZER_NAME,
  MOCK_ORIGIN,
  seedMeetings,
  seedParticipants,
} from './fixtures';

const BASE32 = 'abcdefghijklmnopqrstuvwxyz234567';
const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 100;

const MESSAGES: Partial<Record<MeetingErrorCode, string>> = {
  not_found: 'Не найдено',
  unauthorized: 'Нужно войти',
  meeting_not_started: 'Встреча еще не началась',
  meeting_ended: 'Встреча завершена',
  meeting_cancelled: 'Встреча отменена',
  meeting_full: 'В комнате уже 10 участников',
  meeting_not_editable: 'Параметры начатой встречи изменить нельзя',
  consent_required: 'Нужно решение о согласии на анализ эмоций',
  notice_outdated: 'Уведомление об анализе обновилось',
  analysis_disabled: 'Анализ эмоций в этой встрече выключен',
  participant_removed: 'Организатор удалил вас из встречи',
  idempotency_key_reused: 'Этот ключ уже использован с другим запросом',
  validation_error: 'Проверьте введенные данные',
};

function fail(code: MeetingErrorCode, errors?: ValidationIssue[]): never {
  throw new ApiError({
    status: MEETING_ERROR_CODES[code],
    code,
    message: MESSAGES[code] ?? code,
    requestId: 'mock',
    errors,
  });
}

function invalid(field: string, msg: string): never {
  fail('validation_error', [{ loc: ['body', field], msg, type: 'value_error' }]);
}

function randomInviteCode(): string {
  return Array.from({ length: 10 }, () => BASE32[Math.floor(Math.random() * 32)]).join('');
}

/** Ключ сортировки списка: coalesce(started_at, scheduled_at, created_at) по убыванию. */
function sortKey(m: Meeting): string {
  return m.started_at ?? m.scheduled_at ?? m.created_at;
}

interface TokenInfo {
  meetingId: string;
  participantId: string;
}

export type MockMeetingsApi = MeetingsApi & {
  /** Вернуть данные к исходным (между тестами). */
  reset(): void;
};

/**
 * Реализация meeting-service в памяти: те же проверки и коды ошибок, что в контракте
 * (docs/api/rest-api.md, раздел 3), но без сети и без LiveKit. Токены LiveKit – заглушки.
 * `now` – источник времени (в тестах подменяется).
 */
export function createMockMeetingsApi(now: () => Date = () => new Date()): MockMeetingsApi {
  let meetings: Meeting[] = [];
  let participants: Record<string, Participant[]> = {};
  let tokens = new Map<string, TokenInfo>();
  let idempotency = new Map<string, { fingerprint: string; meeting: Meeting }>();
  let settings: Settings = { analysis_enabled_default: true, analysis_fps_default: 3 };
  let counter = 0;

  function reset() {
    meetings = seedMeetings();
    participants = seedParticipants();
    tokens = new Map();
    idempotency = new Map();
    settings = { analysis_enabled_default: true, analysis_fps_default: 3 };
    counter = 0;
  }
  reset();

  const nextId = (prefix: string) => `${prefix}-${(counter += 1)}`;

  function find(id: string): Meeting {
    return meetings.find((m) => m.id === id) ?? fail('not_found');
  }

  function findByInvite(code: string): Meeting {
    return meetings.find((m) => m.invite_code === code) ?? fail('not_found');
  }

  const listOf = (meetingId: string) => (participants[meetingId] ??= []);
  const onlineCount = (meetingId: string) => listOf(meetingId).filter((p) => p.online).length;

  function recount(m: Meeting) {
    m.participants_count = Math.max(m.participants_count, onlineCount(m.id));
  }

  function requireOpen(m: Meeting) {
    if (m.status === 'ended') fail('meeting_ended');
    if (m.status === 'cancelled') fail('meeting_cancelled');
  }

  /** Встреча идет: в ней есть кого модерировать и куда возвращаться (ensure_in_progress бэкенда). */
  function requireInProgress(m: Meeting) {
    if (m.status === 'scheduled') fail('meeting_not_started');
    requireOpen(m);
  }

  function checkFps(fps: number | undefined) {
    if (fps !== undefined && (!Number.isInteger(fps) || fps < 2 || fps > 5)) {
      invalid('analysis_fps', 'Допустимо от 2 до 5');
    }
  }

  function checkTitle(title: string | undefined) {
    if (title !== undefined && (title.trim().length < 1 || title.length > 200)) {
      invalid('title', 'От 1 до 200 символов');
    }
  }

  function tokenInfo(): { info: TokenInfo; participant: Participant; meeting: Meeting } {
    const token = getParticipantToken();
    const info = token ? tokens.get(token) : undefined;
    if (!info) fail('unauthorized');
    const meeting = find(info.meetingId);
    const participant = listOf(meeting.id).find((p) => p.id === info.participantId);
    if (!participant) fail('unauthorized');
    return { info, participant, meeting };
  }

  function joinResult(m: Meeting, participantId: string): JoinResult {
    return {
      participant_id: participantId,
      livekit_url: MOCK_LIVEKIT_URL,
      livekit_token: `mock.livekit.${participantId}`,
      meeting: {
        id: m.id,
        title: m.title,
        status: m.status,
        analysis_enabled: m.analysis_enabled,
      },
    };
  }

  function organizerOf(m: Meeting, consent?: ConsentDecision): Participant {
    const id = `p-org-${m.id}`;
    let org = listOf(m.id).find((p) => p.id === id);
    if (!org) {
      org = {
        id,
        display_name: MOCK_ORGANIZER_NAME,
        role: 'organizer',
        consent_state: m.analysis_enabled ? (consent ?? 'denied') : 'not_required',
        online: false,
        is_removed: false,
        first_joined_at: null,
        last_left_at: null,
      };
      listOf(m.id).unshift(org);
    }
    return org;
  }

  return {
    reset,

    async listMeetings(params: ListMeetingsParams = {}) {
      const q = params.q?.trim().toLowerCase();
      if (q && q.length > 100) invalid('q', 'Не длиннее 100 символов');
      const limit = Math.min(Math.max(params.limit ?? DEFAULT_LIMIT, 1), MAX_LIMIT);
      const offset = params.cursor ? Number(/^o:(\d+)$/.exec(params.cursor)?.[1]) : 0;
      if (!Number.isInteger(offset)) invalid('cursor', 'Неверный курсор');

      const filtered = meetings
        .filter((m) => !params.status?.length || params.status.includes(m.status))
        .filter((m) => !q || m.title.toLowerCase().includes(q))
        .filter((m) => !params.from || sortKey(m) >= params.from)
        .filter((m) => !params.to || sortKey(m).slice(0, 10) <= params.to.slice(0, 10))
        .sort((a, b) => (sortKey(a) < sortKey(b) ? 1 : sortKey(a) > sortKey(b) ? -1 : 0));
      const items = filtered.slice(offset, offset + limit).map((m) => ({ ...m }));
      const end = offset + limit;
      return { items, next_cursor: end < filtered.length ? `o:${end}` : null };
    },

    async createMeeting(body: CreateMeetingRequest, idempotencyKey?: string) {
      const fingerprint = JSON.stringify(body);
      if (idempotencyKey) {
        const seen = idempotency.get(idempotencyKey);
        if (seen) {
          if (seen.fingerprint !== fingerprint) fail('idempotency_key_reused');
          return { ...seen.meeting };
        }
      }
      checkTitle(body.title);
      checkFps(body.analysis_fps);
      const code = randomInviteCode();
      const scheduledAt = body.scheduled_at ?? null;
      const created: Meeting = {
        id: nextId('m-new'),
        title: body.title.trim(),
        // «Сейчас» (без времени) и запланированная встреча остаются scheduled,
        // пока организатор не войдет: первый вход активирует встречу (rest-api.md, /join).
        status: 'scheduled',
        invite_code: code,
        invite_url: `${MOCK_ORIGIN}/j/${code}`,
        analysis_enabled: body.analysis_enabled ?? settings.analysis_enabled_default,
        analysis_fps: body.analysis_fps ?? settings.analysis_fps_default,
        scheduled_at: scheduledAt,
        started_at: null,
        ended_at: null,
        participants_count: 0,
        created_at: now().toISOString(),
      };
      meetings.unshift(created);
      if (idempotencyKey) idempotency.set(idempotencyKey, { fingerprint, meeting: created });
      return { ...created };
    },

    async getMeeting(id) {
      return { ...find(id) };
    },

    async updateMeeting(id, body: UpdateMeetingRequest) {
      const m = find(id);
      checkTitle(body.title);
      checkFps(body.analysis_fps);
      const { title, ...rest } = body;
      if (Object.keys(rest).length > 0 && m.status !== 'scheduled') fail('meeting_not_editable');
      if (title !== undefined) m.title = title.trim();
      if (body.scheduled_at !== undefined) m.scheduled_at = body.scheduled_at;
      if (body.analysis_enabled !== undefined) m.analysis_enabled = body.analysis_enabled;
      if (body.analysis_fps !== undefined) m.analysis_fps = body.analysis_fps;
      return { ...m };
    },

    async deleteMeeting(id) {
      find(id);
      meetings = meetings.filter((m) => m.id !== id);
      delete participants[id];
    },

    async joinAsOrganizer(id, consent) {
      const m = find(id);
      requireOpen(m);
      if (m.analysis_enabled && !consent) fail('consent_required');
      const org = organizerOf(m, consent);
      if (!org.online && onlineCount(m.id) >= MAX_PARTICIPANTS) fail('meeting_full');
      if (m.status === 'scheduled') {
        m.status = 'active';
        m.started_at = now().toISOString();
      }
      org.online = true;
      org.first_joined_at ??= now().toISOString();
      if (consent && m.analysis_enabled) org.consent_state = consent;
      recount(m);
      return joinResult(m, org.id);
    },

    async endMeeting(id) {
      const m = find(id);
      if (m.status === 'cancelled') fail('meeting_cancelled');
      // Не начатую встречу не завершают, а отменяют (DELETE): иначе в истории появилась бы «прошедшая» встреча.
      if (m.status === 'scheduled') fail('meeting_not_started');
      if (m.status !== 'ended') {
        m.status = 'ended';
        m.ended_at = now().toISOString();
        for (const p of listOf(m.id)) {
          if (p.online) p.last_left_at = m.ended_at;
          p.online = false;
        }
      }
      return { ...m };
    },

    async listParticipants(id) {
      find(id);
      return listOf(id).map((p) => ({ ...p }));
    },

    async muteParticipant(id, participantId) {
      const m = find(id);
      if (!listOf(id).some((p) => p.id === participantId)) fail('not_found');
      requireInProgress(m);
    },

    async removeParticipant(id, participantId) {
      const m = find(id);
      const p = listOf(id).find((x) => x.id === participantId) ?? fail('not_found');
      requireInProgress(m);
      if (p.role === 'organizer') {
        invalid('participant_id', 'Организатора из своей встречи не удаляют: встречу завершают');
      }
      p.is_removed = true;
      p.online = false;
      p.last_left_at = now().toISOString();
    },

    async getSettings() {
      return { ...settings };
    },

    async putSettings(next) {
      checkFps(next.analysis_fps_default);
      settings = { ...next };
      return { ...settings };
    },

    async getJoinInfo(code) {
      const m = findByInvite(code);
      return {
        title: m.title,
        organizer_name: MOCK_ORGANIZER_NAME,
        status: m.status,
        scheduled_at: m.scheduled_at,
        analysis_enabled: m.analysis_enabled,
        consent_notice: m.analysis_enabled ? MOCK_CONSENT_NOTICE : null,
      };
    },

    async joinMeeting(code, body): Promise<GuestJoinResult> {
      const m = findByInvite(code);
      const name = body.display_name.trim();
      if (name.length < 1 || name.length > 64) invalid('display_name', 'От 1 до 64 символов');
      requireOpen(m);
      if (m.status === 'scheduled') fail('meeting_not_started');
      if (onlineCount(m.id) >= MAX_PARTICIPANTS) fail('meeting_full');
      if (m.analysis_enabled) {
        if (!body.consent) fail('consent_required');
        if (body.notice_version !== MOCK_CONSENT_NOTICE.version) fail('notice_outdated');
      }

      const participant: Participant = {
        id: nextId('p-guest'),
        display_name: name,
        role: 'guest',
        consent_state: m.analysis_enabled ? (body.consent ?? 'denied') : 'not_required',
        online: true,
        is_removed: false,
        first_joined_at: now().toISOString(),
        last_left_at: null,
      };
      listOf(m.id).push(participant);
      recount(m);
      const token = `pt_mock_${crypto.randomUUID()}`;
      tokens.set(token, { meetingId: m.id, participantId: participant.id });
      return { ...joinResult(m, participant.id), participant_token: token };
    },

    async setConsent(decision: ConsentChange, options) {
      let meeting: Meeting;
      let participant: Participant;
      if (options?.meetingId) {
        meeting = find(options.meetingId);
        participant = organizerOf(meeting);
      } else {
        ({ meeting, participant } = tokenInfo());
      }
      if (meeting.status === 'ended') fail('meeting_ended');
      if (!meeting.analysis_enabled) fail('analysis_disabled');
      participant.consent_state = decision;
      return { consent_state: decision, synced: true };
    },

    async rejoin() {
      const { participant, meeting } = tokenInfo();
      if (participant.is_removed) fail('participant_removed');
      requireInProgress(meeting);
      participant.online = true;
      return joinResult(meeting, participant.id);
    },
  };
}
