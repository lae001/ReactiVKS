import { HttpResponse, http } from 'msw';

import { setParticipantToken } from '@/shared/lib/participant-session';
import { mockNoSession, organizer, problem, tokenResponse } from '@/test/api-mocks';
import { server } from '@/test/server';

import { setSession } from '../session';

import { createHttpMeetingsApi } from './http';
import { MEETING_ERROR_CODES, type Meeting, type MeetingErrorCode } from './types';

const api = createHttpMeetingsApi();

const meeting: Meeting = {
  id: '0192a000-0000-7000-8000-00000000000a',
  title: 'Переговоры',
  status: 'scheduled',
  invite_code: 'k3m7qx4tpa',
  invite_url: 'https://vks.example.ru/j/k3m7qx4tpa',
  analysis_enabled: true,
  analysis_fps: 3,
  scheduled_at: null,
  started_at: null,
  ended_at: null,
  participants_count: 0,
  created_at: '2026-11-19T10:00:00Z',
};

const joinResult = {
  participant_id: 'p1',
  livekit_url: 'wss://livekit.example.ru',
  livekit_token: 'eyJ',
  meeting: { id: meeting.id, title: meeting.title, status: 'active', analysis_enabled: true },
};

beforeEach(() => setSession(tokenResponse(organizer, 'org-token')));

