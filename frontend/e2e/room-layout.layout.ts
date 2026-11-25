import { expect, test, type Page } from '@playwright/test';

// Комната в режиме mock (/room/m-active): страница занимает окно ровно, без прокрутки документа по горизонтали и
// по вертикали, левый край корня – 0. Запуск: pnpm test:e2e:layout.

const user = {
  id: '0192a000-0000-7000-8000-000000000001',
  email: 'ivan@example.ru',
  display_name: 'Иван Петров',
  role: 'organizer',
};

const WIDTHS = [
  { width: 360, height: 740 },
  { width: 768, height: 900 },
  { width: 960, height: 720 },
  { width: 1024, height: 700 },
  { width: 1280, height: 720 },
  { width: 1920, height: 1080 },
] as const;

async function signIn(page: Page) {
  await page.route('**/api/v1/auth/config', (r) =>
    r.fulfill({ json: { registration_enabled: false, password_reset_enabled: false } }),
  );
  await page.route('**/api/v1/auth/refresh', (r) =>
    r.fulfill({ json: { access_token: 'mock', token_type: 'Bearer', expires_in: 900, user } }),
  );
  await page.route('**/api/v1/users/me', (r) => r.fulfill({ json: user }));
}

/** Размеры документа и положение корня комнаты (первый дочерний элемент `#root`). */
async function measure(page: Page) {
  return page.evaluate(() => {
    const scrolling = document.scrollingElement!;
    const root = document.querySelector('#root > *')!.getBoundingClientRect();
    return {
      scrollWidth: scrolling.scrollWidth,
      innerWidth: window.innerWidth,
      scrollHeight: scrolling.scrollHeight,
      innerHeight: window.innerHeight,
      scrollX: window.scrollX,
      scrollY: window.scrollY,
      left: root.left,
      top: root.top,
      width: root.width,
      height: root.height,
    };
  });
}

/** Элементы с горизонтальной прокруткой и прокрутка корня и его предков: ничего не должно быть сдвинуто. */
async function scrolledElements(page: Page) {
  return page.evaluate(() => {
    const shifted = [...document.querySelectorAll('*')]
      .filter((el) => el.scrollLeft !== 0)
      .map(
        (el) => `${el.tagName}.${String(el.className).slice(0, 40)} scrollLeft=${el.scrollLeft}`,
      );
    const root = document.querySelector('#root > *') as HTMLElement;
    const chain: HTMLElement[] = [];
    for (let el: HTMLElement | null = root; el; el = el.parentElement) chain.push(el);
    return {
      shifted,
      chain: chain.map((el) => [el.scrollLeft, el.scrollTop]),
    };
  });
}

/** Главные кнопки панели управления видны целиком: не обрезаны, не спрятаны в прокрутке. */
async function expectMainButtonsVisible(page: Page, label: string) {
  const footer = page.getByRole('contentinfo', { name: 'Управление встречей' });
  const window = page.viewportSize()!;
  for (const name of ['Микрофон', 'Камера', 'Чат', 'Завершить встречу']) {
    const button = footer.getByRole('button', { name: new RegExp(`^${name}`) });
    await expect(button, `${label}: «${name}»`).toBeVisible();
    const box = (await button.boundingBox())!;
    expect(box.x, `${label}: «${name}» слева`).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width, `${label}: «${name}» справа`).toBeLessThanOrEqual(window.width);
    expect(box.y + box.height, `${label}: «${name}» снизу`).toBeLessThanOrEqual(window.height);
  }
}

async function expectFitsWindow(page: Page, label: string) {
  const scrolled = await scrolledElements(page);
  expect(scrolled.shifted, `${label}: сдвинутые элементы`).toEqual([]);
  expect(
    scrolled.chain.flat().every((v) => v === 0),
    `${label}: корень и предки не прокручены`,
  ).toBe(true);
  const m = await measure(page);
  const info = `${label}: ${JSON.stringify(m)}`;
  expect(m.scrollWidth, `горизонтальная прокрутка – ${info}`).toBeLessThanOrEqual(m.innerWidth);
  expect(m.scrollHeight, `вертикальная прокрутка – ${info}`).toBeLessThanOrEqual(m.innerHeight);
  expect(m.left, `левый край корня – ${info}`).toBe(0);
  expect(m.top, `верхний край корня – ${info}`).toBe(0);
  expect(m.width, info).toBe(m.innerWidth);
  expect(m.height, info).toBe(m.innerHeight);
  expect([m.scrollX, m.scrollY], info).toEqual([0, 0]);
}

for (const { width, height } of WIDTHS) {
  test(`комната на ${width} px: нет прокрутки документа, корень на все окно`, async ({ page }) => {
    await signIn(page);
    await page.setViewportSize({ width, height });
    await page.goto('/room/m-active');
    await expect(
      page.getByRole('heading', { level: 1, name: 'Еженедельная планерка команды' }),
    ).toBeVisible();
    await expectFitsWindow(page, 'без панелей');
    await expectMainButtonsVisible(page, 'без панелей');

    // страницу пытаются прокрутить колесом и клавишами: она не двигается
    await page.mouse.wheel(300, 300);
    await page.keyboard.press('End');
    await expectFitsWindow(page, 'после попытки прокрутки');

    // боковые панели (в мок-комнате чат и участники) тоже умещаются
    for (const tab of ['Участники', 'Чат']) {
      await page.getByRole('button', { name: tab }).click();
      await expect(page.getByRole('complementary')).toBeVisible();
      await expectFitsWindow(page, `панель «${tab}»`);
      await expectMainButtonsVisible(page, `панель «${tab}»`);
    }

    // Tab по всей панели управления: фокус ничего не сдвигает
    await page
      .getByRole('contentinfo', { name: 'Управление встречей' })
      .locator('button')
      .first()
      .focus();
    for (let i = 0; i < 12; i += 1) {
      await page.keyboard.press('Tab');
      await expectFitsWindow(page, `Tab ${i + 1}`);
    }
  });
}

test('после выхода из комнаты прокрутка страницы возвращается', async ({ page }) => {
  await signIn(page);
  await page.goto('/room/m-active');
  await page.getByRole('heading', { level: 1, name: 'Еженедельная планерка команды' }).waitFor();
  expect(await page.evaluate(() => getComputedStyle(document.body).overflow)).toBe('clip');

  await page.goto('/meetings');
  await expect(page.getByRole('heading', { level: 1, name: 'Встречи' })).toBeVisible();
  const overflow = await page.evaluate(() => [
    getComputedStyle(document.documentElement).overflow,
    getComputedStyle(document.body).overflow,
  ]);
  expect(overflow).toEqual(['visible', 'visible']);
});
