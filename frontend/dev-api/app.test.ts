import { request as httpRequest, createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';

import { http as mswHttp, passthrough } from 'msw';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { server as mswServer } from '../src/test/server.ts';

import {
  createApp,
  type LiveKitGateway,
  LiveKitUnavailableError,
  MAX_PARTICIPANTS,
} from './app.ts';

/** REST-часть dev-api без LiveKit: вместо него подмена, которая запоминает вызовы. */
function fakeGateway() {
  const state = {
    online: [] as string[] | null,
    synced: true,
    unavailable: false,
  };
  const guard = () => {
    if (state.unavailable) throw new LiveKitUnavailableError('down');
  };
  const gateway = {
    url: 'ws://livekit.test',
    createToken: vi.fn(async (a: { identity: string; attributes: Record<string, string> }) => {
      return `jwt.${a.identity}`;
    }),
    ensureRoom: vi.fn(async () => guard()),
    listOnline: vi.fn(async () => state.online),
    updateAttributes: vi.fn(async () => state.synced),
    mute: vi.fn(async () => guard()),
    removeParticipant: vi.fn(async () => guard()),
    deleteRoom: vi.fn(async () => undefined),
  };
  return { gateway: gateway satisfies LiveKitGateway, state };
}

let http: Server;
let base = '';
let live: ReturnType<typeof fakeGateway>;
let app: ReturnType<typeof createApp>;

/** JWT организатора без подписи: dev-api берет из него `sub` (владелец) и `name`. */
const bearer = (sub: string, name?: string) => ({
  Authorization: `Bearer ${['{"alg":"none"}', JSON.stringify({ sub, name })]
    .map((part) => Buffer.from(part).toString('base64url'))
    .concat('x')
    .join('.')}`,
});

const ORG = bearer('user-owner');
const OTHER = bearer('user-other', 'Другой Организатор');

/** Поля ответов, которые читают тесты (остальное проверяется через toMatchObject). */
interface Body {
  id: string;
  title: string;
  invite_code: string;
  invite_url: string;
  started_at: string | null;
  ended_at: string | null;
  next_cursor: string | null;
  participant_id: string;
  participant_token: string;
  consent_notice: unknown;
  status: string;
  errors: { loc: unknown[] }[];
  items: {
    id: string;
    title: string;
    display_name: string;
    role: string;
    consent_state: string;
    online: boolean;
  }[];
}

async function call(
  method: string,
  path: string,
  options: { headers?: Record<string, string>; body?: unknown } = {},
) {
  const res = await fetch(base + path, {
    method,
    headers: { 'Content-Type': 'application/json', ...options.headers },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const raw = await res.text();
  return { status: res.status, body: raw ? (JSON.parse(raw) as Body) : null };
}

const create = async (body: Record<string, unknown> = { title: 'Планерка' }) =>
  (await call('POST', '/api/v1/meetings', { headers: ORG, body })).body!;

/** Встреча, которую организатор уже начал. */
async function activeMeeting(body: Record<string, unknown> = {}) {
  const m = await create({ title: 'Планерка', ...body });
  const joined = await call('POST', `/api/v1/meetings/${m.id}/join`, {
    headers: ORG,
    body: { consent: 'granted' },
  });
  expect(joined.status).toBe(200);
  return m;
}

async function guestJoin(code: string, name = 'Анна', extra: Record<string, unknown> = {}) {
  return call('POST', `/api/v1/join/${code}`, {
    body: { display_name: name, consent: 'granted', notice_version: 'v1', ...extra },
  });
}

beforeAll(async () => {
  live = fakeGateway();
  app = createApp({ gateway: live.gateway, origin: 'http://vks.test' });
  http = createServer((req, res) => void app.handle(req, res));
  await new Promise<void>((resolve) => http.listen(0, '127.0.0.1', resolve));
  base = `http://127.0.0.1:${(http.address() as AddressInfo).port}`;
});

afterAll(() => new Promise<void>((resolve) => http.close(() => resolve())));

beforeEach(() => {
  // dev-api слушает настоящий порт: запросы к нему пропускаем мимо MSW из общего setup
  mswServer.use(
    mswHttp.all('*', ({ request }) => (request.url.startsWith(base) ? passthrough() : undefined)),
  );
  app.reset();
  live.state.online = [];
  live.state.synced = true;
  live.state.unavailable = false;
  Object.values(live.gateway).forEach(
    (f) => typeof f === 'function' && 'mockClear' in f && f.mockClear(),
  );
});
afterEach(() => vi.restoreAllMocks());

describe('dev-api: общее', () => {
  it('маршруты организатора без заголовка Authorization – 401 unauthorized', async () => {
    const r = await call('GET', '/api/v1/meetings');
    expect(r.status).toBe(401);
    expect(r.body).toMatchObject({ code: 'unauthorized' });
  });

  it('неизвестный маршрут – 404, неверный JSON – 422', async () => {
    expect((await call('GET', '/api/v1/nothing')).status).toBe(404);
    const res = await fetch(`${base}/api/v1/meetings`, {
      method: 'POST',
      headers: { ...ORG, 'Content-Type': 'application/json' },
      body: '{oops',
    });
    expect(res.status).toBe(422);
  });

  it('чужое имя хоста (DNS rebinding) – 403', async () => {
    const status = await new Promise<number>((resolve, reject) => {
      const req = httpRequest(
        base + '/api/v1/settings',
        { headers: { Host: 'evil.example.com', ...ORG } },
        (res) => {
          res.resume();
          resolve(res.statusCode ?? 0);
        },
      );
      req.on('error', reject);
      req.end();
    });
    expect(status).toBe(403);
  });

  it('ошибки отдаются как problem+json с code и request_id', async () => {
    const res = await fetch(`${base}/api/v1/meetings/nope`, { headers: ORG });
    expect(res.headers.get('content-type')).toContain('application/problem+json');
    const body = (await res.json()) as Record<string, unknown>;
    expect(body).toMatchObject({ code: 'not_found', status: 404 });
    expect(typeof body.request_id).toBe('string');
  });
});

describe('dev-api: встречи', () => {
  it('создает встречу в статусе scheduled со ссылкой и настройками по умолчанию', async () => {
    const r = await call('POST', '/api/v1/meetings', { headers: ORG, body: { title: '  Демо  ' } });
    expect(r.status).toBe(201);
    expect(r.body).toMatchObject({
      title: 'Демо',
      status: 'scheduled',
      analysis_enabled: true,
      analysis_fps: 3,
      scheduled_at: null,
      participants_count: 0,
    });
    expect(r.body?.invite_code).toMatch(/^[a-z2-7]{10}$/);
    expect(r.body?.invite_url).toBe(`http://vks.test/j/${r.body?.invite_code}`);
  });

  it('значения по умолчанию берутся из /settings', async () => {
    await call('PUT', '/api/v1/settings', {
      headers: ORG,
      body: { analysis_enabled_default: false, analysis_fps_default: 5 },
    });
    expect(await create()).toMatchObject({ analysis_enabled: false, analysis_fps: 5 });
  });

  it('валидация: 422 с loc по полю', async () => {
    for (const [body, field] of [
      [{ title: '' }, 'title'],
      [{ title: 'x'.repeat(201) }, 'title'],
      [{ title: 'ok', analysis_fps: 9 }, 'analysis_fps'],
      [{ title: 'ok', scheduled_at: 'вчера' }, 'scheduled_at'],
    ] as const) {
      const r = await call('POST', '/api/v1/meetings', { headers: ORG, body });
      expect(r.status).toBe(422);
      expect(r.body?.errors[0].loc).toEqual(['body', field]);
    }
  });

  it('Idempotency-Key: то же тело – та же встреча, другое тело – 409', async () => {
    const headers = { ...ORG, 'Idempotency-Key': 'k-1' };
    const a = await call('POST', '/api/v1/meetings', { headers, body: { title: 'Один' } });
    const b = await call('POST', '/api/v1/meetings', { headers, body: { title: 'Один' } });
    expect(b.body?.id).toBe(a.body?.id);
    const list = await call('GET', '/api/v1/meetings', { headers: ORG });
    expect(list.body?.items).toHaveLength(1);

    const c = await call('POST', '/api/v1/meetings', { headers, body: { title: 'Другой' } });
    expect(c.status).toBe(409);
    expect(c.body).toMatchObject({ code: 'idempotency_key_reused' });
  });

  it('список: фильтр status через запятую, поиск q, курсор', async () => {
    const active = await activeMeeting({ title: 'Идет сейчас' });
    await create({ title: 'Позже', scheduled_at: '2030-01-01T10:00:00Z' });
    const ended = await create({ title: 'Закончена' });
    await call('POST', `/api/v1/meetings/${ended.id}/end`, { headers: ORG });

    const titles = async (query: string) =>
      (
        (await call('GET', `/api/v1/meetings${query}`, { headers: ORG })).body?.items as {
          title: string;
        }[]
      ).map((m) => m.title);

    expect(await titles('?status=scheduled,active')).toEqual(
      expect.arrayContaining(['Идет сейчас', 'Позже']),
    );
    expect(await titles('?status=scheduled,active')).not.toContain('Закончена');
    expect(await titles('?status=ended,cancelled')).toEqual(['Закончена']);
    expect(await titles('?q=ПОЗЖЕ')).toEqual(['Позже']);

    const first = await call('GET', '/api/v1/meetings?limit=2', { headers: ORG });
    expect(first.body?.items).toHaveLength(2);
    expect(first.body?.next_cursor).toBe('o:2');
    const second = await call('GET', '/api/v1/meetings?limit=2&cursor=o:2', { headers: ORG });
    expect(second.body?.items).toHaveLength(1);
    expect(second.body?.next_cursor).toBeNull();
    expect(active.id).toBeTruthy();
  });

  it('карточка, правка названия, 409 meeting_not_editable после начала, удаление', async () => {
    const m = await create();
    const patched = await call('PATCH', `/api/v1/meetings/${m.id}`, {
      headers: ORG,
      body: { title: 'Новое', analysis_fps: 4 },
    });
    expect(patched.body).toMatchObject({ title: 'Новое', analysis_fps: 4 });

    await call('POST', `/api/v1/meetings/${m.id}/join`, {
      headers: ORG,
      body: { consent: 'denied' },
    });
    const title = await call('PATCH', `/api/v1/meetings/${m.id}`, {
      headers: ORG,
      body: { title: 'Еще' },
    });
    expect(title.status).toBe(200);
    const fpsChange = await call('PATCH', `/api/v1/meetings/${m.id}`, {
      headers: ORG,
      body: { analysis_fps: 2 },
    });
    expect(fpsChange.status).toBe(409);
    expect(fpsChange.body).toMatchObject({ code: 'meeting_not_editable' });

    expect((await call('DELETE', `/api/v1/meetings/${m.id}`, { headers: ORG })).status).toBe(204);
    expect(live.gateway.deleteRoom).toHaveBeenCalledWith(m.id);
    expect((await call('GET', `/api/v1/meetings/${m.id}`, { headers: ORG })).status).toBe(404);
  });
});

describe('dev-api: вход организатора и завершение', () => {
  it('первый вход активирует встречу, создает комнату и выдает токен LiveKit', async () => {
    const m = await create();
    const r = await call('POST', `/api/v1/meetings/${m.id}/join`, {
      headers: ORG,
      body: { consent: 'granted' },
    });
    expect(r.status).toBe(200);
    expect(r.body).toMatchObject({
      livekit_url: 'ws://livekit.test',
      meeting: { id: m.id, status: 'active', analysis_enabled: true },
    });
    expect(live.gateway.ensureRoom).toHaveBeenCalledWith(m.id);
    expect(live.gateway.createToken).toHaveBeenCalledWith({
      room: m.id,
      identity: `p_${r.body?.participant_id}`,
      name: 'Организатор',
      attributes: { 'vks.role': 'organizer', 'vks.consent': 'granted', 'vks.kind': 'human' },
    });
    const card = await call('GET', `/api/v1/meetings/${m.id}`, { headers: ORG });
    expect(card.body).toMatchObject({ status: 'active', participants_count: 1 });
    expect(card.body?.started_at).toBeTruthy();
  });

  it('имя организатора берется из JWT без проверки подписи', async () => {
    const m = await create();
    await call('POST', `/api/v1/meetings/${m.id}/join`, {
      headers: bearer('user-owner', 'Иван Петров'),
      body: { consent: 'granted' },
    });
    expect(live.gateway.createToken).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Иван Петров' }),
    );
  });

  it('без выбора согласия – 409 consent_required; без анализа согласие не нужно', async () => {
    const m = await create();
    const r = await call('POST', `/api/v1/meetings/${m.id}/join`, { headers: ORG, body: {} });
    expect(r.status).toBe(409);
    expect(r.body).toMatchObject({ code: 'consent_required' });

    const quiet = await create({ title: 'Без анализа', analysis_enabled: false });
    const ok = await call('POST', `/api/v1/meetings/${quiet.id}/join`, { headers: ORG, body: {} });
    expect(ok.status).toBe(200);
    expect(live.gateway.createToken).toHaveBeenLastCalledWith(
      expect.objectContaining({
        attributes: expect.objectContaining({ 'vks.consent': 'not_required' }),
      }),
    );
  });

  it('LiveKit недоступен – 503 livekit_unavailable, встреча не стартует', async () => {
    live.state.unavailable = true;
    const m = await create();
    const r = await call('POST', `/api/v1/meetings/${m.id}/join`, {
      headers: ORG,
      body: { consent: 'granted' },
    });
    expect(r.status).toBe(503);
    expect(r.body).toMatchObject({ code: 'livekit_unavailable' });
    expect((await call('GET', `/api/v1/meetings/${m.id}`, { headers: ORG })).body?.status).toBe(
      'scheduled',
    );
  });

  it('завершение идемпотентно и удаляет комнату; вход в завершенную – 409 meeting_ended', async () => {
    const m = await activeMeeting();
    const first = await call('POST', `/api/v1/meetings/${m.id}/end`, { headers: ORG });
    const again = await call('POST', `/api/v1/meetings/${m.id}/end`, { headers: ORG });
    expect(first.body).toMatchObject({ status: 'ended' });
    expect(again.body?.ended_at).toBe(first.body?.ended_at);
    expect(live.gateway.deleteRoom).toHaveBeenCalledTimes(1);

    const join = await call('POST', `/api/v1/meetings/${m.id}/join`, {
      headers: ORG,
      body: { consent: 'granted' },
    });
    expect(join.body).toMatchObject({ code: 'meeting_ended' });
  });
});

describe('dev-api: лобби и вход гостя', () => {
  it('GET /join/{code}: без авторизации, уведомление v1; без анализа – consent_notice null', async () => {
    const m = await activeMeeting({ title: 'Лобби' });
    const info = await call('GET', `/api/v1/join/${m.invite_code}`);
    expect(info.body).toMatchObject({
      title: 'Лобби',
      status: 'active',
      analysis_enabled: true,
      consent_notice: { version: 'v1' },
    });
    const quiet = await create({ title: 'Тихая', analysis_enabled: false });
    expect(
      (await call('GET', `/api/v1/join/${quiet.invite_code}`)).body?.consent_notice,
    ).toBeNull();
    expect((await call('GET', '/api/v1/join/zzzzzzzzzz')).status).toBe(404);
  });

  it('встреча не началась – 409 meeting_not_started', async () => {
    const m = await create();
    const r = await guestJoin(m.invite_code);
    expect(r.status).toBe(409);
    expect(r.body).toMatchObject({ code: 'meeting_not_started' });
  });

  it('вход гостя: токен pt_…, токен LiveKit с атрибутами и identity p_<id>', async () => {
    const m = await activeMeeting();
    const r = await guestJoin(m.invite_code, 'Анна', { consent: 'denied' });
    expect(r.status).toBe(200);
    expect(r.body?.participant_token).toMatch(/^pt_/);
    expect(r.body).toMatchObject({
      meeting: { id: m.id, status: 'active' },
      livekit_url: 'ws://livekit.test',
    });
    expect(live.gateway.createToken).toHaveBeenLastCalledWith({
      room: m.id,
      identity: `p_${r.body?.participant_id}`,
      name: 'Анна',
      attributes: { 'vks.role': 'guest', 'vks.consent': 'denied', 'vks.kind': 'human' },
    });
  });

  it('проверки: имя, согласие, версия уведомления', async () => {
    const m = await activeMeeting();
    const noName = await guestJoin(m.invite_code, '   ');
    expect(noName.status).toBe(422);
    expect(noName.body?.errors[0].loc).toEqual(['body', 'display_name']);
    expect((await guestJoin(m.invite_code, 'x'.repeat(65))).status).toBe(422);

    const noConsent = await call('POST', `/api/v1/join/${m.invite_code}`, {
      body: { display_name: 'Анна', notice_version: 'v1' },
    });
    expect(noConsent.body).toMatchObject({ code: 'consent_required' });

    const old = await guestJoin(m.invite_code, 'Анна', { notice_version: 'v0' });
    expect(old.status).toBe(409);
    expect(old.body).toMatchObject({ code: 'notice_outdated' });
  });

  it(`комната на ${MAX_PARTICIPANTS} участников: одиннадцатый получает meeting_full`, async () => {
    const m = await activeMeeting(); // организатор – первый
    for (let i = 1; i < MAX_PARTICIPANTS; i += 1) {
      expect((await guestJoin(m.invite_code, `Гость ${i}`)).status).toBe(200);
    }
    const extra = await guestJoin(m.invite_code, 'Лишний');
    expect(extra.status).toBe(409);
    expect(extra.body).toMatchObject({ code: 'meeting_full' });
  });

  it('вышедшие из комнаты (по данным LiveKit) освобождают места', async () => {
    const m = await activeMeeting();
    const ids: string[] = [];
    for (let i = 1; i < MAX_PARTICIPANTS; i += 1) {
      ids.push((await guestJoin(m.invite_code, `Гость ${i}`)).body!.participant_id);
    }
    // все подключились к LiveKit, один – потом вышел
    live.state.online = ids.slice(1).map((id) => `p_${id}`);
    vi.useFakeTimers({ toFake: ['Date'], now: Date.now() + 120_000 });
    try {
      const r = await guestJoin(m.invite_code, 'Новый');
      expect(r.status).toBe(200);
    } finally {
      vi.useRealTimers();
    }
  });

  it('завершенная встреча – 409 meeting_ended', async () => {
    const m = await activeMeeting();
    await call('POST', `/api/v1/meetings/${m.id}/end`, { headers: ORG });
    expect((await guestJoin(m.invite_code)).body).toMatchObject({ code: 'meeting_ended' });
  });
});

describe('dev-api: участники и модерация', () => {
  it('список участников: организатор и гости, online по данным LiveKit', async () => {
    const m = await activeMeeting();
    const guest = await guestJoin(m.invite_code, 'Анна');
    live.state.online = [`p_${guest.body?.participant_id}`];

    const r = await call('GET', `/api/v1/meetings/${m.id}/participants`, { headers: ORG });
    const items = r.body?.items as {
      display_name: string;
      role: string;
      consent_state: string;
      online: boolean;
    }[];
    expect(items.map((p) => p.display_name)).toEqual(['Организатор', 'Анна']);
    expect(items[1]).toMatchObject({ role: 'guest', consent_state: 'granted', online: true });
    expect(Object.keys(items[1]!)).not.toContain('joinedAtMs');
  });

  it('mute: вызывает LiveKit с identity и видом; неверный вид – 422; чужой участник – 404', async () => {
    const m = await activeMeeting();
    const guest = (await guestJoin(m.invite_code)).body!;
    const url = `/api/v1/meetings/${m.id}/participants/${guest.participant_id}/mute`;

    expect((await call('POST', url, { headers: ORG, body: { kind: 'audio' } })).status).toBe(204);
    expect(live.gateway.mute).toHaveBeenCalledWith(m.id, `p_${guest.participant_id}`, 'audio');
    expect((await call('POST', url, { headers: ORG, body: { kind: 'sound' } })).status).toBe(422);
    const missing = await call('POST', `/api/v1/meetings/${m.id}/participants/nope/mute`, {
      headers: ORG,
      body: { kind: 'video' },
    });
    expect(missing.status).toBe(404);

    live.state.unavailable = true;
    expect((await call('POST', url, { headers: ORG, body: { kind: 'video' } })).body).toMatchObject(
      {
        code: 'livekit_unavailable',
      },
    );
  });

  it('mute в завершенной встрече – 409 meeting_ended', async () => {
    const m = await activeMeeting();
    const guest = (await guestJoin(m.invite_code)).body!;
    await call('POST', `/api/v1/meetings/${m.id}/end`, { headers: ORG });
    const r = await call(
      'POST',
      `/api/v1/meetings/${m.id}/participants/${guest.participant_id}/mute`,
      {
        headers: ORG,
        body: { kind: 'audio' },
      },
    );
    expect(r.body).toMatchObject({ code: 'meeting_ended' });
  });

  it('remove: участник удален в LiveKit и помечен; его rejoin – 409 participant_removed', async () => {
    const m = await activeMeeting();
    const guest = (await guestJoin(m.invite_code)).body!;
    const auth = { Authorization: `Participant ${guest.participant_token}` };

    const r = await call(
      'POST',
      `/api/v1/meetings/${m.id}/participants/${guest.participant_id}/remove`,
      {
        headers: ORG,
      },
    );
    expect(r.status).toBe(204);
    expect(live.gateway.removeParticipant).toHaveBeenCalledWith(m.id, `p_${guest.participant_id}`);

    const list = await call('GET', `/api/v1/meetings/${m.id}/participants`, { headers: ORG });
    expect(
      list.body?.items.find((p: { id: string }) => p.id === guest.participant_id),
    ).toMatchObject({
      is_removed: true,
      online: false,
    });
    const rejoin = await call('POST', '/api/v1/participants/me/rejoin', { headers: auth });
    expect(rejoin.status).toBe(409);
    expect(rejoin.body).toMatchObject({ code: 'participant_removed' });

    // остальные запросы по токену удаленного участника – 401 (на фронтенде это «Вас удалили…»)
    const consent = await call('PUT', '/api/v1/participants/me/consent', {
      headers: auth,
      body: { decision: 'granted' },
    });
    expect(consent.status).toBe(401);
    expect(live.gateway.updateAttributes).not.toHaveBeenCalled();
  });
});

describe('dev-api: согласие и повторный вход', () => {
  it('гость меняет согласие: атрибут vks.consent обновляется в LiveKit, 200 synced', async () => {
    const m = await activeMeeting();
    const guest = (await guestJoin(m.invite_code)).body!;
    const r = await call('PUT', '/api/v1/participants/me/consent', {
      headers: { Authorization: `Participant ${guest.participant_token}` },
      body: { decision: 'revoked' },
    });
    expect(r.status).toBe(200);
    expect(r.body).toEqual({ consent_state: 'revoked', synced: true });
    expect(live.gateway.updateAttributes).toHaveBeenCalledWith(m.id, `p_${guest.participant_id}`, {
      'vks.consent': 'revoked',
    });
  });

  it('участник не в комнате LiveKit – 202 synced=false, новый токен уже с новым согласием', async () => {
    live.state.synced = false;
    const m = await activeMeeting();
    const guest = (await guestJoin(m.invite_code)).body!;
    const auth = { Authorization: `Participant ${guest.participant_token}` };
    const r = await call('PUT', '/api/v1/participants/me/consent', {
      headers: auth,
      body: { decision: 'revoked' },
    });
    expect(r.status).toBe(202);
    expect(r.body).toEqual({ consent_state: 'revoked', synced: false });

    await call('POST', '/api/v1/participants/me/rejoin', { headers: auth });
    expect(live.gateway.createToken).toHaveBeenLastCalledWith(
      expect.objectContaining({
        attributes: expect.objectContaining({ 'vks.consent': 'revoked' }),
      }),
    );
  });

  it('организатор: Bearer и meeting_id в параметре', async () => {
    const m = await activeMeeting();
    const r = await call('PUT', `/api/v1/participants/me/consent?meeting_id=${m.id}`, {
      headers: ORG,
      body: { decision: 'revoked' },
    });
    expect(r.body).toMatchObject({ consent_state: 'revoked' });
    const noId = await call('PUT', '/api/v1/participants/me/consent', {
      headers: ORG,
      body: { decision: 'granted' },
    });
    expect(noId.status).toBe(422);
  });

  it('ошибки: 401 без токена и с чужим токеном, 409 analysis_disabled и meeting_ended, 422', async () => {
    const m = await activeMeeting();
    const guest = (await guestJoin(m.invite_code)).body!;
    const auth = { Authorization: `Participant ${guest.participant_token}` };
    const put = (headers: Record<string, string>, decision: unknown = 'granted') =>
      call('PUT', '/api/v1/participants/me/consent', { headers, body: { decision } });

    expect((await put({})).status).toBe(401);
    expect((await put({ Authorization: 'Participant pt_nope' })).status).toBe(401);
    expect((await put(auth, 'maybe')).status).toBe(422);

    await call('POST', `/api/v1/meetings/${m.id}/end`, { headers: ORG });
    expect((await put(auth)).body).toMatchObject({ code: 'meeting_ended' });

    const quiet = await activeMeeting({ title: 'Тихая', analysis_enabled: false });
    const q = (await guestJoin(quiet.invite_code)).body!;
    const r = await put({ Authorization: `Participant ${q.participant_token}` });
    expect(r.status).toBe(409);
    expect(r.body).toMatchObject({ code: 'analysis_disabled' });
  });

  it('rejoin: новый токен LiveKit; без токена – 401; завершенная встреча – meeting_ended', async () => {
    const m = await activeMeeting();
    const guest = (await guestJoin(m.invite_code)).body!;
    const auth = { Authorization: `Participant ${guest.participant_token}` };

    const r = await call('POST', '/api/v1/participants/me/rejoin', { headers: auth });
    expect(r.status).toBe(200);
    expect(r.body).toMatchObject({ participant_id: guest.participant_id, meeting: { id: m.id } });
    expect((await call('POST', '/api/v1/participants/me/rejoin')).status).toBe(401);

    await call('POST', `/api/v1/meetings/${m.id}/end`, { headers: ORG });
    expect(
      (await call('POST', '/api/v1/participants/me/rejoin', { headers: auth })).body,
    ).toMatchObject({
      code: 'meeting_ended',
    });
  });
});

describe('dev-api: настройки', () => {
  it('GET и PUT /settings, валидация fps', async () => {
    expect((await call('GET', '/api/v1/settings', { headers: ORG })).body).toEqual({
      analysis_enabled_default: true,
      analysis_fps_default: 3,
    });
    const put = await call('PUT', '/api/v1/settings', {
      headers: ORG,
      body: { analysis_enabled_default: false, analysis_fps_default: 4 },
    });
    expect(put.body).toEqual({ analysis_enabled_default: false, analysis_fps_default: 4 });
    const bad = await call('PUT', '/api/v1/settings', {
      headers: ORG,
      body: { analysis_enabled_default: true, analysis_fps_default: 1 },
    });
    expect(bad.status).toBe(422);
  });
});

describe('dev-api: у встречи есть владелец (claim sub)', () => {
  it('второй пользователь не видит чужую встречу в списке, владелец видит', async () => {
    await create({ title: 'Моя' });
    const mine = await call('GET', '/api/v1/meetings', { headers: ORG });
    expect(mine.body?.items.map((m) => m.title)).toEqual(['Моя']);
    const theirs = await call('GET', '/api/v1/meetings', { headers: OTHER });
    expect(theirs.status).toBe(200);
    expect(theirs.body?.items).toEqual([]);
  });

  it('чужая встреча: 404 not_found на GET, PATCH, DELETE, join, end, участников, mute и remove', async () => {
    const m = await activeMeeting();
    const guest = (await guestJoin(m.invite_code)).body!;
    const id = `/api/v1/meetings/${m.id}`;
    const attempts: [string, string, unknown?][] = [
      ['GET', id],
      ['PATCH', id, { title: 'Взлом' }],
      ['DELETE', id],
      ['POST', `${id}/join`, { consent: 'granted' }],
      ['POST', `${id}/end`],
      ['GET', `${id}/participants`],
      ['POST', `${id}/participants/${guest.participant_id}/mute`, { kind: 'audio' }],
      ['POST', `${id}/participants/${guest.participant_id}/remove`],
      ['PUT', `/api/v1/participants/me/consent?meeting_id=${m.id}`, { decision: 'revoked' }],
    ];
    for (const [method, path, body] of attempts) {
      const r = await call(method, path, { headers: OTHER, body });
      expect([method, path, r.status, (r.body as { code?: string } | null)?.code]).toEqual([
        method,
        path,
        404,
        'not_found',
      ]);
    }
    // ничего не изменилось: встреча идет, название прежнее, чужого участника в комнате нет
    const card = await call('GET', id, { headers: ORG });
    expect(card.body).toMatchObject({ title: 'Планерка', status: 'active' });
    const people = (await call('GET', `${id}/participants`, { headers: ORG })).body!.items;
    expect(people.every((p) => p.display_name !== 'Другой Организатор')).toBe(true);
    expect(live.gateway.mute).not.toHaveBeenCalled();
    expect(live.gateway.removeParticipant).not.toHaveBeenCalled();
  });

  it('владелец продолжает работать со своей встречей: изменение, участники, завершение', async () => {
    const m = await activeMeeting();
    const id = `/api/v1/meetings/${m.id}`;
    expect(
      (await call('PATCH', id, { headers: ORG, body: { title: 'Новое' } })).body,
    ).toMatchObject({
      title: 'Новое',
    });
    expect((await call('GET', `${id}/participants`, { headers: ORG })).status).toBe(200);
    expect((await call('POST', `${id}/end`, { headers: ORG })).body).toMatchObject({
      status: 'ended',
    });
  });

  it('организатор в комнате получает identity по своей встрече: два аккаунта не выбивают друг друга', async () => {
    const mine = await activeMeeting();
    const other = (
      await call('POST', '/api/v1/meetings', {
        headers: OTHER,
        body: { title: 'Чужая' },
      })
    ).body!;
    await call('POST', `/api/v1/meetings/${other.id}/join`, {
      headers: OTHER,
      body: { consent: 'granted' },
    });
    const identities = live.gateway.createToken.mock.calls.map(([a]) => a.identity);
    expect(new Set(identities).size).toBe(2);
    expect(identities).toContain(`p_org-${mine.id}`);
    expect(identities).toContain(`p_org-${other.id}`);
  });

  it('настройки и ключ идемпотентности у каждого пользователя свои', async () => {
    await call('PUT', '/api/v1/settings', {
      headers: ORG,
      body: { analysis_enabled_default: false, analysis_fps_default: 5 },
    });
    expect((await call('GET', '/api/v1/settings', { headers: OTHER })).body).toEqual({
      analysis_enabled_default: true,
      analysis_fps_default: 3,
    });
    const a = await call('POST', '/api/v1/meetings', {
      headers: { ...ORG, 'Idempotency-Key': 'k1' },
      body: { title: 'Один' },
    });
    const b = await call('POST', '/api/v1/meetings', {
      headers: { ...OTHER, 'Idempotency-Key': 'k1' },
      body: { title: 'Другой' },
    });
    expect(b.status).toBe(201);
    expect(b.body?.id).not.toBe(a.body?.id);
  });

  it('токен без sub (не JWT) – 401, пользователь не определен', async () => {
    const r = await call('GET', '/api/v1/meetings', {
      headers: { Authorization: 'Bearer test.jwt' },
    });
    expect(r.status).toBe(401);
  });

  it('гостевые маршруты владельца не требуют', async () => {
    const m = await activeMeeting();
    expect((await call('GET', `/api/v1/join/${m.invite_code}`)).status).toBe(200);
    const guest = (await guestJoin(m.invite_code)).body!;
    const auth = { Authorization: `Participant ${guest.participant_token}` };
    expect((await call('POST', '/api/v1/participants/me/rejoin', { headers: auth })).status).toBe(
      200,
    );
  });
});

describe('dev-api: текст уведомления в лобби', () => {
  it('без служебных слов: пользователь не видит «dev-api» и «черновик»', async () => {
    const m = await activeMeeting();
    const info = (await call('GET', `/api/v1/join/${m.invite_code}`)).body!;
    const text = (info.consent_notice as { text_md: string }).text_md;
    expect(text).toMatch(/распознает эмоции/);
    expect(text).not.toMatch(/dev-api|черновик|mock|TODO/i);
  });
});

describe('dev-api: participants_count – число записей participant встречи', () => {
  const count = async (id: string) =>
    (
      (await call('GET', `/api/v1/meetings/${id}`, { headers: ORG })).body as unknown as {
        participants_count: number;
      }
    ).participants_count;

  it('организатор в двух вкладках (повторный join) – одна запись', async () => {
    const m = await activeMeeting();
    await call('POST', `/api/v1/meetings/${m.id}/join`, {
      headers: ORG,
      body: { consent: 'granted' },
    });
    await call('POST', `/api/v1/meetings/${m.id}/join`, {
      headers: ORG,
      body: { consent: 'granted' },
    });
    expect(await count(m.id)).toBe(1);
  });

  it('гость: rejoin (обновление страницы) запись не создает, новый вход по ссылке – создает', async () => {
    const m = await activeMeeting();
    const guest = (await guestJoin(m.invite_code)).body!;
    expect(await count(m.id)).toBe(2);
    const auth = { Authorization: `Participant ${guest.participant_token}` };
    await call('POST', '/api/v1/participants/me/rejoin', { headers: auth });
    await call('POST', '/api/v1/participants/me/rejoin', { headers: auth });
    expect(await count(m.id)).toBe(2);

    // вход по ссылке без токена (другая вкладка, другой браузер) – новая запись: человека не отличить
    await guestJoin(m.invite_code);
    expect(await count(m.id)).toBe(3);
  });

  it('одинаковые имена – разные записи', async () => {
    const m = await activeMeeting();
    await guestJoin(m.invite_code, 'Анна');
    await guestJoin(m.invite_code, 'Анна');
    expect(await count(m.id)).toBe(3);
    const people = (await call('GET', `/api/v1/meetings/${m.id}/participants`, { headers: ORG }))
      .body!.items;
    expect(people.filter((p) => p.display_name === 'Анна')).toHaveLength(2);
  });

  it('удаленный участник остается записью (как в meeting-service), его rejoin закрыт', async () => {
    const m = await activeMeeting();
    const guest = (await guestJoin(m.invite_code)).body!;
    await call('POST', `/api/v1/meetings/${m.id}/participants/${guest.participant_id}/remove`, {
      headers: ORG,
    });
    expect(await count(m.id)).toBe(2);
    const again = await call('POST', '/api/v1/participants/me/rejoin', {
      headers: { Authorization: `Participant ${guest.participant_token}` },
    });
    expect(again.status).toBe(409);
  });
});