describe('http: организатор (Bearer)', () => {
  it('listMeetings: status через запятую, q, limit, cursor; пустые параметры не уходят', async () => {
    let url: URL | null = null;
    let auth: string | null = null;
    server.use(
      http.get('/api/v1/meetings', ({ request }) => {
        url = new URL(request.url);
        auth = request.headers.get('Authorization');
        return HttpResponse.json({ items: [meeting], next_cursor: 'c2' });
      }),
    );
    const page = await api.listMeetings({
      status: ['active', 'scheduled'],
      q: 'План',
      limit: 20,
      cursor: 'c1',
    });
    expect(page).toEqual({ items: [meeting], next_cursor: 'c2' });
    expect(auth).toBe('Bearer org-token');
    expect(Object.fromEntries(url!.searchParams)).toEqual({
      status: 'active,scheduled',
      q: 'План',
      limit: '20',
      cursor: 'c1',
    });

    await api.listMeetings();
    expect(url!.search).toBe('');
  });

  it('createMeeting: тело и заголовок Idempotency-Key', async () => {
    let key: string | null = null;
    let body: unknown;
    server.use(
      http.post('/api/v1/meetings', async ({ request }) => {
        key = request.headers.get('Idempotency-Key');
        body = await request.json();
        return HttpResponse.json(meeting, { status: 201 });
      }),
    );
    await expect(api.createMeeting({ title: 'Переговоры' }, 'key-1')).resolves.toEqual(meeting);
    expect(key).toBe('key-1');
    expect(body).toEqual({ title: 'Переговоры' });

    await api.createMeeting({ title: 'Без ключа' });
    expect(key).toBeNull();
  });

  it('getMeeting, updateMeeting (PATCH), deleteMeeting (204)', async () => {
    const calls: string[] = [];
    server.use(
      http.get('/api/v1/meetings/:id', ({ params }) => {
        calls.push(`GET ${String(params.id)}`);
        return HttpResponse.json(meeting);
      }),
      http.patch('/api/v1/meetings/:id', async ({ request }) => {
        calls.push(`PATCH ${JSON.stringify(await request.json())}`);
        return HttpResponse.json({ ...meeting, title: 'Новое' });
      }),
      http.delete('/api/v1/meetings/:id', () => {
        calls.push('DELETE');
        return new HttpResponse(null, { status: 204 });
      }),
    );
    await api.getMeeting(meeting.id);
    await expect(api.updateMeeting(meeting.id, { title: 'Новое' })).resolves.toMatchObject({
      title: 'Новое',
    });
    await expect(api.deleteMeeting(meeting.id)).resolves.toBeUndefined();
    expect(calls).toEqual([`GET ${meeting.id}`, 'PATCH {"title":"Новое"}', 'DELETE']);
  });

  it('id в пути экранируется', async () => {
    let path = '';
    server.use(
      http.get('/api/v1/meetings/:id', ({ request }) => {
        path = new URL(request.url).pathname;
        return HttpResponse.json(meeting);
      }),
    );
    await api.getMeeting('a/b');
    expect(path).toBe('/api/v1/meetings/a%2Fb');
  });

  it('joinAsOrganizer: consent в теле; endMeeting: POST', async () => {
    let joinBody: unknown;
    server.use(
      http.post('/api/v1/meetings/:id/join', async ({ request }) => {
        joinBody = await request.json();
        return HttpResponse.json(joinResult);
      }),
      http.post('/api/v1/meetings/:id/end', () =>
        HttpResponse.json({ ...meeting, status: 'ended' }),
      ),
    );
    await expect(api.joinAsOrganizer(meeting.id, 'granted')).resolves.toEqual(joinResult);
    expect(joinBody).toEqual({ consent: 'granted' });
    await api.joinAsOrganizer(meeting.id);
    expect(joinBody).toEqual({});
    await expect(api.endMeeting(meeting.id)).resolves.toMatchObject({ status: 'ended' });
  });

  it('listParticipants возвращает items; mute и remove – 204', async () => {
    let muteBody: unknown;
    let removed = false;
    server.use(
      http.get('/api/v1/meetings/:id/participants', () =>
        HttpResponse.json({ items: [{ id: 'p1' }] }),
      ),
      http.post('/api/v1/meetings/:id/participants/:pid/mute', async ({ request }) => {
        muteBody = await request.json();
        return new HttpResponse(null, { status: 204 });
      }),
      http.post('/api/v1/meetings/:id/participants/:pid/remove', () => {
        removed = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    await expect(api.listParticipants(meeting.id)).resolves.toEqual([{ id: 'p1' }]);
    await api.muteParticipant(meeting.id, 'p1', 'audio');
    expect(muteBody).toEqual({ kind: 'audio' });
    await api.removeParticipant(meeting.id, 'p1');
    expect(removed).toBe(true);
  });

  it('getSettings и putSettings', async () => {
    const settings = { analysis_enabled_default: false, analysis_fps_default: 4 };
    let put: unknown;
    server.use(
      http.get('/api/v1/settings', () => HttpResponse.json(settings)),
      http.put('/api/v1/settings', async ({ request }) => {
        put = await request.json();
        return HttpResponse.json(settings);
      }),
    );
    await expect(api.getSettings()).resolves.toEqual(settings);
    await expect(api.putSettings(settings)).resolves.toEqual(settings);
    expect(put).toEqual(settings);
  });
});

describe('http: гость и участник', () => {
  it('getJoinInfo и joinMeeting идут без Authorization', async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get('/api/v1/join/:code', ({ request }) => {
        seen.push(request.headers.get('Authorization'));
        return HttpResponse.json({ title: 'T', consent_notice: null });
      }),
      http.post('/api/v1/join/:code', async ({ request }) => {
        seen.push(request.headers.get('Authorization'));
        expect(await request.json()).toEqual({
          display_name: 'Анна',
          consent: 'granted',
          notice_version: 'v1',
        });
        return HttpResponse.json({ ...joinResult, participant_token: 'pt_1' });
      }),
    );
    await api.getJoinInfo('k3m7qx4tpa');
    const joined = await api.joinMeeting('k3m7qx4tpa', {
      display_name: 'Анна',
      consent: 'granted',
      notice_version: 'v1',
    });
    expect(joined.participant_token).toBe('pt_1');
    expect(seen).toEqual([null, null]);
  });

  it('setConsent гостя: Participant-токен; 202 (synced=false) – не ошибка', async () => {
    setParticipantToken('pt_guest');
    let auth: string | null = null;
    let search = '';
    server.use(
      http.put('/api/v1/participants/me/consent', async ({ request }) => {
        auth = request.headers.get('Authorization');
        search = new URL(request.url).search;
        expect(await request.json()).toEqual({ decision: 'revoked' });
        return HttpResponse.json({ consent_state: 'revoked', synced: false }, { status: 202 });
      }),
    );
    await expect(api.setConsent('revoked')).resolves.toEqual({
      consent_state: 'revoked',
      synced: false,
    });
    expect(auth).toBe('Participant pt_guest');
    expect(search).toBe('');
  });

  it('setConsent организатора: Bearer и ?meeting_id=', async () => {
    let auth: string | null = null;
    let search = '';
    server.use(
      http.put('/api/v1/participants/me/consent', ({ request }) => {
        auth = request.headers.get('Authorization');
        search = new URL(request.url).search;
        return HttpResponse.json({ consent_state: 'granted', synced: true });
      }),
    );
    await api.setConsent('granted', { meetingId: 'm1' });
    expect(auth).toBe('Bearer org-token');
    expect(search).toBe('?meeting_id=m1');
  });

  it('rejoin: Participant-токен; без токена – unauthorized без запроса', async () => {
    let requests = 0;
    server.use(
      http.post('/api/v1/participants/me/rejoin', ({ request }) => {
        requests += 1;
        expect(request.headers.get('Authorization')).toBe('Participant pt_guest');
        return HttpResponse.json(joinResult);
      }),
    );
    await expect(api.rejoin()).rejects.toMatchObject({ code: 'unauthorized', status: 401 });
    expect(requests).toBe(0);

    setParticipantToken('pt_guest');
    await expect(api.rejoin()).resolves.toEqual(joinResult);
  });
});

describe('http: коды ошибок реестра', () => {
  // Каждый код – на методе, который по контракту его возвращает.
  const cases: [MeetingErrorCode, () => Promise<unknown>, string][] = [
    ['validation_error', () => api.createMeeting({ title: '' }), 'POST /api/v1/meetings'],
    ['unauthorized', () => api.listMeetings(), 'GET /api/v1/meetings'],
    ['forbidden', () => api.getSettings(), 'GET /api/v1/settings'],
    ['not_found', () => api.getMeeting('x'), 'GET /api/v1/meetings/x'],
    ['too_many_requests', () => api.getJoinInfo('abc'), 'GET /api/v1/join/abc'],
    ['user_blocked', () => api.joinAsOrganizer('m1', 'granted'), 'POST /api/v1/meetings/m1/join'],
    [
      'meeting_not_started',
      () => api.joinMeeting('abc', { display_name: 'А' }),
      'POST /api/v1/join/abc',
    ],
    ['meeting_ended', () => api.endMeeting('m1'), 'POST /api/v1/meetings/m1/end'],
    ['meeting_cancelled', () => api.endMeeting('m1'), 'POST /api/v1/meetings/m1/end'],
    ['meeting_full', () => api.joinMeeting('abc', { display_name: 'А' }), 'POST /api/v1/join/abc'],
    [
      'meeting_not_editable',
      () => api.updateMeeting('m1', { analysis_fps: 4 }),
      'PATCH /api/v1/meetings/m1',
    ],
    [
      'consent_required',
      () => api.joinMeeting('abc', { display_name: 'А' }),
      'POST /api/v1/join/abc',
    ],
    [
      'notice_outdated',
      () => api.joinMeeting('abc', { display_name: 'А', consent: 'granted', notice_version: 'v0' }),
      'POST /api/v1/join/abc',
    ],
    [
      'analysis_disabled',
      () => api.setConsent('granted', { meetingId: 'm1' }),
      'PUT /api/v1/participants/me/consent',
    ],
    ['participant_removed', () => api.rejoin(), 'POST /api/v1/participants/me/rejoin'],
    [
      'idempotency_key_reused',
      () => api.createMeeting({ title: 'Другое' }, 'k'),
      'POST /api/v1/meetings',
    ],
    ['livekit_unavailable', () => api.joinAsOrganizer('m1'), 'POST /api/v1/meetings/m1/join'],
    ['internal_error', () => api.listMeetings(), 'GET /api/v1/meetings'],
  ];

  it('реестр в тестах покрывает все коды', () => {
    expect(new Set(cases.map(([code]) => code))).toEqual(new Set(Object.keys(MEETING_ERROR_CODES)));
  });

  it.each(cases)('%s → ApiError с кодом и статусом из реестра', async (code, call, route) => {
    setParticipantToken('pt_guest');
    mockNoSession(); // 401 запускает один refresh, он тоже отвечает 401
    const [method, path] = route.split(' ') as [string, string];
    const handler = (http as unknown as Record<string, typeof http.get>)[method.toLowerCase()]!;
    server.use(handler(path, () => problem(MEETING_ERROR_CODES[code], code)));
    await expect(call()).rejects.toMatchObject({
      name: 'ApiError',
      code,
      status: MEETING_ERROR_CODES[code],
    });
  });

  it('429: Retry-After доступен в ошибке', async () => {
    server.use(
      http.get('/api/v1/join/:code', () =>
        problem(429, 'too_many_requests', { headers: { 'Retry-After': '30' } }),
      ),
    );
    await expect(api.getJoinInfo('abc')).rejects.toMatchObject({ retryAfter: 30 });
  });
});
