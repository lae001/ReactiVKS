import { randomBytes, randomUUID } from 'node:crypto';
import type { IncomingMessage, ServerResponse } from 'node:http';

/**
 * ВРЕМЕННЫЙ dev-сервер вместо meeting-service: подмножество контракта docs/api/rest-api.md (раздел 3),
 * которое использует слой API фронтенда. Данные в памяти, JWT организатора не проверяется
 * (достаточно заголовка `Authorization: Bearer <JWT>` с claim `sub`), у каждой встречи свой владелец.
 * Удаляется, когда появится настоящий meeting-service (dev-api/README.md).
 */

// ---------- LiveKit ----------

/** LiveKit недоступен или ответил сбоем: REST отвечает `503 livekit_unavailable`. */
export class LiveKitUnavailableError extends Error {}

/** То, что dev-api берет у LiveKit (LiveKitGateway из docs/api/livekit-integration.md). */
export interface LiveKitGateway {
  url: string;
  createToken(args: {
    room: string;
    identity: string;
    name: string;
    attributes: Record<string, string>;
  }): Promise<string>;
  ensureRoom(room: string): Promise<void>;
  /** identity участников, которые сейчас в комнате; null – LiveKit недоступен */
  listOnline(room: string): Promise<string[] | null>;
  /** true – атрибуты обновлены, false – участника нет в комнате, возьмутся из нового токена */
  updateAttributes(
    room: string,
    identity: string,
    attributes: Record<string, string>,
  ): Promise<boolean>;
  mute(room: string, identity: string, kind: 'audio' | 'video'): Promise<void>;
  removeParticipant(room: string, identity: string): Promise<void>;
  deleteRoom(room: string): Promise<void>;
}

// ---------- Типы контракта ----------

type MeetingStatus = 'scheduled' | 'active' | 'ended' | 'cancelled';
type ConsentState = 'granted' | 'denied' | 'revoked' | 'not_required';

