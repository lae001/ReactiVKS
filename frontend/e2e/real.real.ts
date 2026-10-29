import { expect, test, type BrowserContext, type Page } from '@playwright/test';

import { expectRemoteAudio, expectRemoteVideo, TRACK_PEER_CONNECTIONS } from './media-helpers';

// Те же шаги, что в room.room.ts, но против НАСТОЯЩИХ auth-service (8001) и meeting-service (8002) и LiveKit
// с вебхуками: никакой подмены /api/v1/auth, организатор входит через форму /login.
// Учетные данные тестового организатора передаются переменными окружения и в репозиторий не попадают:
//   E2E_REAL_EMAIL, E2E_REAL_PASSWORD (пользователь должен существовать: POST /api/v1/auth/register).
// Запуск (сервисы и LiveKit подняты вручную): pnpm test:e2e:real

const EMAIL = process.env.E2E_REAL_EMAIL ?? '';
const PASSWORD = process.env.E2E_REAL_PASSWORD ?? '';
const ORGANIZER_NAME = process.env.E2E_REAL_NAME ?? 'Тест Организатор';

test.skip(!EMAIL || !PASSWORD, 'нужны E2E_REAL_EMAIL и E2E_REAL_PASSWORD');

/** Вход организатора через форму: настоящий POST /auth/login, refresh-cookie ставит сервер. */
async function signIn(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Электронная почта').fill(EMAIL);
  await page.getByLabel('Пароль').fill(PASSWORD);
  await page.getByRole('button', { name: 'Войти' }).click();
  await expect(page).toHaveURL(/\/meetings$/);
}

/** Access-токен для проверочных REST-запросов теста (отдельная сессия, SPA он не нужен). */
async function apiToken(page: Page): Promise<string> {
  const response = await page.request.post('/api/v1/auth/login', {
    data: { email: EMAIL, password: PASSWORD },
  });
  expect(response.status()).toBe(200);
  return ((await response.json()) as { access_token: string }).access_token;
}

async function newPage(context: BrowserContext) {
  const page = await context.newPage();
  await page.addInitScript(TRACK_PEER_CONNECTIONS);
  return page;
}

