import { expect, test } from '@playwright/test';

// Одноразовый пользователь на каждый запуск: ничего чужого не трогаем.
const unique = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
const email = `test+${unique}@example.ru`;
const password = 'Passw0rd-e2e1';

test('регистрация → вход → перезагрузка (refresh) → выход', async ({ page, context }) => {
  // 1. Регистрация: после нее выполняется автоматический вход
  await page.goto('/register');
  await page.getByLabel('Имя').fill('Тест Тестов');
  await page.getByLabel('Электронная почта').fill(email);
  await page.getByLabel('Пароль').fill(password);
  await page.getByRole('button', { name: 'Создать аккаунт' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Встречи' })).toBeVisible();
  await expect(page).toHaveURL(/\/meetings$/);
  await expect(page.getByText('Тест Тестов')).toBeVisible();

  // Cookie refresh-токена принята браузером на http://localhost и недоступна скриптам
  const cookie = (await context.cookies()).find((c) => c.name === 'vks_refresh');
  expect(cookie, 'cookie vks_refresh не сохранилась').toBeDefined();
  expect(cookie).toMatchObject({ httpOnly: true, secure: true, sameSite: 'Strict' });
  expect(cookie?.path).toBe('/api/v1/auth');

  // Токены не лежат в хранилищах браузера
  const storage = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
  expect(storage).not.toMatch(/eyJ/);

  // 2. Обновление страницы: сессия восстанавливается через POST /auth/refresh
  const refreshed = page.waitForResponse(
    (r) => r.url().endsWith('/api/v1/auth/refresh') && r.request().method() === 'POST',
  );
  await page.reload();
  expect((await refreshed).status()).toBe(200);
  await expect(page.getByRole('heading', { level: 1, name: 'Встречи' })).toBeVisible();
  await expect(page).toHaveURL(/\/meetings$/);

  // 3. Защищенная страница после перезагрузки тоже открывается
  await page.goto('/settings');
  await expect(page.getByLabel('Имя')).toHaveValue('Тест Тестов');

  // 4. Выход: POST /auth/logout, переход на /login, cookie очищена
  const loggedOut = page.waitForResponse((r) => r.url().endsWith('/api/v1/auth/logout'));
  await page.getByRole('button', { name: 'Выйти' }).click();
  expect((await loggedOut).status()).toBe(204);
  await expect(page.getByRole('heading', { level: 1, name: 'Вход' })).toBeVisible();
  expect((await context.cookies()).find((c) => c.name === 'vks_refresh')).toBeUndefined();

  // 5. После выхода защищенные страницы закрыты
  await page.goto('/meetings');
  await expect(page.getByRole('heading', { level: 1, name: 'Вход' })).toBeVisible();

  // 6. Повторный вход тем же паролем и неверный пароль
  await page.getByLabel('Электронная почта').fill(email);
  await page.getByLabel('Пароль').fill('Wrong-pass1');
  await page.getByRole('button', { name: 'Войти' }).click();
  await expect(page.getByRole('alert')).toContainText('Неверная почта или пароль');
  await page.getByLabel('Пароль').fill(password);
  await page.getByRole('button', { name: 'Войти' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Встречи' })).toBeVisible();
});

test('повторная регистрация той же почты – email_taken у поля', async ({ page }) => {
  await page.goto('/register');
  await page.getByLabel('Имя').fill('Дубль');
  await page.getByLabel('Электронная почта').fill(email);
  await page.getByLabel('Пароль').fill(password);
  await page.getByRole('button', { name: 'Создать аккаунт' }).click();
  await expect(page.getByText(/Эта почта уже зарегистрирована/)).toBeVisible();
});
