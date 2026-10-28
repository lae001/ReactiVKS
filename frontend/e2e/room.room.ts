import { expect, test, type BrowserContext, type Page } from '@playwright/test';

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

  await orgContext.close();
  await guestContext.close();
});