test('настоящий бэкенд: организатор создает и начинает встречу, гость входит по /j/<код>', async ({
  browser,
}) => {
  const options = { permissions: ['camera', 'microphone'], locale: 'ru-RU' };
  const orgContext = await browser.newContext(options);
  const guestContext = await browser.newContext(options);
  const org = await newPage(orgContext);
  const guest = await newPage(guestContext);

  // запросы meeting-service, которые дошли до dev-api через прокси Vite (auth-service не запущен)
  const served: string[] = [];
  org.on('response', (r) => {
    const url = new URL(r.url());
    if (url.pathname.startsWith('/api/v1/') && !url.pathname.startsWith('/api/v1/auth')) {
      if (r.status() < 400 && r.headers()['x-request-id']) served.push(url.pathname);
    }
  });

  // 1. вход организатора через форму и список встреч из meeting-service
  await signIn(org);
  const ACCESS_TOKEN = await apiToken(org);
  await expect(org.getByRole('heading', { level: 1, name: 'Встречи' })).toBeVisible();
  await expect(org.getByRole('region', { name: 'Ближайшие' })).toBeVisible();
  expect(served).toContain('/api/v1/meetings');

  // 2. создание встречи: настройки по умолчанию из GET /settings
  await org.goto('/meetings/new');
  await org.getByLabel('Название').fill('E2E: настоящий бэкенд');
  await org.getByRole('button', { name: 'Создать и получить ссылку' }).click();
  await expect(org.getByText('Встреча создана')).toBeVisible();
  const inviteUrl = (await org.locator('p.break-all').innerText()).trim();
  const code = /\/j\/([a-z2-7]{10})$/.exec(inviteUrl)?.[1];
  expect(code, `ссылка-приглашение: ${inviteUrl}`).toBeTruthy();
  expect(served).toContain('/api/v1/settings');

  // 3. пока организатор не вошел, гость видит лобби, но войти не может (meeting_not_started)
  await guest.goto(`/j/${code}`);
  await expect(
    guest.getByRole('heading', { level: 1, name: 'E2E: настоящий бэкенд' }),
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
    expect.arrayContaining([ORGANIZER_NAME, 'Анна Гостева']),
  );

  // 7. оба в комнате LiveKit по токенам dev-api: соединение установлено, две плитки у каждого
  for (const page of [org, guest]) {
    await expect(page.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
    await expect(page.getByTestId('lk-gallery')).toHaveAttribute('data-tiles', '2');
  }

  // 8. видят и слышат друг друга (кадры идут, входящие байты аудио растут)
  await expectRemoteVideo(org, 'Анна Гостева');
  await expectRemoteVideo(guest, ORGANIZER_NAME);
  await expectRemoteAudio(org, 'Анна Гостева');
  await expectRemoteAudio(guest, ORGANIZER_NAME);

  // 9. состав и роли берутся из LiveKit (имя в токене, атрибуты vks.*), панель управления по-русски
  const controls = guest.getByRole('contentinfo', { name: 'Управление встречей' });
  for (const label of ['Микрофон', 'Камера', 'Устройства', 'Участники', 'Выйти']) {
    await expect(controls.getByRole('button', { name: label })).toBeVisible();
  }
  await guest.getByRole('button', { name: 'Участники' }).click();
  const panel = guest.getByRole('tabpanel');
  await expect(panel).toContainText('Анна Гостева');
  await expect(panel).toContainText(ORGANIZER_NAME);
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

  // 11. согласие: PUT /participants/me/consent в meeting-service ЕЩЕ НЕ РЕАЛИЗОВАН (EMO-84). Проверяем, что
  // интерфейс честно говорит об этом и не меняет состояние ни у гостя, ни у организатора.
  await org.getByRole('tab', { name: /Участники/ }).click();
  const guestRow = org.getByRole('listitem').filter({ hasText: 'Анна Гостева' });
  const consentToggle = (page: Page) => page.getByRole('button', { name: 'Анализ моих эмоций' });
  const unsupported = 'Пока недоступно: сервер ещё не поддерживает эту функцию.';
  await expect(guestRow).toContainText('Анализ разрешен');
  await consentToggle(guest).click();
  await expect(guest.getByRole('alert')).toContainText(unsupported);
  await expect(consentToggle(guest)).toHaveAttribute('aria-pressed', 'true');
  await expect(guestRow).toContainText('Анализ разрешен');
  await consentToggle(org).click();
  await expect(org.getByRole('alert')).toContainText(unsupported);
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

test('настоящий бэкенд: «Начать сейчас» – один клик от списка до комнаты', async ({ browser }) => {
  const context = await browser.newContext({
    permissions: ['camera', 'microphone'],
    locale: 'ru-RU',
  });
  const page = await newPage(context);
  await signIn(page);
  const token = await apiToken(page);

  // действие 1: «Начать сейчас» создает встречу и входит в нее (POST /meetings + POST /meetings/{id}/join)
  await page.getByRole('button', { name: /Начать сейчас/ }).click();
  await expect(page).toHaveURL(/\/room\/[0-9a-f-]{36}$/);
  const meetingId = /\/room\/([0-9a-f-]{36})$/.exec(page.url())?.[1];
  await expect(page.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
  await expect(page.getByTestId('lk-gallery')).toHaveAttribute('data-tiles', '1');

  const card = await page.request.get(`/api/v1/meetings/${meetingId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(await card.json()).toMatchObject({ status: 'active' });

  // завершение: подтверждение, переход в карточку
  await page.getByRole('button', { name: 'Завершить встречу' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Завершить встречу' }).click();
  await expect(page).toHaveURL(new RegExp(`/meetings/${meetingId}$`));
  const ended = await page.request.get(`/api/v1/meetings/${meetingId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(await ended.json()).toMatchObject({ status: 'ended' });
  await context.close();
});

test('настоящий бэкенд: смена пароля завершает сессию, старый пароль больше не подходит', async ({
  browser,
}) => {
  // отдельный пользователь: смена пароля отзывает все его сессии
  const email = `pw.${Date.now()}@example.ru`;
  const oldPassword = `${PASSWORD}`;
  const newPassword = `${PASSWORD}-new`;
  const context = await browser.newContext({ locale: 'ru-RU' });
  const page = await context.newPage();
  const registered = await page.request.post('/api/v1/auth/register', {
    data: { email, password: oldPassword, display_name: 'Смена Пароля' },
  });
  expect(registered.status()).toBe(201);

  const login = async (password: string) => {
    await page.goto('/login');
    await page.getByLabel('Электронная почта').fill(email);
    await page.getByLabel('Пароль').fill(password);
    await page.getByRole('button', { name: 'Войти' }).click();
  };

  await login(oldPassword);
  await expect(page).toHaveURL(/\/meetings$/);
  await page.goto('/settings');
  // неверный текущий пароль: ошибка у поля, сессия сохраняется
  await page.getByLabel('Текущий пароль').fill('Wrong-Password-9');
  await page.getByLabel('Новый пароль').fill(newPassword);
  await page.getByRole('button', { name: 'Сменить пароль' }).click();
  await expect(page.getByText(/Текущий пароль неверный/)).toBeVisible();
  await expect(page).toHaveURL(/\/settings$/);

  // верный: переход на /login с сообщением
  await page.getByLabel('Текущий пароль').fill(oldPassword);
  await page.getByRole('button', { name: 'Сменить пароль' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText('Пароль изменён, войдите снова.')).toBeVisible();

  // сессия действительно завершена: после перезагрузки это гость
  await page.goto('/meetings');
  await expect(page).toHaveURL(/\/login/);

  // старый пароль отклонен, новый принят
  await login(oldPassword);
  await expect(page.getByRole('alert')).toContainText('Неверная почта или пароль');
  await login(newPassword);
  await expect(page).toHaveURL(/\/meetings$/);
  await context.close();
});
