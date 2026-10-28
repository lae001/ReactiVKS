import { expect, test } from '@playwright/test';

// Лобби в Chromium с фейковыми устройствами (см. playwright.lobby.config.ts).
// Слой API – mock, поэтому ссылка demoactive работает без бэкенда.

test.beforeEach(async ({ page }) => {
  // гость не вошел в систему: AuthProvider получит 401 и пустит на публичную страницу
  await page.route('**/api/v1/auth/refresh', (route) =>
    route.fulfill({
      status: 401,
      contentType: 'application/problem+json',
      body: JSON.stringify({ code: 'unauthorized', message: 'no session' }),
    }),
  );
});

test('лобби: устройства, выбор запоминается, звук микрофона виден, вход в комнату', async ({
  page,
}) => {
  await page.goto('/j/demoactive');
  await expect(
    page.getByRole('heading', { level: 1, name: 'Еженедельная планерка команды' }),
  ).toBeVisible();

  // фейковая камера и микрофон дали доступ, списки заполнены
  const camera = page.getByRole('combobox', { name: 'Камера' });
  const mic = page.getByRole('combobox', { name: 'Микрофон' });
  await expect(camera).toBeEnabled();
  await expect(camera.locator('option')).not.toHaveCount(0);
  await expect(mic.locator('option')).not.toHaveCount(0);
  await expect(page.getByRole('alert')).toHaveCount(0);

  // индикатор уровня: фейковый микрофон Chromium периодически «пищит»
  const meter = page.getByRole('meter', { name: 'Уровень микрофона' });
  await expect
    .poll(async () => Number(await meter.getAttribute('aria-valuenow')), { timeout: 10_000 })
    .toBeGreaterThan(0);

  // выбор микрофона запоминается и подставляется после перезагрузки
  const options = await mic.locator('option').all();
  const last = options[options.length - 1];
  const chosen = (await last?.getAttribute('value')) ?? '';
  await mic.selectOption(chosen);
  const saved = await page.evaluate(() => localStorage.getItem('vks_device_prefs'));
  expect(JSON.parse(saved ?? '{}')).toMatchObject({ micId: chosen });
  await page.reload();
  await expect(mic).toHaveValue(chosen);

  // вход: имя, явное согласие, комната
  await page.getByLabel('Как вас представить').fill('Анна Тестова');
  await page.getByRole('radio', { name: /Участвую без анализа/ }).check();
  await page.getByRole('button', { name: 'Войти во встречу' }).click();
  await expect(page).toHaveURL(/\/room\/m-active$/);
  const token = await page.evaluate(() => sessionStorage.getItem('vks_participant_token'));
  expect(token).toMatch(/^pt_/);
});