interface Meeting {
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

interface Participant {
  id: string;
  display_name: string;
  role: 'organizer' | 'guest';
  consent_state: ConsentState;
  online: boolean;
  is_removed: boolean;
  first_joined_at: string | null;
  last_left_at: string | null;
}

/** Участник во внутреннем состоянии: публичные поля плюс служебные. */
interface Stored extends Participant {
  joinedAtMs: number;
  seenOnline: boolean;
}

export const MAX_PARTICIPANTS = 10;
/** Сколько после входа по REST участник считается «в комнате», даже если еще не подключился к LiveKit. */
const CONNECT_GRACE_MS = 60_000;
export const CONSENT_NOTICE = {
  version: 'v1',
  text_md:
    'Во время встречи организатор видит эмоции участников, распознанные по видео (dev-api, черновик текста). ' +
    'Анализ включается только с вашего согласия, решение можно изменить в любой момент.',
};

const CODES = {
  validation_error: 422,
  unauthorized: 401,
  not_found: 404,
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
type Code = keyof typeof CODES;

interface Issue {
  loc: (string | number)[];
  msg: string;
  type: string;
}

// Без «свойств-параметров» конструктора: Node убирает типы без преобразования кода (strip-types)
class HttpError extends Error {
  readonly code: Code;
  readonly errors?: Issue[];
  constructor(code: Code, message: string = code, errors?: Issue[]) {
    super(message);
    this.code = code;
    this.errors = errors;
  }
}

const fail: (code: Code, message?: string) => never = (code, message) => {
  throw new HttpError(code, message);
};
const invalid: (field: string, msg: string) => never = (field, msg) => {
  throw new HttpError('validation_error', 'Проверьте введенные данные', [
    { loc: ['body', field], msg, type: 'value_error' },
  ]);
};

// ---------- Запрос и ответ ----------

type Auth =
  | { kind: 'organizer'; userId: string; name: string }
  | { kind: 'participant'; token: string }
  | null;

interface Ctx {
  params: string[];
  query: URLSearchParams;
  body: Record<string, unknown>;
  auth: Auth;
  headers: IncomingMessage['headers'];
}

interface Reply {
  status: number;
  body?: unknown;
}

type Handler = (ctx: Ctx) => Promise<Reply> | Reply;

const ok = (body: unknown, status = 200): Reply => ({ status, body });
const noContent = (): Reply => ({ status: 204 });

const BASE32 = 'abcdefghijklmnopqrstuvwxyz234567';
const MAX_BODY = 64 * 1024;

function inviteCode(): string {
  return Array.from(randomBytes(10), (b) => BASE32[b % 32]).join('');
}

/**
 * Claims `sub` (id пользователя) и `name` из JWT организатора без проверки подписи: токен выпускает
 * auth-service (docs/architecture/05-security-privacy.md), здесь он нужен, чтобы знать владельца встречи
 * и подписать участника в галерее. Токен без `sub` пользователя не определяет.
 */
function claimsFromJwt(token: string): { userId: string; name: string } | null {
  try {
    const part = token.split('.')[1] ?? '';
    const payload = JSON.parse(Buffer.from(part, 'base64url').toString()) as {
      sub?: unknown;
      name?: unknown;
    };
    if (typeof payload.sub !== 'string' || !payload.sub) return null;
    const name = typeof payload.name === 'string' && payload.name.trim() ? payload.name.trim() : '';
    return { userId: payload.sub, name: name || 'Организатор' };
  } catch {
    return null; // токен не JWT или повреждён
  }
}

function parseAuth(header: string | undefined): Auth {
  if (!header) return null;
  const [scheme, ...rest] = header.split(' ');
  const value = rest.join(' ').trim();
  if (!value) return null;
  if (scheme === 'Bearer') {
    const claims = claimsFromJwt(value);
    return claims && { kind: 'organizer', ...claims };
  }
  if (scheme === 'Participant') return { kind: 'participant', token: value };
  return null;
}

const text = (v: unknown, field: string, min: number, max: number): string => {
  if (typeof v !== 'string' || v.trim().length < min || v.trim().length > max) {
    return invalid(field, `От ${min} до ${max} символов`);
  }
  return v.trim();
};

function fps(v: unknown): number {
  if (typeof v !== 'number' || !Number.isInteger(v) || v < 2 || v > 5) {
    return invalid('analysis_fps', 'Допустимо от 2 до 5');
  }
  return v;
}

function scheduledAt(v: unknown): string | null {
  if (v === null) return null;
  if (typeof v !== 'string' || Number.isNaN(Date.parse(v))) {
    return invalid('scheduled_at', 'Ожидается дата и время ISO 8601');
  }
  return new Date(v).toISOString();
}

// ---------- Приложение ----------

export interface AppOptions {
  gateway: LiveKitGateway;
  /** Адрес фронтенда для invite_url */
  origin?: string;
  now?: () => Date;
}

export function createApp({
  gateway,
  origin = 'http://localhost:5173',
  now = () => new Date(),
}: AppOptions) {
  let meetings: Meeting[] = [];
  let people = new Map<string, Stored[]>(); // по id встречи
  let tokens = new Map<string, { meetingId: string; participantId: string }>();
  let idempotency = new Map<string, { fingerprint: string; meeting: Meeting }>();
  // владелец встречи (claim sub); в ответы API не попадает, как и в контракте
  let owners = new Map<string, string>();
  // настройки анализа по умолчанию – у каждого организатора свои
  let settingsOf = new Map<
    string,
    { analysis_enabled_default: boolean; analysis_fps_default: number }
  >();

  function reset() {
    meetings = [];
    people = new Map();
    tokens = new Map();
    idempotency = new Map();
    owners = new Map();
    settingsOf = new Map();
  }

  const settingsFor = (userId: string) =>
    settingsOf.get(userId) ?? { analysis_enabled_default: true, analysis_fps_default: 3 };

  const iso = () => now().toISOString();
  const listOf = (id: string) => people.get(id) ?? people.set(id, []).get(id)!;
  const pub = (p: Stored): Participant => ({
    id: p.id,
    display_name: p.display_name,
    role: p.role,
    consent_state: p.consent_state,
    online: p.online,
    is_removed: p.is_removed,
    first_joined_at: p.first_joined_at,
    last_left_at: p.last_left_at,
  });

  const find = (id: string): Meeting => meetings.find((m) => m.id === id) ?? fail('not_found');
  const byInvite = (code: string): Meeting =>
    meetings.find((m) => m.invite_code === code) ?? fail('not_found');

  /**
   * Встреча организатора. Чужая встреча – `404 not_found`, как в контракте (docs/api/rest-api.md: «Встречи нет
   * или она чужая»): ответ не раскрывает, существует ли встреча.
   */
  function owned(org: { userId: string }, id: string): Meeting {
    const m = find(id);
    return owners.get(m.id) === org.userId ? m : fail('not_found');
  }

  function requireOrganizer(ctx: Ctx): Extract<Auth, { kind: 'organizer' }> {
    if (ctx.auth?.kind !== 'organizer') return fail('unauthorized');
    return ctx.auth;
  }

  /** Гость по Participant-токену. Удаленный участник для всех, кроме rejoin, – 401 (токен больше не действует). */
  function guest(ctx: Ctx, allowRemoved = false): { meeting: Meeting; participant: Stored } {
    if (ctx.auth?.kind !== 'participant') return fail('unauthorized');
    const info = tokens.get(ctx.auth.token);
    if (!info) return fail('unauthorized');
    const meeting = meetings.find((m) => m.id === info.meetingId);
    const participant = meeting && listOf(meeting.id).find((p) => p.id === info.participantId);
    if (!meeting || !participant) return fail('unauthorized');
    if (participant.is_removed && !allowRemoved) return fail('unauthorized');
    return { meeting, participant };
  }

  /** Кто сейчас в комнате: данные LiveKit плюс только что вошедшие, кто еще не успел подключиться. */
  async function refreshOnline(m: Meeting): Promise<Stored[]> {
    const list = listOf(m.id);
    const online = await gateway.listOnline(m.id);
    for (const p of list) {
      const inRoom = online?.includes(`p_${p.id}`) ?? false;
      const fresh = !p.seenOnline && now().getTime() - p.joinedAtMs < CONNECT_GRACE_MS;
      if (inRoom) p.seenOnline = true;
      const was = p.online;
      p.online = !p.is_removed && m.status === 'active' && (inRoom || fresh);
      if (was && !p.online && !p.last_left_at) p.last_left_at = iso();
    }
    return list;
  }

  const onlineCount = async (m: Meeting) => (await refreshOnline(m)).filter((p) => p.online).length;

  function recount(m: Meeting) {
    m.participants_count = listOf(m.id).filter((p) => !p.is_removed).length;
  }

  function requireOpen(m: Meeting) {
    if (m.status === 'ended') fail('meeting_ended', 'Встреча завершена');
    if (m.status === 'cancelled') fail('meeting_cancelled', 'Встреча отменена');
  }

  async function joinResult(m: Meeting, p: Stored) {
    const attributes = {
      'vks.role': p.role,
      'vks.consent': p.consent_state,
      'vks.kind': 'human',
    };
    return {
      participant_id: p.id,
      livekit_url: gateway.url,
      livekit_token: await gateway.createToken({
        room: m.id,
        identity: `p_${p.id}`,
        name: p.display_name,
        attributes,
      }),
      meeting: { id: m.id, title: m.title, status: m.status, analysis_enabled: m.analysis_enabled },
    };
  }

  function newParticipant(
    role: Stored['role'],
    name: string,
    consent: ConsentState,
    id: string = randomUUID(),
  ): Stored {
    const at = iso();
    return {
      id,
      display_name: name,
      role,
      consent_state: consent,
      online: true,
      is_removed: false,
      first_joined_at: at,
      last_left_at: null,
      joinedAtMs: now().getTime(),
      seenOnline: false,
    };
  }

  function consentOf(m: Meeting, decision: unknown): ConsentState {
    if (!m.analysis_enabled) return 'not_required';
    return decision === 'granted' ? 'granted' : 'denied';
  }

  const organizerId = (m: Meeting) => `org-${m.id}`;

  // ---------- Маршруты ----------

  const routes: { method: string; pattern: RegExp; handler: Handler }[] = [];
  const route = (method: string, path: string, handler: Handler) =>
    routes.push({
      method,
      pattern: new RegExp(`^${path.replace(/:\w+/g, '([^/]+)')}$`),
      handler,
    });

  route('POST', '/api/v1/meetings', (ctx) => {
    const org = requireOrganizer(ctx);
    const settings = settingsFor(org.userId);
    const header = ctx.headers['idempotency-key'];
    // ключ идемпотентности действует в пределах пользователя
    const key = typeof header === 'string' ? `${org.userId}:${header}` : undefined;
    const fingerprint = JSON.stringify(ctx.body);
    const seen = key ? idempotency.get(key) : undefined;
    if (seen) {
      if (seen.fingerprint !== fingerprint) return fail('idempotency_key_reused');
      return ok(seen.meeting, 201);
    }
    const title = text(ctx.body.title, 'title', 1, 200);
    if (ctx.body.analysis_fps !== undefined) fps(ctx.body.analysis_fps);
    if (ctx.body.analysis_enabled !== undefined && typeof ctx.body.analysis_enabled !== 'boolean') {
      invalid('analysis_enabled', 'Ожидается true или false');
    }
    const code = inviteCode();
    const meeting: Meeting = {
      id: randomUUID(),
      title,
      // встреча «сейчас» тоже scheduled: первый вход организатора активирует ее
      status: 'scheduled',
      invite_code: code,
      invite_url: `${origin}/j/${code}`,
      analysis_enabled:
        (ctx.body.analysis_enabled as boolean | undefined) ?? settings.analysis_enabled_default,
      analysis_fps: (ctx.body.analysis_fps as number | undefined) ?? settings.analysis_fps_default,
      scheduled_at: ctx.body.scheduled_at === undefined ? null : scheduledAt(ctx.body.scheduled_at),
      started_at: null,
      ended_at: null,
      participants_count: 0,
      created_at: iso(),
    };
    meetings.unshift(meeting);
    owners.set(meeting.id, org.userId);
    if (key) idempotency.set(key, { fingerprint, meeting });
    return ok(meeting, 201);
  });

  route('GET', '/api/v1/meetings', (ctx) => {
    const org = requireOrganizer(ctx);
    const statuses = ctx.query.get('status')?.split(',').filter(Boolean);
    const q = ctx.query.get('q')?.trim().toLowerCase();
    if (q && q.length > 100) invalid('q', 'Не длиннее 100 символов');
    const limit = Math.min(Math.max(Number(ctx.query.get('limit') ?? 20) || 20, 1), 100);
    const cursor = ctx.query.get('cursor');
    const offset = cursor ? Number(/^o:(\d+)$/.exec(cursor)?.[1]) : 0;
    if (!Number.isInteger(offset)) invalid('cursor', 'Неверный курсор');
    const from = ctx.query.get('from');
    const to = ctx.query.get('to');
    const key = (m: Meeting) => m.started_at ?? m.scheduled_at ?? m.created_at;

    const filtered = meetings
      .filter((m) => owners.get(m.id) === org.userId)
      .filter((m) => !statuses?.length || statuses.includes(m.status))
      .filter((m) => !q || m.title.toLowerCase().includes(q))
      .filter((m) => !from || key(m) >= from)
      .filter((m) => !to || key(m).slice(0, 10) <= to.slice(0, 10))
      .sort((a, b) => (key(a) < key(b) ? 1 : key(a) > key(b) ? -1 : 0));
    const end = offset + limit;
    return ok({
      items: filtered.slice(offset, end),
      next_cursor: end < filtered.length ? `o:${end}` : null,
    });
  });

  route('GET', '/api/v1/meetings/:id', (ctx) => {
    const org = requireOrganizer(ctx);
    return ok(owned(org, ctx.params[0]!));
  });

  route('PATCH', '/api/v1/meetings/:id', (ctx) => {
    const org = requireOrganizer(ctx);
    const m = owned(org, ctx.params[0]!);
    const { title, ...rest } = ctx.body;
    const newTitle = title === undefined ? undefined : text(title, 'title', 1, 200);
    if (ctx.body.analysis_fps !== undefined) fps(ctx.body.analysis_fps);
    const newSchedule =
      ctx.body.scheduled_at === undefined ? undefined : scheduledAt(ctx.body.scheduled_at);
    if (Object.keys(rest).length > 0 && m.status !== 'scheduled') fail('meeting_not_editable');
    if (newTitle !== undefined) m.title = newTitle;
    if (newSchedule !== undefined) m.scheduled_at = newSchedule;
    if (typeof ctx.body.analysis_enabled === 'boolean')
      m.analysis_enabled = ctx.body.analysis_enabled;
    if (typeof ctx.body.analysis_fps === 'number') m.analysis_fps = ctx.body.analysis_fps;
    return ok(m);
  });

  route('DELETE', '/api/v1/meetings/:id', async (ctx) => {
    const org = requireOrganizer(ctx);
    const m = owned(org, ctx.params[0]!);
    if (m.status === 'active') await gateway.deleteRoom(m.id);
    meetings = meetings.filter((x) => x.id !== m.id);
    people.delete(m.id);
    return noContent();
  });

  route('POST', '/api/v1/meetings/:id/join', async (ctx) => {
    const org = requireOrganizer(ctx);
    const m = owned(org, ctx.params[0]!);
    requireOpen(m);
    const decision = ctx.body.consent;
    if (decision !== undefined && decision !== 'granted' && decision !== 'denied') {
      invalid('consent', 'Ожидается granted или denied');
    }
    if (m.analysis_enabled && !decision) fail('consent_required');

    const list = listOf(m.id);
    let person = list.find((p) => p.id === organizerId(m));
    if (!person) {
      person = newParticipant('organizer', org.name, consentOf(m, decision), organizerId(m));
      list.unshift(person);
    }
    await refreshOnline(m);
    const inRoom = person.online && person.seenOnline;
    if (!inRoom && (await onlineCount(m)) >= MAX_PARTICIPANTS) fail('meeting_full');
    await gateway.ensureRoom(m.id);
    if (m.status === 'scheduled') {
      m.status = 'active';
      m.started_at = iso();
    }
    person.display_name = org.name;
    person.consent_state = consentOf(m, decision ?? person.consent_state);
    person.online = true;
    person.is_removed = false;
    person.joinedAtMs = now().getTime();
    person.last_left_at = null;
    recount(m);
    return ok(await joinResult(m, person));
  });

  route('POST', '/api/v1/meetings/:id/end', async (ctx) => {
    const org = requireOrganizer(ctx);
    const m = owned(org, ctx.params[0]!);
    if (m.status === 'cancelled') fail('meeting_cancelled');
    if (m.status !== 'ended') {
      m.status = 'ended';
      m.ended_at = iso();
      m.started_at ??= m.ended_at;
      for (const p of listOf(m.id)) {
        if (p.online) p.last_left_at = m.ended_at;
        p.online = false;
      }
      await gateway.deleteRoom(m.id);
    }
    return ok(m);
  });

  route('GET', '/api/v1/meetings/:id/participants', async (ctx) => {
    const org = requireOrganizer(ctx);
    const m = owned(org, ctx.params[0]!);
    return ok({ items: (await refreshOnline(m)).map(pub) });
  });

  route('POST', '/api/v1/meetings/:id/participants/:pid/mute', async (ctx) => {
    const org = requireOrganizer(ctx);
    const m = owned(org, ctx.params[0]!);
    const kind = ctx.body.kind;
    if (kind !== 'audio' && kind !== 'video') invalid('kind', 'Ожидается audio или video');
    if (m.status === 'ended') fail('meeting_ended');
    const p = listOf(m.id).find((x) => x.id === ctx.params[1]) ?? fail('not_found');
    await gateway.mute(m.id, `p_${p.id}`, kind as 'audio' | 'video');
    return noContent();
  });

  route('POST', '/api/v1/meetings/:id/participants/:pid/remove', async (ctx) => {
    const org = requireOrganizer(ctx);
    const m = owned(org, ctx.params[0]!);
    const p = listOf(m.id).find((x) => x.id === ctx.params[1]) ?? fail('not_found');
    await gateway.removeParticipant(m.id, `p_${p.id}`);
    p.is_removed = true;
    p.online = false;
    p.last_left_at = iso();
    recount(m);
    return noContent();
  });

  route('GET', '/api/v1/join/:code', (ctx) => {
    const m = byInvite(ctx.params[0]!);
    return ok({
      title: m.title,
      organizer_name:
        listOf(m.id).find((p) => p.role === 'organizer')?.display_name ?? 'Организатор',
      status: m.status,
      scheduled_at: m.scheduled_at,
      analysis_enabled: m.analysis_enabled,
      consent_notice: m.analysis_enabled ? CONSENT_NOTICE : null,
    });
  });

  route('POST', '/api/v1/join/:code', async (ctx) => {
    const m = byInvite(ctx.params[0]!);
    const name = text(ctx.body.display_name, 'display_name', 1, 64);
    requireOpen(m);
    if (m.status === 'scheduled') fail('meeting_not_started');
    if ((await onlineCount(m)) >= MAX_PARTICIPANTS) fail('meeting_full');
    if (m.analysis_enabled) {
      if (ctx.body.consent !== 'granted' && ctx.body.consent !== 'denied') fail('consent_required');
      if (ctx.body.notice_version !== CONSENT_NOTICE.version) fail('notice_outdated');
    }
    const person = newParticipant('guest', name, consentOf(m, ctx.body.consent));
    listOf(m.id).push(person);
    recount(m);
    const token = `pt_${randomBytes(24).toString('base64url')}`;
    tokens.set(token, { meetingId: m.id, participantId: person.id });
    return ok({ ...(await joinResult(m, person)), participant_token: token });
  });

  route('PUT', '/api/v1/participants/me/consent', async (ctx) => {
    const decision = ctx.body.decision;
    if (decision !== 'granted' && decision !== 'revoked') {
      invalid('decision', 'Ожидается granted или revoked');
    }
    let m: Meeting;
    let person: Stored;
    if (ctx.auth?.kind === 'organizer') {
      m = owned(
        ctx.auth,
        ctx.query.get('meeting_id') ?? fail('validation_error', 'Нужен параметр meeting_id'),
      );
      person = listOf(m.id).find((p) => p.id === organizerId(m)) ?? fail('not_found');
    } else {
      ({ meeting: m, participant: person } = guest(ctx));
    }
    if (m.status === 'ended') fail('meeting_ended');
    if (!m.analysis_enabled) fail('analysis_disabled');
    person.consent_state = decision as ConsentState;
    const synced = await gateway.updateAttributes(m.id, `p_${person.id}`, {
      'vks.consent': decision as string,
    });
    return ok({ consent_state: person.consent_state, synced }, synced ? 200 : 202);
  });

  route('POST', '/api/v1/participants/me/rejoin', async (ctx) => {
    const { meeting: m, participant } = guest(ctx, true);
    if (participant.is_removed) fail('participant_removed');
    if (m.status === 'ended' || m.status === 'cancelled') fail('meeting_ended');
    participant.online = true;
    participant.seenOnline = false;
    participant.joinedAtMs = now().getTime();
    return ok(await joinResult(m, participant));
  });

  route('GET', '/api/v1/settings', (ctx) => {
    return ok(settingsFor(requireOrganizer(ctx).userId));
  });

  route('PUT', '/api/v1/settings', (ctx) => {
    const org = requireOrganizer(ctx);
    if (typeof ctx.body.analysis_enabled_default !== 'boolean') {
      invalid('analysis_enabled_default', 'Ожидается true или false');
    }
    const settings = {
      analysis_enabled_default: ctx.body.analysis_enabled_default,
      analysis_fps_default: fps(ctx.body.analysis_fps_default),
    };
    settingsOf.set(org.userId, settings);
    return ok(settings);
  });

  // ---------- HTTP ----------

  async function readBody(req: IncomingMessage): Promise<Record<string, unknown>> {
    const chunks: Buffer[] = [];
    let size = 0;
    for await (const chunk of req) {
      size += (chunk as Buffer).length;
      if (size > MAX_BODY) throw new HttpError('validation_error', 'Тело запроса слишком большое');
      chunks.push(chunk as Buffer);
    }
    if (size === 0) return {};
    try {
      const parsed: unknown = JSON.parse(Buffer.concat(chunks).toString());
      if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      // ниже – одна и та же ошибка для любого неверного тела
    }
    throw new HttpError('validation_error', 'Тело запроса должно быть JSON-объектом');
  }

  function send(res: ServerResponse, reply: Reply, requestId: string) {
    const body = reply.body === undefined ? '' : JSON.stringify(reply.body);
    res.writeHead(reply.status, {
      'Content-Type': 'application/json',
      'X-Request-ID': requestId,
      'Content-Length': Buffer.byteLength(body),
    });
    res.end(body);
  }

  function sendError(res: ServerResponse, error: unknown, requestId: string) {
    const known = error instanceof HttpError;
    const unavailable = error instanceof LiveKitUnavailableError;
    const code: Code = known ? error.code : unavailable ? 'livekit_unavailable' : 'internal_error';
    const status = CODES[code];
    const message = known
      ? error.message
      : unavailable
        ? 'Видеосервер недоступен'
        : 'Внутренняя ошибка dev-api';
    const body = JSON.stringify({
      type: 'about:blank',
      title: message,
      status,
      code,
      detail: message,
      request_id: requestId,
      ...(known && error.errors ? { errors: error.errors } : {}),
    });
    res.writeHead(status, {
      'Content-Type': 'application/problem+json',
      'X-Request-ID': requestId,
      'Content-Length': Buffer.byteLength(body),
    });
    res.end(body);
  }

  async function handle(req: IncomingMessage, res: ServerResponse) {
    const requestId = randomUUID();
    try {
      // dev-сервер без аутентификации: чужие имена хоста (DNS rebinding) не принимаем
      const host = (req.headers.host ?? '').replace(/:\d+$/, '');
      if (host !== '127.0.0.1' && host !== 'localhost') {
        res.writeHead(403).end();
        return;
      }
      const url = new URL(req.url ?? '/', 'http://127.0.0.1');
      for (const r of routes) {
        const match = r.pattern.exec(url.pathname);
        if (r.method !== req.method || !match) continue;
        const body = req.method === 'GET' || req.method === 'DELETE' ? {} : await readBody(req);
        const params = match.slice(1).map(decodeURIComponent);
        const reply = await r.handler({
          params,
          query: url.searchParams,
          body,
          auth: parseAuth(req.headers.authorization),
          headers: req.headers,
        });
        return send(res, reply, requestId);
      }
      throw new HttpError('not_found', 'Маршрут не поддерживается dev-api');
    } catch (error) {
      if (!(error instanceof HttpError) && !(error instanceof LiveKitUnavailableError)) {
        console.error('dev-api:', error);
      }
      sendError(res, error, requestId);
    }
  }

  return { handle, reset };
}
