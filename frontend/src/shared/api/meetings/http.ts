import { getParticipantToken } from '@/shared/lib/participant-session';

import { apiFetch } from '../client';
import { ApiError } from '../problem';

import type { MeetingsApi } from './api';
import type {
  ConsentResult,
  GuestJoinResult,
  JoinInfo,
  JoinResult,
  Meeting,
  Page,
  Participant,
  Settings,
} from './types';

const BASE = '/api/v1';

/** Заголовок гостя/участника: Authorization: Participant <participant_token>. */
function participantAuth(): Record<string, string> {
  const token = getParticipantToken();
  if (!token) {
    throw new ApiError({
      status: 401,
      code: 'unauthorized',
      message: 'Нет токена участника: войдите во встречу по ссылке',
    });
  }
  return { Authorization: `Participant ${token}` };
}

const enc = encodeURIComponent;

/** Параметры `from`/`to` сервера – даты `YYYY-MM-DD`: datetime с временем дал бы `422`. */
function dateParam(value: string | undefined): string | undefined {
  return value ? value.slice(0, 10) : undefined;
}

/** Сервер принимает `limit` 1–100 и на других значениях отвечает `422`. */
function limitParam(value: number | undefined): number | undefined {
  return value === undefined ? undefined : Math.min(Math.max(Math.trunc(value), 1), 100);
}

/** Реализация поверх настоящего meeting-service (docs/api/rest-api.md, раздел 3). */
export function createHttpMeetingsApi(): MeetingsApi {
  return {
    listMeetings: (params = {}, signal) =>
      apiFetch<Page<Meeting>>(`${BASE}/meetings`, {
        query: {
          status: params.status?.join(','),
          q: params.q,
          from: dateParam(params.from),
          to: dateParam(params.to),
          limit: limitParam(params.limit),
          cursor: params.cursor,
        },
        signal,
      }),

    createMeeting: (body, idempotencyKey) =>
      apiFetch<Meeting>(`${BASE}/meetings`, {
        method: 'POST',
        body,
        headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined,
      }),

    getMeeting: (id, signal) => apiFetch<Meeting>(`${BASE}/meetings/${enc(id)}`, { signal }),

    updateMeeting: (id, body) =>
      apiFetch<Meeting>(`${BASE}/meetings/${enc(id)}`, { method: 'PATCH', body }),

    deleteMeeting: (id) => apiFetch(`${BASE}/meetings/${enc(id)}`, { method: 'DELETE' }),

    joinAsOrganizer: (id, consent) =>
      apiFetch<JoinResult>(`${BASE}/meetings/${enc(id)}/join`, {
        method: 'POST',
        body: consent ? { consent } : {},
      }),

    endMeeting: (id) => apiFetch<Meeting>(`${BASE}/meetings/${enc(id)}/end`, { method: 'POST' }),

    listParticipants: async (id, signal) =>
      (
        await apiFetch<{ items: Participant[] }>(`${BASE}/meetings/${enc(id)}/participants`, {
          signal,
        })
      ).items,

    muteParticipant: (id, participantId, kind) =>
      apiFetch(`${BASE}/meetings/${enc(id)}/participants/${enc(participantId)}/mute`, {
        method: 'POST',
        body: { kind },
      }),

    removeParticipant: (id, participantId) =>
      apiFetch(`${BASE}/meetings/${enc(id)}/participants/${enc(participantId)}/remove`, {
        method: 'POST',
      }),

    getSettings: (signal) => apiFetch<Settings>(`${BASE}/settings`, { signal }),

    putSettings: (settings) =>
      apiFetch<Settings>(`${BASE}/settings`, { method: 'PUT', body: settings }),

    getJoinInfo: (inviteCode, signal) =>
      apiFetch<JoinInfo>(`${BASE}/join/${enc(inviteCode)}`, { auth: false, signal }),

    joinMeeting: (inviteCode, body) =>
      apiFetch<GuestJoinResult>(`${BASE}/join/${enc(inviteCode)}`, {
        method: 'POST',
        body,
        auth: false,
      }),

    setConsent: async (decision, options) =>
      options?.meetingId
        ? apiFetch<ConsentResult>(`${BASE}/participants/me/consent`, {
            method: 'PUT',
            body: { decision },
            query: { meeting_id: options.meetingId },
          })
        : apiFetch<ConsentResult>(`${BASE}/participants/me/consent`, {
            method: 'PUT',
            body: { decision },
            auth: false,
            headers: participantAuth(),
          }),

    rejoin: async () =>
      apiFetch<JoinResult>(`${BASE}/participants/me/rejoin`, {
        method: 'POST',
        auth: false,
        headers: participantAuth(),
      }),
  };
}
