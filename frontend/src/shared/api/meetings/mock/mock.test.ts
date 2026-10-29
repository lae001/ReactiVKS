import { clearParticipantToken, setParticipantToken } from '@/shared/lib/participant-session';

import { MOCK_CONSENT_NOTICE } from './fixtures';

import { createMockMeetingsApi } from './index';

const FIXED_NOW = new Date('2026-11-20T10:00:00Z');
const NOTICE = MOCK_CONSENT_NOTICE.version;

function setup() {
  return createMockMeetingsApi(() => FIXED_NOW);
}

/** Гость входит по коду и «получает» токен в sessionStorage, как это делает лобби. */
async function enterAsGuest(api: ReturnType<typeof setup>, code = 'demoactive') {
  const joined = await api.joinMeeting(code, {
    display_name: 'Анна',
    consent: 'granted',
    notice_version: NOTICE,
  });
  setParticipantToken(joined.participant_token);
  return joined;
}

describe('mock: коды ошибок реестра (те, что воспроизводимы без сети)', () => {
  // forbidden, too_many_requests, user_blocked, livekit_unavailable, internal_error приходят только
  // от настоящего сервиса и проверяются в http.test.ts.

  it('not_found: встреча и приглашение', async () => {
    const api = setup();
    await expect(api.getMeeting('нет')).rejects.toMatchObject({ code: 'not_found', status: 404 });
    await expect(api.getJoinInfo('zzzzzzzzzz')).rejects.toMatchObject({ code: 'not_found' });
    await expect(api.deleteMeeting('нет')).rejects.toMatchObject({ code: 'not_found' });
  });

  it('meeting_not_started: гость в запланированную встречу', async () => {
    await expect(
      setup().joinMeeting('demolater2', {
        display_name: 'Анна',
        consent: 'granted',
        notice_version: NOTICE,
      }),
    ).rejects.toMatchObject({ code: 'meeting_not_started', status: 409 });
  });

  it('meeting_ended: вход гостя, вход организатора, повторный вход по токену', async () => {
    const api = setup();
    await expect(
      api.joinMeeting('demoended2', { display_name: 'Анна', consent: 'granted' }),
    ).rejects.toMatchObject({ code: 'meeting_ended' });
    await expect(api.joinAsOrganizer('m-ended', 'granted')).rejects.toMatchObject({
      code: 'meeting_ended',
    });

    await enterAsGuest(api);
    await api.endMeeting('m-active');
    await expect(api.rejoin()).rejects.toMatchObject({ code: 'meeting_ended' });
    await expect(api.muteParticipant('m-active', 'p-anna', 'audio')).rejects.toMatchObject({
      code: 'meeting_ended',
    });
    await expect(api.setConsent('revoked')).rejects.toMatchObject({ code: 'meeting_ended' });
  });

  it('meeting_cancelled: вход гостя и организатора, завершение', async () => {
    const api = setup();
    await expect(
      api.joinMeeting('democancel', { display_name: 'Анна', consent: 'granted' }),
    ).rejects.toMatchObject({ code: 'meeting_cancelled', status: 409 });
    await expect(api.joinAsOrganizer('m-cancelled', 'granted')).rejects.toMatchObject({
      code: 'meeting_cancelled',
    });
    await expect(api.endMeeting('m-cancelled')).rejects.toMatchObject({
      code: 'meeting_cancelled',
    });
  });

  it('meeting_not_started: не начатую встречу не завершают, а отменяют', async () => {
    const api = setup();
    await expect(api.endMeeting('m-later')).rejects.toMatchObject({
      code: 'meeting_not_started',
      status: 409,
    });
    await expect(api.getMeeting('m-later')).resolves.toMatchObject({ status: 'scheduled' });
    await api.deleteMeeting('m-later');
    await expect(api.getMeeting('m-later')).rejects.toMatchObject({ code: 'not_found' });
  });

  it('mute и remove после завершения: meeting_ended', async () => {
    const api = setup();
    const guest = await enterAsGuest(api);
    await api.endMeeting('m-active');
    await expect(api.removeParticipant('m-active', guest.participant_id)).rejects.toMatchObject({
      code: 'meeting_ended',
      status: 409,
    });
    await expect(
      api.muteParticipant('m-active', guest.participant_id, 'video'),
    ).rejects.toMatchObject({ code: 'meeting_ended' });
  });

  it('remove организатора: 422 validation_error, он остается во встрече', async () => {
    const api = setup();
    await api.joinAsOrganizer('m-active', 'granted');
    const organizer = (await api.listParticipants('m-active')).find((p) => p.role === 'organizer')!;
    await expect(api.removeParticipant('m-active', organizer.id)).rejects.toMatchObject({
      code: 'validation_error',
      status: 422,
    });
    const after = (await api.listParticipants('m-active')).find((p) => p.id === organizer.id);
    expect(after?.is_removed).toBe(false);
  });

  it('meeting_full: 10 онлайн – одиннадцатый не входит, и гость, и организатор', async () => {
    const api = setup();
    await expect(api.joinMeeting('demofull22', { display_name: 'Анна' })).rejects.toMatchObject({
      code: 'meeting_full',
      status: 409,
    });
    await expect(api.joinAsOrganizer('m-full')).rejects.toMatchObject({ code: 'meeting_full' });

    // освободилось место – вход возможен
    await api.removeParticipant('m-full', 'p-full-1');
    await expect(api.joinMeeting('demofull22', { display_name: 'Анна' })).resolves.toBeDefined();
  });

  it('consent_required: анализ включен, решение не передано', async () => {
    const api = setup();
    await expect(
      api.joinMeeting('demoactive', { display_name: 'Анна', notice_version: NOTICE }),
    ).rejects.toMatchObject({ code: 'consent_required', status: 409 });
    await expect(api.joinAsOrganizer('m-active')).rejects.toMatchObject({
      code: 'consent_required',
    });
    // без анализа решение не нужно
    await expect(api.joinMeeting('demonoanal', { display_name: 'Анна' })).resolves.toBeDefined();
  });

  it('notice_outdated: версия уведомления не совпала с текущей', async () => {
    await expect(
      setup().joinMeeting('demoactive', {
        display_name: 'Анна',
        consent: 'granted',
        notice_version: 'v0',
      }),
    ).rejects.toMatchObject({ code: 'notice_outdated', status: 409 });
  });

  it('participant_removed: удаленный не может вернуться по своему токену', async () => {
    const api = setup();
    const joined = await enterAsGuest(api);
    await expect(api.rejoin()).resolves.toMatchObject({ participant_id: joined.participant_id });

    await api.removeParticipant('m-active', joined.participant_id);
    await expect(api.rejoin()).rejects.toMatchObject({
      code: 'participant_removed',
      status: 409,
    });
  });

  it('analysis_disabled: согласие во встрече без анализа', async () => {
    const api = setup();
    await enterAsGuest(api, 'demonoanal');
    await expect(api.setConsent('revoked')).rejects.toMatchObject({
      code: 'analysis_disabled',
      status: 409,
    });
    await expect(api.setConsent('granted', { meetingId: 'm-noanal' })).rejects.toMatchObject({
      code: 'analysis_disabled',
    });
  });

  it('meeting_not_editable: параметры начатой встречи, но не название', async () => {
    const api = setup();
    await expect(api.updateMeeting('m-active', { analysis_fps: 4 })).rejects.toMatchObject({
      code: 'meeting_not_editable',
      status: 409,
    });
    await expect(api.updateMeeting('m-active', { title: 'Новое' })).resolves.toMatchObject({
      title: 'Новое',
    });
    await expect(api.updateMeeting('m-later', { analysis_fps: 4 })).resolves.toMatchObject({
      analysis_fps: 4,
    });
  });

  it('idempotency_key_reused: тот же ключ с другим телом; с тем же – та же встреча', async () => {
    const api = setup();
    const first = await api.createMeeting({ title: 'Планерка' }, 'key-1');
    await expect(api.createMeeting({ title: 'Планерка' }, 'key-1')).resolves.toEqual(first);
    const { items } = await api.listMeetings({ q: 'Планерка' });
    expect(items.filter((m) => m.title === 'Планерка')).toHaveLength(1);

    await expect(api.createMeeting({ title: 'Другая' }, 'key-1')).rejects.toMatchObject({
      code: 'idempotency_key_reused',
      status: 409,
    });
  });

  it('unauthorized: гость без токена или с неизвестным токеном', async () => {
    const api = setup();
    await expect(api.rejoin()).rejects.toMatchObject({ code: 'unauthorized', status: 401 });
    setParticipantToken('pt_unknown');
    await expect(api.setConsent('revoked')).rejects.toMatchObject({ code: 'unauthorized' });
    clearParticipantToken();
  });

  it('validation_error: название, имя, частота кадров', async () => {
    const api = setup();
    await expect(api.createMeeting({ title: '   ' })).rejects.toMatchObject({
      code: 'validation_error',
      status: 422,
    });
    await expect(api.createMeeting({ title: 'x'.repeat(201) })).rejects.toMatchObject({
      code: 'validation_error',
    });
    await expect(api.createMeeting({ title: 'ok', analysis_fps: 6 })).rejects.toMatchObject({
      code: 'validation_error',
    });
    await expect(api.joinMeeting('demonoanal', { display_name: '' })).rejects.toMatchObject({
      code: 'validation_error',
      errors: [{ loc: ['body', 'display_name'] }],
    });
    await expect(
      api.putSettings({ analysis_enabled_default: true, analysis_fps_default: 1 }),
    ).rejects.toMatchObject({ code: 'validation_error' });
  });
});

