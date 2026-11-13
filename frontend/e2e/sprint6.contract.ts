import { expect, test, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';

// Все ответы API в этом файле — контрактные фикстуры, включая авторизацию.
const meeting = {
  id: 'contract-ended',
  title: 'Проверка истории',
  status: 'ended',
  analysis_enabled: true,
  analysis_fps: 3,
  invite_code: 'fixture000',
  invite_url: '',
  participants_count: 1,
  created_at: '2026-11-12T10:00:00Z',
  scheduled_at: null,
  started_at: '2026-11-12T10:00:00Z',
  ended_at: '2026-11-12T10:01:00Z',
};
const labels = ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral'];
const distribution = Object.fromEntries(labels.map((label) => [label, label === 'happy' ? 1 : 0]));
const csv = Buffer.from(
  '\ufeffts,participant_id,display_name,samples,face_samples,p_angry,p_disgust,p_fear,p_happy,p_sad,p_surprise,p_neutral\r\n2026-11-12T10:00:00Z,contract-person,Участник,3,3,0,0,0,1,0,0,0\r\n',
  'utf8',
);

/** Небольшой корректный PDF для проверки доставки байтов, не генератор экспорта приложения. */
function fixturePdf() {
  const stream = 'BT /F1 16 Tf 50 750 Td (Contract fixture - test emotion data) Tj ET';
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
  ];
  let document = '%PDF-1.4\n';
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets.push(Buffer.byteLength(document));
    document += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = Buffer.byteLength(document);
  document += `xref\n0 6\n0000000000 65535 f \n${offsets
    .slice(1)
    .map((n) => `${String(n).padStart(10, '0')} 00000 n \n`)
    .join('')}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(document);
}
const pdf = fixturePdf();

async function fixture(page: Page, role = 'organizer') {
  const user = {
    id: 'contract-owner',
    email: 'fixture@example.invalid',
    display_name: 'Тестовый пользователь',
    role,
  };
  let settings = { analysis_enabled_default: true, analysis_fps_default: 3 };
  const state = {
    ready: false,
    invalidSettings: false,
    queries: [] as URL[],
    created: {} as Record<string, unknown>,
    status: 'active',
    adminRequests: 0,
  };
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body });
    if (path === '/api/v1/auth/refresh')
      return json({ access_token: 'contract-access', token_type: 'Bearer', expires_in: 900, user });
    if (path === '/api/v1/users/me') return json(user);
    if (path === '/api/v1/settings') {
      if (request.method() === 'PUT') {
        if (state.invalidSettings) return json({ status: 422, code: 'validation_error' }, 422);
        settings = request.postDataJSON();
      }
      return json(settings);
    }
    if (path === '/api/v1/meetings') {
      if (request.method() === 'POST') {
        state.created = request.postDataJSON();
        return json(
          { ...meeting, ...state.created, id: 'contract-created', status: 'scheduled' },
          201,
        );
      }
      state.queries.push(url);
      const past = url.searchParams.get('status')?.includes('ended');
      const found =
        !url.searchParams.get('q') || meeting.title.includes(url.searchParams.get('q')!);
      return json({ items: past && found ? [meeting] : [], next_cursor: null });
    }
    if (path === `/api/v1/meetings/${meeting.id}`) return json(meeting);
    if (path.endsWith('/export.csv') || path.endsWith('/export.pdf')) {
      expect(request.headers()['authorization']).toBe('Bearer contract-access');
      const isCsv = path.endsWith('.csv');
      return route.fulfill({
        body: isCsv ? csv : pdf,
        headers: {
          'Content-Type': isCsv ? 'text/csv; charset=utf-8' : 'application/pdf',
          'Content-Disposition': `attachment; filename="meeting-report.${isCsv ? 'csv' : 'pdf'}"`,
        },
      });
    }
    if (path.endsWith('/series'))
      return json({
        resolution: '5s',
        labels,
        series: [
          {
            participant_id: 'contract-person',
            points: [{ ts: meeting.started_at, p: [0, 0, 0, 1, 0, 0, 0], face_ratio: 1 }],
          },
        ],
      });
    if (path === `/api/v1/reports/${meeting.id}`)
      return json({
        meeting_id: meeting.id,
        status: state.ready ? 'ready' : 'pending',
        model_version: 'contract',
        meeting: {
          title: meeting.title,
          started_at: meeting.started_at,
          ended_at: meeting.ended_at,
          duration_s: 60,
        },
        summary: {
          overall: { distribution, face_detected_ratio: 1, negative_share: 0 },
          participants: [
            {
              participant_id: 'contract-person',
              display_name: 'Участник',
              consent: 'granted',
              distribution,
              dominant: 'happy',
              face_detected_ratio: 1,
              analyzed_seconds: 60,
            },
          ],
        },
        markers: [],
        disclaimer: 'Контрактные тестовые данные эмоций',
      });
    if (path.startsWith('/api/v1/admin')) {
      state.adminRequests++;
      if (role !== 'admin') return json({ status: 403, code: 'forbidden' }, 403);
      if (path.endsWith('/users/contract-user')) {
        state.status = request.postDataJSON().status;
        return json({
          id: 'contract-user',
          display_name: 'Участник',
          email: 'user@example.invalid',
          role: 'organizer',
          status: state.status,
          created_at: meeting.created_at,
          last_login_at: null,
        });
      }
      if (path.endsWith('/users'))
        return json({
          items: [
            {
              id: 'contract-user',
              display_name: 'Участник',
              email: 'user@example.invalid',
              role: 'organizer',
              status: state.status,
              created_at: meeting.created_at,
              last_login_at: null,
            },
          ],
          next_cursor: null,
        });
      return json({ status: 404, code: 'not_found' }, 404);
    }
    throw new Error(`Нет контрактного обработчика: ${request.method()} ${path}`);
  });
  return state;
}

test('UC-5: история, фильтры, отчёт, скачанные CSV и PDF', async ({ page, browser }, info) => {
  const state = await fixture(page);
  await info.attach('browser', {
    body: `${info.project.name}: ${browser.version()}; контрактные API`,
    contentType: 'text/plain',
  });
  await page.goto('/meetings');
  await page.getByRole('searchbox', { name: 'Поиск по названию' }).fill('Проверка');
  await page.getByLabel('С даты (UTC)').fill('2026-11-12');
  await page.getByLabel('По дату (UTC)').fill('2026-11-12');
  await page.getByLabel('Статус — Прошедшие').selectOption('ended');
  await expect
    .poll(() =>
      state.queries.some(
        (url) =>
          url.searchParams.get('q') === 'Проверка' &&
          url.searchParams.get('from') === '2026-11-12' &&
          url.searchParams.get('status') === 'ended',
      ),
    )
    .toBe(true);
  await page
    .getByRole('region', { name: 'Прошедшие' })
    .getByRole('link', { name: 'Отчет', exact: true })
    .click();
  await expect(page.getByText('Отчёт готовится…')).toBeVisible();
  await expect(page.getByText('Скачать PDF')).toBeDisabled();
  await page.screenshot({ path: info.outputPath('report-pending.png') });
  const csvDownload = page.waitForEvent('download');
  await page.getByText('Скачать CSV').click();
  const csvFile = await csvDownload;
  expect(csvFile.suggestedFilename()).toBe('meeting-report.csv');
  const csvPath = info.outputPath('meeting-report.csv');
  await csvFile.saveAs(csvPath);
  const actualCsv = await readFile(csvPath);
  expect(actualCsv).toEqual(csv);
  expect(actualCsv.subarray(0, 3)).toEqual(Buffer.from([239, 187, 191]));
  expect(actualCsv.toString('utf8')).toContain('Участник');
  state.ready = true;
  await expect(page.getByRole('heading', { name: 'Отчет по эмоциям' })).toBeVisible({
    timeout: 10_000,
  });
  await page.screenshot({ path: info.outputPath('report-ready.png') });
  const pdfDownload = page.waitForEvent('download');
  await page.getByText('Скачать PDF').click();
  const pdfFile = await pdfDownload;
  expect(pdfFile.suggestedFilename()).toBe('meeting-report.pdf');
  const pdfPath = info.outputPath('meeting-report.pdf');
  await pdfFile.saveAs(pdfPath);
  expect(await readFile(pdfPath)).toEqual(pdf);
});

test('настройки переживают reload, используются новой встречей, отказ сервера объясняется', async ({
  page,
}) => {
  const state = await fixture(page);
  await page.goto('/settings');
  await page.getByLabel('Частота анализа по умолчанию').fill('5');
  await page.getByLabel('Включать анализ в новых встречах').uncheck();
  await page.getByText('Сохранить настройки встреч').click();
  await expect(page.getByText('Настройки встреч сохранены.')).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Частота анализа по умолчанию')).toHaveValue('5');
  await page.goto('/meetings/new');
  await expect(page.getByRole('checkbox', { name: /Анализировать эмоции/ })).not.toBeChecked();
  await page.getByLabel('Название', { exact: true }).fill('Новая встреча');
  await page.getByRole('button', { name: 'Создать и получить ссылку' }).click();
  await expect(page.getByText('Встреча создана')).toBeVisible();
  expect(state.created).toMatchObject({ analysis_enabled: false, analysis_fps: 5 });
  await page.goto('/settings');
  state.invalidSettings = true;
  await page.getByLabel('Частота анализа по умолчанию').fill('4');
  await page.getByText('Сохранить настройки встреч').click();
  await expect(page.getByText(/Сервер отклонил настройки/)).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Частота анализа по умолчанию')).toHaveValue('5');
  await page.goto('/admin');
  await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible();
  expect(state.adminRequests).toBe(0);
});

test('администратор: подтверждение блокировки и разблокировки, реальные ошибки недоступных разделов', async ({
  page,
}) => {
  const state = await fixture(page, 'admin');
  await page.goto('/admin');
  await page.getByRole('button', { name: 'Заблокировать: Участник' }).click();
  expect(state.status).toBe('active');
  await page
    .getByRole('alertdialog')
    .getByRole('button', { name: 'Заблокировать', exact: true })
    .click();
  await expect(page.getByText('Заблокирован', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Разблокировать: Участник' }).click();
  await page
    .getByRole('alertdialog')
    .getByRole('button', { name: 'Разблокировать', exact: true })
    .click();
  await expect(page.getByText('Активен', { exact: true })).toBeVisible();
  await expect(page.getByText(/Сервис пока не предоставляет этот раздел/)).toHaveCount(2);
});
