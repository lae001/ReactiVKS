import { expect, test, type WebSocketRoute } from '@playwright/test';

// Контрактный стенд спринта 5: auth, meeting и медиасвязь настоящие;
// отсутствующие realtime/analytics и изменение согласия подменены явно только в этом тесте.
test('контракт UC-4–UC-5: эмоции, отметка, reconnect, отзыв и отчёт той же встречи', async ({
  browser,
}) => {
  test.skip(
    !process.env.E2E_REAL_EMAIL || !process.env.E2E_REAL_PASSWORD,
    'нужна тестовая учётная запись',
  );
  const context = await browser.newContext({
    permissions: ['camera', 'microphone'],
    locale: 'ru-RU',
  });
  const page = await context.newPage();
  const labels = ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral'];
  const p = [0, 0, 0, 0.7, 0, 0, 0.3];
  let socket: WebSocketRoute;
  let connections = 0;
  let authenticated = false;
  let meetingId = '';
  let participantId = '';
  let since = '';
  let reportRequests = 0;
  let reportReady = false;
  const markers: {
    id: string;
    ts: string;
    label: string;
    kind: string;
    participant_id: null;
    details: object;
  }[] = [];
  const started = new Date().toISOString();
  const snapshot = () => ({
    type: 'subscribed',
    meeting_id: meetingId,
    snapshot: {
      labels,
      analysis: { state: 'active' },
      participants: participantId
        ? [
            {
              participant_id: participantId,
              display_name: 'Тест Организатор',
              role: 'organizer',
              state: 'analyzing',
              last: null,
            },
          ]
        : [],
    },
  });
  await page.routeWebSocket('**/ws', (ws) => {
    socket = ws;
    connections++;
    ws.onMessage((raw) => {
      const message = JSON.parse(String(raw));
      if (message.type === 'auth') {
        authenticated = typeof message.token === 'string' && message.token.length > 20;
        ws.send(
          JSON.stringify({
            type: 'welcome',
            user_id: 'contract',
            server_time: new Date().toISOString(),
          }),
        );
      }
      if (message.type === 'subscribe') {
        meetingId = message.meeting_id;
        ws.send(JSON.stringify(snapshot()));
      }
      if (message.type === 'ping')
        ws.send(JSON.stringify({ type: 'pong', server_time: new Date().toISOString() }));
    });
  });
  await page.route('**/api/v1/reports/**', async (route) => {
    const url = new URL(route.request().url());
    expect(url.pathname).toContain(`/reports/${meetingId}`);
    if (url.pathname.endsWith('/markers')) {
      const body = route.request().postDataJSON();
      const marker = {
        id: 'contract-marker',
        ts: new Date().toISOString(),
        label: body.label,
        kind: 'manual',
        participant_id: null,
        details: {},
      };
      markers.push(marker);
      await route.fulfill({ status: 201, json: marker });
      return;
    }
    if (url.pathname.endsWith('/series')) {
      since = url.searchParams.get('since') ?? since;
      await route.fulfill({
        json: {
          resolution: '1s',
          labels,
          series: [{ participant_id: participantId, points: [{ ts: started, p, face_ratio: 1 }] }],
        },
      });
      return;
    }
    reportRequests++;
    const distribution = Object.fromEntries(labels.map((label, i) => [label, p[i]]));
    await route.fulfill({
      json: {
        meeting_id: meetingId,
        status: reportReady ? 'ready' : 'pending',
        model_version: 'contract-fixture',
        meeting: {
          title: 'Контрактная встреча',
          started_at: started,
          ended_at: new Date().toISOString(),
          duration_s: 60,
        },
        summary: {
          overall: { distribution, face_detected_ratio: 1, negative_share: 0 },
          participants: [
            {
              participant_id: participantId,
              display_name: 'Тест Организатор',
              consent: 'revoked',
              distribution,
              dominant: 'happy',
              face_detected_ratio: 1,
              analyzed_seconds: 5,
            },
          ],
        },
        markers,
        disclaimer: 'Контрактные данные: ML не запускался.',
      },
    });
  });
  const decisions: string[] = [];
  await page.route('**/api/v1/participants/me/consent*', async (route) => {
    const decision = route.request().postDataJSON().decision;
    expect(['granted', 'revoked']).toContain(decision);
    decisions.push(decision);
    await route.fulfill({ json: { consent_state: decision, synced: true } });
    socket.send(
      JSON.stringify({
        type: 'participant.status',
        meeting_id: meetingId,
        participant_id: participantId,
        display_name: 'Тест Организатор',
        state: decision === 'granted' ? 'analyzing' : 'no_consent',
      }),
    );
  });
  await page.goto('/login');
  await page.getByLabel('Электронная почта').fill(process.env.E2E_REAL_EMAIL!);
  await page.getByLabel('Пароль').fill(process.env.E2E_REAL_PASSWORD!);
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  await expect(page).toHaveURL(/\/meetings$/);
  const joined = page.waitForResponse(
    (r) => /\/meetings\/[^/]+\/join$/.test(new URL(r.url()).pathname) && r.status() === 200,
  );
  await page.getByRole('button', { name: /Начать сейчас/ }).click();
  participantId = (await (await joined).json()).participant_id;
  await expect(page.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
  await expect.poll(() => authenticated).toBe(true);
  socket!.send(JSON.stringify(snapshot()));
  await expect(page.getByRole('button', { name: 'Анализ моих эмоций' })).toHaveAttribute(
    'aria-pressed',
    'false',
  );
  await page.getByRole('button', { name: 'Анализ моих эмоций' }).click();
  await expect(page.getByRole('button', { name: 'Анализ моих эмоций' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.getByText('Идет анализ эмоций', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Эмоции', exact: true }).click();
  const panel = page.getByRole('tabpanel');
  const ts = new Date().toISOString();
  socket!.send(
    JSON.stringify({
      type: 'emotion.update',
      meeting_id: meetingId,
      items: [
        {
          participant_id: participantId,
          state: 'analyzing',
          ts,
          dominant: 'happy',
          confidence: 0.7,
          p,
        },
      ],
    }),
  );
  await expect(panel).toContainText('Радость');
  await page.getByLabel('Название отметки').fill('Проверенный момент');
  await page.getByRole('button', { name: 'Отметить момент' }).click();
  await expect(panel).toContainText('Отметка сохранена в отчёте');
  const previous = connections;
  await socket!.close({ code: 1012 });
  await expect.poll(() => connections).toBeGreaterThan(previous);
  await expect.poll(() => since).toBe(ts);
  await page.getByRole('button', { name: 'Анализ моих эмоций' }).click();
  await expect(page.getByRole('button', { name: 'Анализ моих эмоций' })).toHaveAttribute(
    'aria-pressed',
    'false',
  );
  await expect(panel).not.toContainText('Радость');
  await page.getByRole('button', { name: 'Анализ моих эмоций' }).click();
  await expect(page.getByRole('button', { name: 'Анализ моих эмоций' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await page.getByRole('button', { name: 'Анализ моих эмоций' }).click();
  await expect(page.getByRole('button', { name: 'Анализ моих эмоций' })).toHaveAttribute(
    'aria-pressed',
    'false',
  );
  expect(decisions).toEqual(['granted', 'revoked', 'granted', 'revoked']);
  socket!.send(
    JSON.stringify({ type: 'analysis.status', meeting_id: meetingId, state: 'unavailable' }),
  );
  await expect(panel).toContainText('Анализ недоступен');
  await expect(page.getByText('Идет анализ эмоций', { exact: true })).toHaveCount(0);
  await expect(page.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
  await page.getByRole('button', { name: 'Завершить встречу' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Завершить встречу' }).click();
  await expect(page).toHaveURL(new RegExp(`/meetings/${meetingId}$`));
  await expect(page.getByText('Отчёт готовится…')).toBeVisible();
  reportReady = true;
  await expect(page.getByRole('heading', { name: 'Отчет по эмоциям' })).toBeVisible({
    timeout: 10000,
  });
  await expect(page.getByText('Проверенный момент')).toBeVisible();
  await expect(page.getByRole('img', { name: /График вероятностей/ })).toBeVisible();
  expect(reportRequests).toBeGreaterThanOrEqual(2);
  await context.close();
});