describe('mock: список встреч', () => {
  it('сортировка по coalesce(started_at, scheduled_at, created_at) по убыванию', async () => {
    const { items } = await setup().listMeetings({ limit: 100 });
    const keys = items.map((m) => m.started_at ?? m.scheduled_at ?? m.created_at);
    expect(keys).toEqual([...keys].sort().reverse());
  });

  it('фильтр по статусам и поиск по подстроке без учета регистра', async () => {
    const api = setup();
    const ended = await api.listMeetings({ status: ['ended'] });
    expect(ended.items.map((m) => m.id).sort()).toEqual(['m-ended', 'm-ended-2']);

    const several = await api.listMeetings({ status: ['active', 'scheduled'] });
    expect(several.items.every((m) => ['active', 'scheduled'].includes(m.status))).toBe(true);

    const found = await api.listMeetings({ q: 'ПЛАНЕРКА' });
    expect(found.items.map((m) => m.id)).toEqual(['m-active']);
    expect((await api.listMeetings({ q: 'нет такой' })).items).toEqual([]);
  });

  it('курсор: страницы без повторов и пропусков, на последней next_cursor = null', async () => {
    const api = setup();
    const all = (await api.listMeetings({ limit: 100 })).items.map((m) => m.id);
    const seen: string[] = [];
    let cursor: string | undefined;
    let pages = 0;
    do {
      const page = await api.listMeetings({ limit: 3, cursor });
      seen.push(...page.items.map((m) => m.id));
      cursor = page.next_cursor ?? undefined;
      pages += 1;
    } while (cursor);
    expect(seen).toEqual(all);
    expect(pages).toBe(Math.ceil(all.length / 3));
  });

  it('удаленные не возвращаются', async () => {
    const api = setup();
    await api.deleteMeeting('m-later');
    const { items } = await api.listMeetings({ limit: 100 });
    expect(items.some((m) => m.id === 'm-later')).toBe(false);
  });
});

