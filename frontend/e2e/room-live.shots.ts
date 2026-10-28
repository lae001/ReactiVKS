import { expect, test, type BrowserContext, type Page } from '@playwright/test';

import { expectRemoteVideo } from './media-helpers';

// Живые снимки комнаты (docs/frontend/mockups.md): организатор и гость в двух контекстах одного Chromium,
// настоящая комната на LiveKit, фейковая камера Chromium. Запуск: livekit-server --dev --bind 127.0.0.1,
// pnpm dev:api, затем pnpm mockups:live. Результат – docs/frontend/mockups/room-live-*.png.
// В кадре только тестовые имена: ссылок-приглашений, токенов и данных вне страницы на снимках нет.

const OUT = '../docs/frontend/mockups';

const organizer = {
  id: '0192a000-0000-7000-8000-000000000001',
  email: 'ivan@example.ru',
  display_name: 'Иван Петров',
  role: 'organizer',
};

/** Access-токен как у auth-service: JWT с claim `name`; подпись dev-api не проверяет. */
const ACCESS_TOKEN = [
  { alg: 'none' },
  { sub: organizer.id, role: organizer.role, name: organizer.display_name },
]
  .map((part) => Buffer.from(JSON.stringify(part)).toString('base64url'))
  .concat('shot')
  .join('.');

async function mockAuth(page: Page, signedIn: boolean) {
  await page.route('**/api/v1/auth/**', (route) => {
    const url = route.request().url();
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

test('живая комната: организатор и гость, фейковая камера Chromium', async ({ browser }) => {
  const options = {
    permissions: ['camera', 'microphone'],
    locale: 'ru-RU',
    viewport: { width: 1280, height: 720 },
  };
  const orgContext = await browser.newContext(options);
  const guestContext = await browser.newContext(options);
  const org = await newPage(orgContext, true);
  const guest = await newPage(guestContext, false);
  const headers = { Authorization: `Bearer ${ACCESS_TOKEN}` };

  // встреча и вход организатора через REST (dev-api создает комнату LiveKit)
  await org.goto('/meetings');
  const created = (await (
    await org.request.post('/api/v1/meetings', {
      headers,
      data: { title: 'Еженедельная планерка команды' },
    })
  ).json()) as { id: string; invite_code: string };
  await org.goto(`/room/${created.id}`);

  // гость заходит через лобби
  await guest.goto(`/j/${created.invite_code}`);
  await guest.getByLabel('Как вас представить').fill('Анна Смирнова');
  await guest.getByRole('radio', { name: /Разрешаю анализ/ }).check();
  await guest.getByRole('button', { name: 'Войти во встречу' }).click();

  for (const page of [org, guest]) {
    await expect(page.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
    await expect(page.getByTestId('lk-gallery')).toHaveAttribute('data-tiles', '2');
  }
  await expectRemoteVideo(org, 'Анна Смирнова');
  await expectRemoteVideo(guest, 'Иван Петров');
  await org.waitForTimeout(800);
  await org.screenshot({ path: `${OUT}/room-live-1280.png` });

  // чат и список участников у организатора
  await guest.getByRole('button', { name: 'Чат' }).click();
  await guest.getByLabel('Сообщение').fill('Всем привет! Слышно хорошо.');
  await guest.getByRole('button', { name: 'Отправить' }).click();
  await org.getByRole('button', { name: 'Чат' }).click();
  await expect(org.getByRole('list').getByText('Всем привет! Слышно хорошо.')).toBeVisible();
  await org.waitForTimeout(400);
  await org.screenshot({ path: `${OUT}/room-live-chat-1280.png` });

  await orgContext.close();
  await guestContext.close();
});
