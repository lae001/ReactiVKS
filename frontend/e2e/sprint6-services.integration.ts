import { expect, test } from '@playwright/test';
import { TRACK_PEER_CONNECTIONS, measureRemoteVideo, inboundAudioBytes } from './media-helpers';

// Настоящие auth/meeting/realtime/analytics/LiveKit. Никаких page.route/routeWebSocket.
// При отсутствии Kafka проверяется доступная часть, включая сохранение звонка при unavailable.
test('реальные сервисы: согласие в комнате, snapshot, media при unavailable и ошибки отсутствующих операций', async ({
  browser,
}, info) => {
  test.skip(
    !process.env.E2E_REAL_EMAIL || !process.env.E2E_REAL_PASSWORD,
    'Нужна тестовая учётная запись',
  );
  const orgContext = await browser.newContext({
    permissions: ['camera', 'microphone'],
    locale: 'ru-RU',
  });
  const guestContext = await browser.newContext({
    permissions: ['camera', 'microphone'],
    locale: 'ru-RU',
  });
  const org = await orgContext.newPage();
  const guest = await guestContext.newPage();
  await org.addInitScript(TRACK_PEER_CONNECTIONS);
  await guest.addInitScript(TRACK_PEER_CONNECTIONS);
  await org.addInitScript(() => {
    const Native = window.WebSocket;
    const sockets: WebSocket[] = [];
    (window as unknown as { __emotionSockets: WebSocket[] }).__emotionSockets = sockets;
    window.WebSocket = class extends Native {
      constructor(url: string | URL, protocols?: string | string[]) {
        super(url, protocols);
        if (String(url).endsWith('/ws')) sockets.push(this);
      }
    };
  });
  const snapshots: {
    analysis: { state: string };
    participants: { participant_id: string; state: string; last: unknown }[];
  }[] = [];
  let guestEmotionConnections = 0;
  guest.on('websocket', (ws) => {
    if (ws.url().endsWith('/ws')) guestEmotionConnections++;
  });
  org.on('websocket', (ws) => {
    if (ws.url().endsWith('/ws'))
      ws.on('framereceived', ({ payload }) => {
        const message = JSON.parse(String(payload));
        if (message.type === 'subscribed') snapshots.push(message.snapshot);
      });
  });
  let meetingId = '';
  let access = '';
  const evidence: Record<string, unknown> = {
    browser: browser.version(),
    services: 'real',
    devices: 'virtual',
  };
  try {
    await org.goto('/login');
    await org.getByLabel('Электронная почта').fill(process.env.E2E_REAL_EMAIL!);
    await org.getByLabel('Пароль').fill(process.env.E2E_REAL_PASSWORD!);
    const login = org.waitForResponse((r) => r.url().endsWith('/auth/login') && r.status() === 200);
    await org.getByRole('button', { name: 'Войти', exact: true }).click();
    access = (await (await login).json()).access_token;
    await expect(org).toHaveURL(/\/meetings$/);
    await org.getByRole('link', { name: /Запланировать/ }).click();
    await org.getByLabel('Название', { exact: true }).fill('Интеграция спринта 6');
    await org.getByRole('checkbox', { name: /Анализировать эмоции/ }).check();
    const created = org.waitForResponse(
      (r) =>
        new URL(r.url()).pathname === '/api/v1/meetings' &&
        r.request().method() === 'POST' &&
        r.status() === 201,
    );
    await org.getByRole('button', { name: 'Создать и получить ссылку' }).click();
    const meeting = await (await created).json();
    meetingId = meeting.id;
    await guest.goto(`/j/${meeting.invite_code}`);
    await guest.getByLabel('Как вас представить').fill('Тестовый гость');
    await guest.getByRole('radio', { name: /Участвую без анализа/ }).check();
    await org.getByRole('link', { name: 'Открыть карточку' }).click();
    const joinOrg = org.waitForResponse(
      (r) => r.url().endsWith(`/${meetingId}/join`) && r.status() === 200,
    );
    await org.getByRole('button', { name: 'Начать встречу' }).click();
    const orgParticipant = (await (await joinOrg).json()).participant_id;
    await expect(org.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
    const joinGuest = guest.waitForResponse(
      (r) =>
        /\/api\/v1\/join\//.test(r.url()) && r.request().method() === 'POST' && r.status() === 200,
    );
    await guest.getByRole('button', { name: 'Войти во встречу' }).click();
    const guestParticipant = (await (await joinGuest).json()).participant_id;
    await expect(guest.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
    await expect
      .poll(
        async () =>
          (
            await (
              await org.request.get(`/api/v1/meetings/${meetingId}/participants`, {
                headers: { Authorization: `Bearer ${access}` },
              })
            ).json()
          ).items.filter((p: { online: boolean }) => p.online).length,
      )
      .toBe(2);
    const beforeSnapshots = snapshots.length;
    await org.evaluate(() =>
      (window as unknown as { __emotionSockets: WebSocket[] }).__emotionSockets.forEach((ws) =>
        ws.close(),
      ),
    );
    await expect.poll(() => snapshots.length).toBeGreaterThan(beforeSnapshots);
    const snapshot = snapshots.at(-1)!;
    expect(snapshot.participants.find((p) => p.participant_id === guestParticipant)).toMatchObject({
      state: 'no_consent',
      last: null,
    });
    evidence.snapshot = { analysis: snapshot.analysis, guestWithoutConsent: true };
    await org.getByRole('button', { name: 'Эмоции', exact: true }).click();
    await expect(org.getByRole('tabpanel')).toContainText('Анализ недоступен');
    for (const [name, page] of [
      ['organizer', org],
      ['guest', guest],
    ] as const) {
      const results = [];
      for (const decision of ['granted', 'revoked', 'granted', 'revoked']) {
        const response = page.waitForResponse(
          (r) =>
            new URL(r.url()).pathname.endsWith('/participants/me/consent') &&
            r.request().method() === 'PUT',
        );
        await page.getByRole('button', { name: 'Анализ моих эмоций' }).click();
        const result = await response;
        expect([200, 202]).toContain(result.status());
        const body = await result.json();
        expect(body).toMatchObject({ consent_state: decision, synced: result.status() === 200 });
        await expect(page.getByRole('button', { name: 'Анализ моих эмоций' })).toHaveAttribute(
          'aria-pressed',
          decision === 'granted' ? 'true' : 'false',
        );
        results.push({ decision, status: result.status(), synced: body.synced });
      }
      evidence[name + 'Consent'] = results;
    }
    await org.getByRole('button', { name: 'Анализ моих эмоций' }).click();
    await expect(org.getByRole('button', { name: 'Анализ моих эмоций' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await org.reload();
    await expect(org.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
    await expect(org.getByRole('button', { name: 'Анализ моих эмоций' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    evidence.consentSurvivesReload = true;
    await org.getByRole('button', { name: 'Анализ моих эмоций' }).click();
    if ((await org.getByRole('tabpanel').count()) === 0)
      await org.getByRole('button', { name: 'Эмоции', exact: true }).click();
    expect(guestEmotionConnections).toBe(0);
    const audioBefore = {
      org: await inboundAudioBytes(org),
      guest: await inboundAudioBytes(guest),
    };
    evidence.organizerToGuest = await measureRemoteVideo(guest, `p_${orgParticipant}`);
    evidence.guestToOrganizer = await measureRemoteVideo(org, `p_${guestParticipant}`);
    await expect.poll(() => inboundAudioBytes(org)).toBeGreaterThan(audioBefore.org);
    await expect.poll(() => inboundAudioBytes(guest)).toBeGreaterThan(audioBefore.guest);
    evidence.audio = {
      organizer: [audioBefore.org, await inboundAudioBytes(org)],
      guest: [audioBefore.guest, await inboundAudioBytes(guest)],
    };
    await org.getByLabel('Название отметки').fill('Интеграционный момент');
    await org.getByRole('button', { name: 'Отметить момент' }).click();
    await expect(org.getByRole('tabpanel')).toContainText('Не удалось сохранить отметку');
    await expect(org.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
    await expect(guest.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
    await org.getByRole('button', { name: 'Завершить встречу', exact: true }).click();
    await org
      .getByRole('alertdialog')
      .getByRole('button', { name: 'Завершить встречу', exact: true })
      .click();
    await expect(org).toHaveURL(new RegExp(`/meetings/${meetingId}$`));
    await expect(org.getByText('Отчёт недоступен:', { exact: false })).toBeVisible();
    await org.getByText('Скачать CSV').click();
    await expect(org.getByText(/Экспорт недоступен/)).toBeVisible();
    evidence.guestEmotionConnections = guestEmotionConnections;
    await info.attach('real-services', {
      body: JSON.stringify(evidence, null, 2),
      contentType: 'application/json',
    });
  } finally {
    if (meetingId && access)
      await fetch(`http://127.0.0.1:8013/api/v1/meetings/${meetingId}/end`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${access}` },
        signal: AbortSignal.timeout(10000),
      });
    await orgContext.close();
    await guestContext.close();
  }
});