describe('mock: жизненный цикл встречи', () => {
  it('создание: invite_code по формату контракта, настройки по умолчанию из /settings', async () => {
    const api = setup();
    await api.putSettings({ analysis_enabled_default: false, analysis_fps_default: 5 });
    const m = await api.createMeeting({ title: 'Интервью' });
    expect(m).toMatchObject({
      title: 'Интервью',
      status: 'scheduled',
      analysis_enabled: false,
      analysis_fps: 5,
      participants_count: 0,
      created_at: FIXED_NOW.toISOString(),
    });
    expect(m.invite_code).toMatch(/^[a-z2-7]{10}$/);
    expect(m.invite_url).toMatch(new RegExp(`/j/${m.invite_code}$`));
  });

  it('первый вход организатора активирует встречу; затем гость входит', async () => {
    const api = setup();
    const m = await api.createMeeting({ title: 'Сейчас', analysis_enabled: false });
    await expect(api.joinMeeting(m.invite_code, { display_name: 'Анна' })).rejects.toMatchObject({
      code: 'meeting_not_started',
    });

    const result = await api.joinAsOrganizer(m.id);
    expect(result).toMatchObject({
      livekit_url: expect.stringMatching(/^wss?:\/\//) as string,
      meeting: { id: m.id, status: 'active', analysis_enabled: false },
    });
    expect(await api.getMeeting(m.id)).toMatchObject({
      status: 'active',
      started_at: FIXED_NOW.toISOString(),
    });

    const guest = await api.joinMeeting(m.invite_code, { display_name: ' Анна ' });
    expect(guest.participant_token).toMatch(/^pt_/);
    const people = await api.listParticipants(m.id);
    expect(people.map((p) => [p.role, p.display_name, p.consent_state])).toEqual([
      ['organizer', 'Иван Петров', 'not_required'],
      ['guest', 'Анна', 'not_required'],
    ]);
  });

  it('завершение идемпотентно, все участники уходят в офлайн', async () => {
    const api = setup();
    const first = await api.endMeeting('m-active');
    expect(first).toMatchObject({ status: 'ended', ended_at: FIXED_NOW.toISOString() });
    await expect(api.endMeeting('m-active')).resolves.toMatchObject({ status: 'ended' });
    expect((await api.listParticipants('m-active')).every((p) => !p.online)).toBe(true);
  });

  it('согласие: гость по токену и организатор по meetingId', async () => {
    const api = setup();
    const joined = await enterAsGuest(api);
    await expect(api.setConsent('revoked')).resolves.toEqual({
      consent_state: 'revoked',
      synced: true,
    });
    const me = (await api.listParticipants('m-active')).find((p) => p.id === joined.participant_id);
    expect(me?.consent_state).toBe('revoked');

    await expect(api.setConsent('granted', { meetingId: 'm-active' })).resolves.toMatchObject({
      consent_state: 'granted',
    });
  });

  it('удаление встречи убирает ее и участников', async () => {
    const api = setup();
    await api.deleteMeeting('m-active');
    await expect(api.getMeeting('m-active')).rejects.toMatchObject({ code: 'not_found' });
  });

  it('reset возвращает исходные данные', async () => {
    const api = setup();
    await api.deleteMeeting('m-active');
    api.reset();
    await expect(api.getMeeting('m-active')).resolves.toBeDefined();
  });
});
