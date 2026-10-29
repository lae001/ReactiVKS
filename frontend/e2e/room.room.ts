import { expect, test, type BrowserContext, type Page } from '@playwright/test';

import { expectRemoteAudio, expectRemoteVideo, TRACK_PEER_CONNECTIONS } from './media-helpers';

// Организатор и гость в двух контекстах одного Chromium: SPA в режиме VITE_API_MODE=http ходит через
// прокси Vite в dev-api (127.0.0.1:8002), токены LiveKit выдает dev-api (livekit-server --dev).
// Запуск: livekit-server --dev --bind 127.0.0.1, pnpm dev:api, затем pnpm test:e2e:room.

const organizer = {
  id: '0192a000-0000-7000-8000-000000000001',
  email: 'ivan@example.ru',
  display_name: 'Иван Петров',
  role: 'organizer',
};

/**
 * Access-токен как у auth-service: JWT с claims `sub`, `role`, `name` (docs/architecture/05-security-privacy.md).
 * dev-api подпись не проверяет, но берет из `name` имя организатора для токена LiveKit.
 */
const ACCESS_TOKEN = [
  { alg: 'none' },
  { sub: organizer.id, role: organizer.role, name: organizer.display_name },
]
  .map((part) => Buffer.from(JSON.stringify(part)).toString('base64url'))
  .concat('e2e')
  .join('.');

/** auth-service не нужен: вход организатора подменяется, у гостя сессии нет. */
async function mockAuth(page: Page, signedIn: boolean) {
  await page.route('**/api/v1/auth/**', (route) => {
    const url = route.request().url();
    if (url.endsWith('/auth/config')) {
      return route.fulfill({
        json: { registration_enabled: false, password_reset_enabled: false },
      });
    }
    if (url.endsWith('/auth/refresh') && signedIn) {
      return route.fulfill({
        json: {
          access_token: ACCESS_TOKEN,
          token_type: 'Bearer',
          expires_in: 900,
          user: organizer,
        },
      });
    }
    return route.fulfill({
      status: 401,
      contentType: 'application/problem+json',
      json: { code: 'unauthorized', title: 'unauthorized', status: 401 },
    });
  });
}

async function newPage(context: BrowserContext, signedIn: boolean) {
  const page = await context.newPage();
  await page.addInitScript(TRACK_PEER_CONNECTIONS);
  await mockAuth(page, signedIn);
  return page;
}

