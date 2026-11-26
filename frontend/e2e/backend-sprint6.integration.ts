import { expect, test } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import { TRACK_PEER_CONNECTIONS, measureRemoteVideo } from './media-helpers';

// Настоящий полный стенд с видеозаписью лица; REST и WebSocket не подменяются.
test('backend S6: UI → ML → панель → отчёт и экспорт', async ({ browser, request }) => {
  test.skip(!process.env.E2E_VIDEO, 'Нужно тестовое видео лица');
  const email = `s6-${Date.now()}@example.ru`,
    password = 'Sprint6-check-2026';
  expect(
    (
      await request.post('/api/v1/auth/register', {
        data: { email, password, display_name: 'Организатор S6' },
      })
    ).status(),
  ).toBe(201);
  const context = await browser.newContext({ permissions: ['camera', 'microphone'] });
  const guestContext = await browser.newContext({ permissions: ['camera', 'microphone'] });
  const org = await context.newPage(),
    guest = await guestContext.newPage();
  await org.addInitScript(TRACK_PEER_CONNECTIONS);
  await guest.addInitScript(TRACK_PEER_CONNECTIONS);
  const events: { type: string; received: number; data: Record<string, unknown> }[] = [];
  org.on('websocket', (ws) => {
    if (ws.url().endsWith('/ws'))
      ws.on('framereceived', ({ payload }) => {
        const data = JSON.parse(String(payload));
        events.push({ type: data.type, received: Date.now(), data });
      });
  });
  let meetingId = '',
    access = '';
  try {
    await org.goto('/login');
    await org.getByLabel('Электронная почта').fill(email);
    await org.getByLabel('Пароль').fill(password);
    const login = org.waitForResponse((r) => r.url().endsWith('/auth/login') && r.status() === 200);
    await org.getByRole('button', { name: 'Войти', exact: true }).click();
    access = (await (await login).json()).access_token;
    await expect(org).toHaveURL(/\/meetings$/);
    await org.getByRole('link', { name: /Запланировать/ }).click();
    await org.getByLabel('Название', { exact: true }).fill('Сквозная проверка backend S6');
    await org.getByRole('checkbox', { name: /Анализировать эмоции/ }).check();
    const created = org.waitForResponse(
      (r) => new URL(r.url()).pathname === '/api/v1/meetings' && r.status() === 201,
    );
    await org.getByRole('button', { name: 'Создать и получить ссылку' }).click();
    const meeting = await (await created).json();
    meetingId = meeting.id;
    await org.getByRole('link', { name: 'Открыть карточку' }).click();
    await org.getByRole('button', { name: 'Начать встречу' }).click();
    await expect(org.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
    await guest.goto(`/j/${meeting.invite_code}`);
    await guest.getByLabel('Как вас представить').fill('Гость S6');
    await guest.getByRole('radio', { name: /Участвую без анализа/ }).check();
    await guest.getByRole('button', { name: 'Войти во встречу' }).click();
    await expect(guest.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
    await org.getByRole('button', { name: 'Анализ моих эмоций' }).click();
    await org.getByRole('button', { name: 'Эмоции', exact: true }).click();
    await expect
      .poll(() => events.filter((e) => e.type === 'emotion.update').length, { timeout: 60_000 })
      .toBeGreaterThan(5);
    await expect(org.getByRole('tabpanel')).toContainText('Анализ идёт');
    if (process.env.E2E_AGENT_LOG) {
      const records = (await readFile(process.env.E2E_AGENT_LOG, 'utf8'))
        .trim()
        .split('\n')
        .flatMap((line) => {
          try {
            return [JSON.parse(line)];
          } catch {
            return [];
          }
        });
      const job = records.findLast(
        (record) => record.room === meetingId && record.message.startsWith('Агент в комнате'),
      );
      expect(job?.pid).toBeGreaterThan(1);
      process.kill(job.pid, 'SIGKILL');
      await expect(org.getByRole('tabpanel')).toContainText('Анализ недоступен', {
        timeout: 20_000,
      });
      const people = await (
        await request.get(`/api/v1/meetings/${meetingId}/participants`, {
          headers: { Authorization: `Bearer ${access}` },
        })
      ).json();
      const owner = people.items.find((person: { role: string }) => person.role === 'organizer');
      const media = await measureRemoteVideo(guest, `p_${owner.id}`);
      await writeFile(
        '/tmp/reactivks-s6/ml-failure.json',
        JSON.stringify({ meetingId, media, unavailable: true }),
      );
    }
    await org.getByLabel('Название отметки').fill('Проверка реального ML');
    await org.getByRole('button', { name: 'Отметить момент' }).click();
    await expect(org.getByRole('tabpanel')).toContainText('Отметка сохранена');
    const revoke = org.waitForResponse(
      (r) => r.url().includes('/participants/me/consent') && r.request().method() === 'PUT',
    );
    await org.getByRole('button', { name: 'Анализ моих эмоций' }).click();
    expect([200, 202]).toContain((await revoke).status());
    await expect
      .poll(() =>
        events.some(
          (e) => e.type === 'participant.status' && JSON.stringify(e.data).includes('no_consent'),
        ),
      )
      .toBe(true);
    await expect(guest.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
    await org.getByRole('button', { name: 'Завершить встречу', exact: true }).click();
    await org
      .getByRole('alertdialog')
      .getByRole('button', { name: 'Завершить встречу', exact: true })
      .click();
    const headers = { Authorization: `Bearer ${access}` };
    await expect
      .poll(
        async () =>
          (await (await request.get(`/api/v1/reports/${meetingId}`, { headers })).json()).status,
        { timeout: 80_000 },
      )
      .toBe('ready');
    await org.reload();
    await expect(org.getByText('Проверка реального ML', { exact: true })).toBeVisible();
    for (const format of ['CSV', 'PDF']) {
      const download = org.waitForEvent('download');
      await org.getByText(`Скачать ${format}`, { exact: true }).click();
      await (await download).saveAs(`/tmp/reactivks-s6/report.${format.toLowerCase()}`);
    }
    const report = await (await request.get(`/api/v1/reports/${meetingId}`, { headers })).json();
    expect(
      report.summary.participants.some((p: { analyzed_seconds: number }) => p.analyzed_seconds > 0),
    ).toBe(true);
    await writeFile(
      '/tmp/reactivks-s6/evidence.json',
      JSON.stringify({ meetingId, report, events }, null, 2),
    );
    await org.screenshot({ path: '/tmp/reactivks-s6/report-ui.png', fullPage: true });
  } finally {
    if (meetingId && access)
      await request.post(`/api/v1/meetings/${meetingId}/end`, {
        headers: { Authorization: `Bearer ${access}` },
      });
    await context.close();
    await guestContext.close();
  }
});

test('backend S6: административные встречи и состояние через UI', async ({ page }) => {
  test.skip(
    !process.env.E2E_ADMIN_EMAIL || !process.env.E2E_ADMIN_PASSWORD,
    'Нужна тестовая admin-сессия',
  );
  await page.goto('/login');
  await page.getByLabel('Электронная почта').fill(process.env.E2E_ADMIN_EMAIL!);
  await page.getByLabel('Пароль').fill(process.env.E2E_ADMIN_PASSWORD!);
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  await expect(page).toHaveURL(/\/meetings$/);
  const meetings = page.waitForResponse(
    (r) => new URL(r.url()).pathname === '/api/v1/admin/meetings' && r.status() === 200,
  );
  const health = page.waitForResponse(
    (r) => new URL(r.url()).pathname === '/api/v1/admin/health' && r.status() === 200,
  );
  await page.goto('/admin');
  expect((await (await meetings).json()).items).toBeInstanceOf(Array);
  const components = (await (await health).json()).components;
  for (const name of [
    'auth-service',
    'meeting-service',
    'realtime-service',
    'analytics-service',
    'kafka',
    'postgres',
    'redis',
  ])
    expect(components[name].status).toBe('ok');
  await expect(page.getByRole('heading', { name: 'Встречи системы' })).toBeVisible();
  await page.screenshot({ path: '/tmp/reactivks-s6/admin-ui.png', fullPage: true });
});
