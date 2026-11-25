import { expect, test, type BrowserContext } from '@playwright/test';

// Проверка присутствия и предела; камеры и микрофоны девяти гостей выключены.
// Это НЕ замер ML или десяти одновременных видеопотоков.
test('настоящий стенд: 10 участников в интерфейсе, 11-й получает meeting_full', async ({
  browser,
}) => {
  test.skip(
    !process.env.E2E_REAL_EMAIL || !process.env.E2E_REAL_PASSWORD,
    'нужна тестовая учётная запись',
  );
  const contexts: BrowserContext[] = [];
  try {
    const organizer = await browser.newContext({
      permissions: ['camera', 'microphone'],
      locale: 'ru-RU',
    });
    contexts.push(organizer);
    const page = await organizer.newPage();
    await page.goto('/login');
    await page.getByLabel('Электронная почта').fill(process.env.E2E_REAL_EMAIL!);
    await page.getByLabel('Пароль').fill(process.env.E2E_REAL_PASSWORD!);
    await page.getByRole('button', { name: 'Войти', exact: true }).click();
    await expect(page).toHaveURL(/\/meetings$/);
    const login = await page.request.post('/api/v1/auth/login', {
      data: { email: process.env.E2E_REAL_EMAIL, password: process.env.E2E_REAL_PASSWORD },
    });
    const { access_token: token } = await login.json();
    await page.getByRole('button', { name: /Начать сейчас/ }).click();
    await expect(page.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
    const meetingId = page.url().split('/').at(-1)!;
    const headers = { Authorization: `Bearer ${token}` };
    const card = await (
      await page.request.get(`/api/v1/meetings/${meetingId}`, { headers })
    ).json();
    for (let i = 1; i <= 9; i++) {
      const context = await browser.newContext({
        permissions: ['camera', 'microphone'],
        locale: 'ru-RU',
      });
      contexts.push(context);
      const guest = await context.newPage();
      await guest.goto(`/j/${card.invite_code}`);
      await guest.getByLabel('Как вас представить').fill(`Гость ${i}`);
      await guest.getByRole('radio', { name: /Разрешаю анализ/ }).check();
      await guest.getByRole('button', { name: 'Выключить камеру', exact: true }).click();
      await guest.getByRole('button', { name: 'Выключить микрофон', exact: true }).click();
      await guest.getByRole('button', { name: 'Войти во встречу' }).click();
      await expect(guest.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
      await expect(page.getByTestId('lk-gallery')).toHaveAttribute('data-tiles', String(i + 1));
    }
    const tiles = page.locator('[data-participant-identity]');
    await expect(tiles).toHaveCount(10);
    for (const tile of await tiles.all()) await expect(tile).toBeVisible();
    await expect
      .poll(async () => {
        const result = await (
          await page.request.get(`/api/v1/meetings/${meetingId}/participants`, { headers })
        ).json();
        return result.items.filter((p: { online: boolean }) => p.online).length;
      })
      .toBe(10);
    const info = await (await page.request.get(`/api/v1/join/${card.invite_code}`)).json();
    const denied = await page.request.post(`/api/v1/join/${card.invite_code}`, {
      data: {
        display_name: 'Одиннадцатый',
        consent: 'denied',
        notice_version: info.consent_notice.version,
      },
    });
    expect(denied.status()).toBe(409);
    expect(await denied.json()).toMatchObject({ code: 'meeting_full' });
    await page.getByRole('button', { name: 'Завершить встречу' }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: 'Завершить встречу' }).click();
    await expect(page).toHaveURL(new RegExp(`/meetings/${meetingId}$`));
  } finally {
    for (const context of contexts.reverse()) await context.close();
  }
});