test('режим http: организатор создает и начинает встречу, гость входит по /j/<код>', async ({
  browser,
}) => {
  const options = { permissions: ['camera', 'microphone'], locale: 'ru-RU' };
  const orgContext = await browser.newContext(options);
  const guestContext = await browser.newContext(options);
  const org = await newPage(orgContext, true);
  const guest = await newPage(guestContext, false);

  // запросы meeting-service, которые дошли до dev-api через прокси Vite (auth-service не запущен)
  const served: string[] = [];
  org.on('response', (r) => {
    const url = new URL(r.url());
    if (url.pathname.startsWith('/api/v1/') && !url.pathname.startsWith('/api/v1/auth')) {
      if (r.status() < 400 && r.headers()['x-request-id']) served.push(url.pathname);
    }
  });

  // 1. вход организатора (сессия подменена) и список встреч из dev-api
  await org.goto('/meetings');
  await expect(org.getByRole('heading', { level: 1, name: 'Встречи' })).toBeVisible();
  await expect(org.getByRole('region', { name: 'Ближайшие' })).toBeVisible();
  expect(served).toContain('/api/v1/meetings');

  // 2. создание встречи: настройки по умолчанию из GET /settings (dev-api)
  await org.goto('/meetings/new');
  await org.getByLabel('Название').fill('E2E: встреча через dev-api');
  await org.getByRole('button', { name: 'Создать и получить ссылку' }).click();
  await expect(org.getByText('Встреча создана')).toBeVisible();
  const inviteUrl = (await org.locator('p.break-all').innerText()).trim();
  const code = /\/j\/([a-z2-7]{10})$/.exec(inviteUrl)?.[1];
  expect(code, `ссылка-приглашение: ${inviteUrl}`).toBeTruthy();
  expect(served).toContain('/api/v1/settings');

  // 3. пока организатор не вошел, гость видит лобби, но войти не может (meeting_not_started)
  await guest.goto(`/j/${code}`);
  await expect(
    guest.getByRole('heading', { level: 1, name: 'E2E: встреча через dev-api' }),
  ).toBeVisible();
  await guest.getByLabel('Как вас представить').fill('Анна Гостева');
  await guest.getByRole('radio', { name: /Разрешаю анализ/ }).check();
  await guest.getByRole('button', { name: 'Войти во встречу' }).click();
  await expect(guest.getByText('Встреча еще не началась')).toBeVisible();

  // 4. организатор начинает встречу: POST /meetings/{id}/join (dev-api создает комнату LiveKit)
  await org.getByRole('link', { name: 'Открыть карточку' }).click();
  await org.getByRole('button', { name: 'Начать встречу' }).click();
  await expect(org).toHaveURL(/\/room\/[0-9a-f-]{36}$/);
  const meetingId = /\/room\/([0-9a-f-]{36})$/.exec(org.url())?.[1];
  const card = await org.request.get(`/api/v1/meetings/${meetingId}`, {
    headers: { Authorization: `Bearer ${ACCESS_TOKEN}` },
  });
  expect(card.status()).toBe(200);
  expect(await card.json()).toMatchObject({ status: 'active' });

  // 5. гость, который ждал, входит сам (опрос раз в 5 с) и получает participant_token
  await expect(guest).toHaveURL(new RegExp(`/room/${meetingId}$`), { timeout: 20_000 });
  const token = await guest.evaluate(() => sessionStorage.getItem('vks_participant_token'));
  expect(token).toMatch(/^pt_/);

  // 6. организатор видит гостя в REST-списке участников (из dev-api)
  const participants = await org.request.get(`/api/v1/meetings/${meetingId}/participants`, {
    headers: { Authorization: `Bearer ${ACCESS_TOKEN}` },
  });
  const items = ((await participants.json()) as { items: { display_name: string; role: string }[] })
    .items;
  expect(items.map((p) => p.display_name)).toEqual(
    expect.arrayContaining(['Иван Петров', 'Анна Гостева']),
  );

  // 7. оба в комнате LiveKit по токенам dev-api: соединение установлено, две плитки у каждого
  for (const page of [org, guest]) {
    await expect(page.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
    await expect(page.getByTestId('lk-gallery')).toHaveAttribute('data-tiles', '2');
  }

  // 8. видят и слышат друг друга (кадры идут, входящие байты аудио растут)
  await expectRemoteVideo(org, 'Анна Гостева');
  await expectRemoteVideo(guest, 'Иван Петров');
  await expectRemoteAudio(org, 'Анна Гостева');
  await expectRemoteAudio(guest, 'Иван Петров');

  // 9. состав и роли берутся из LiveKit (имя в токене, атрибуты vks.*), панель управления по-русски
  const controls = guest.getByRole('contentinfo', { name: 'Управление встречей' });
  for (const label of ['Микрофон', 'Камера', 'Устройства', 'Участники', 'Выйти']) {
    await expect(controls.getByRole('button', { name: label })).toBeVisible();
  }
  await guest.getByRole('button', { name: 'Участники' }).click();
  const panel = guest.getByRole('tabpanel');
  await expect(panel).toContainText('Анна Гостева');
  await expect(panel).toContainText('Иван Петров');
  await expect(panel).toContainText('Организатор');
  await expect(guest.getByRole('tab', { name: /Участники · 2/ })).toBeVisible();

  // 10. чат на LiveKit (lk.chat): сообщения доходят в обе стороны
  await guest.getByRole('button', { name: 'Чат' }).click();
  await org.getByRole('button', { name: 'Чат' }).click();
  await guest.getByLabel('Сообщение').fill('Привет от гостя');
  await guest.getByRole('button', { name: 'Отправить' }).click();
  await expect(org.getByRole('list').getByText('Привет от гостя')).toBeVisible();
  await org.getByLabel('Сообщение').fill('Ответ организатора');
  await org.getByRole('button', { name: 'Отправить' }).click();
  await expect(guest.getByRole('list').getByText('Ответ организатора')).toBeVisible();
  await expect(guest.getByRole('list').getByText(/^Вы ·/)).toBeVisible();

  // 11. согласие: PUT /participants/me/consent обновляет атрибут vks.consent в LiveKit, организатор видит
  await org.getByRole('tab', { name: /Участники/ }).click();
  const guestRow = org.getByRole('listitem').filter({ hasText: 'Анна Гостева' });
  const consentToggle = (page: Page) => page.getByRole('button', { name: 'Анализ моих эмоций' });
  await expect(guestRow).toContainText('Анализ разрешен');
  await consentToggle(guest).click();
  await expect(consentToggle(guest)).toHaveAttribute('aria-pressed', 'false');
  await expect(guestRow).toContainText('Анализ отключен');
  await consentToggle(guest).click();
  await expect(guestRow).toContainText('Анализ разрешен');
  // у организатора то же через Bearer и ?meeting_id=
  await consentToggle(org).click();
  await expect(consentToggle(org)).toHaveAttribute('aria-pressed', 'true');
  // панель эмоций – на моке, и это сказано в интерфейсе
  await org.getByRole('button', { name: 'Эмоции' }).click();
  await expect(org.getByRole('note')).toContainText('Демонстрационные данные');

  // 12. модерация: выключить микрофон и камеру гостя (REST → LiveKit), каждое с подтверждением
  await org.getByRole('tab', { name: /Участники/ }).click();
  const confirmIn = (page: Page, label: string) =>
    page.getByRole('alertdialog').getByRole('button', { name: label });
  await org.getByRole('button', { name: 'Выключить микрофон: Анна Гостева' }).click();
  await expect(guest.getByRole('button', { name: 'Микрофон' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await confirmIn(org, 'Выключить микрофон').click();
  await expect(guest.getByRole('button', { name: 'Микрофон' })).toHaveAttribute(
    'aria-pressed',
    'false',
  );
  await org.getByRole('button', { name: 'Выключить камеру: Анна Гостева' }).click();
  await confirmIn(org, 'Выключить камеру').click();
  await expect(guest.getByRole('button', { name: 'Камера' })).toHaveAttribute(
    'aria-pressed',
    'false',
  );

  // 13. удаление: гость видит «Вас удалили из встречи», перезагрузкой вернуться нельзя
  await org.getByRole('button', { name: 'Удалить из встречи: Анна Гостева' }).click();
  await confirmIn(org, 'Удалить из встречи').click();
  await expect(guest.getByRole('heading', { name: 'Вас удалили из встречи' })).toBeVisible();
  await expect(org.getByTestId('lk-gallery')).toHaveAttribute('data-tiles', '1', {
    timeout: 20_000,
  });
  await guest.reload();
  await expect(guest.getByRole('heading', { name: 'Вас удалили из встречи' })).toBeVisible();

  // 14. по ссылке-приглашению гость входит заново как новый участник
  await guest.goto(`/j/${code}`);
  await guest.getByLabel('Как вас представить').fill('Анна Гостева');
  await guest.getByRole('radio', { name: /Разрешаю анализ/ }).check();
  await guest.getByRole('button', { name: 'Войти во встречу' }).click();
  await expect(guest.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
  await expect(org.getByTestId('lk-gallery')).toHaveAttribute('data-tiles', '2', {
    timeout: 20_000,
  });

  // 15. завершение встречи организатором: подтверждение, карточка у него, экран у гостя
  await org.getByRole('button', { name: 'Завершить встречу' }).click();
  await confirmIn(org, 'Завершить встречу').click();
  await expect(org).toHaveURL(new RegExp(`/meetings/${meetingId}$`));
  await expect(guest.getByRole('heading', { name: 'Встреча завершена' })).toBeVisible({
    timeout: 20_000,
  });
  const ended = await org.request.get(`/api/v1/meetings/${meetingId}`, {
    headers: { Authorization: `Bearer ${ACCESS_TOKEN}` },
  });
  expect(await ended.json()).toMatchObject({ status: 'ended' });

  await orgContext.close();
  await guestContext.close();
});
