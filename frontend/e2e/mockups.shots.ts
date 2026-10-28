import { test, type Page } from '@playwright/test';

// Макеты экранов (EMO-52): снимает страницы приложения на тестовых данных в двух ширинах.
// Запуск: pnpm mockups. Результат – docs/frontend/mockups/<экран>-<ширина>.png

const OUT = '../docs/frontend/mockups';
const WIDTHS = [
  { width: 1280, height: 800 },
  { width: 360, height: 740 },
] as const;

const user = {
  id: '0192a000-0000-7000-8000-000000000001',
  email: 'ivan@example.ru',
  display_name: 'Иван Петров',
  role: 'organizer',
};

/** Вместо зеленой тестовой картинки Chromium – спокойный силуэт, чтобы макеты выглядели как встреча. */
async function mockCamera(page: Page) {
  await page.addInitScript(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 640;
    canvas.height = 480;
    const ctx = canvas.getContext('2d');
    const draw = () => {
      if (!ctx) return;
      const g = ctx.createLinearGradient(0, 0, 640, 480);
      g.addColorStop(0, '#2c4b57');
      g.addColorStop(1, '#16252d');
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, 640, 480);
      ctx.fillStyle = '#7fa6b3';
      ctx.beginPath();
      ctx.arc(320, 190, 70, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.ellipse(320, 480, 150, 130, 0, Math.PI, 0);
      ctx.fill();
    };
    draw();
    setInterval(draw, 200);
    const stream = canvas.captureStream(5);
    navigator.mediaDevices.getUserMedia = async () => stream.clone();
  });
}

async function mockApi(page: Page, signedIn: boolean) {
  await page.route('**/api/v1/auth/config', (r) =>
    r.fulfill({ json: { registration_enabled: true, password_reset_enabled: false } }),
  );
  await page.route('**/api/v1/auth/refresh', (r) =>
    signedIn
      ? r.fulfill({
          json: { access_token: 'mock', token_type: 'Bearer', expires_in: 900, user },
        })
      : r.fulfill({
          status: 401,
          contentType: 'application/problem+json',
          json: { code: 'unauthorized', title: 'unauthorized', status: 401 },
        }),
  );
  await page.route('**/api/v1/users/me', (r) => r.fulfill({ json: user }));
}

interface Screen {
  name: string;
  path: string;
  signedIn?: boolean;
  /** Действия перед съемкой */
  prepare?: (page: Page) => Promise<void>;
  fullPage?: boolean;
  /** Ждать этого текста перед съемкой */
  ready: string;
  state?: unknown;
}

const screens: Screen[] = [
  { name: 'login', path: '/login', signedIn: false, ready: 'Войти', fullPage: true },
  {
    name: 'register',
    path: '/register',
    signedIn: false,
    ready: 'Создать аккаунт',
    fullPage: true,
  },
  { name: 'meetings', path: '/meetings', signedIn: true, ready: 'Все встречи', fullPage: true },
  {
    name: 'meeting-new',
    path: '/meetings/new',
    signedIn: true,
    ready: 'Новая встреча',
    fullPage: true,
  },
  { name: 'settings', path: '/settings', signedIn: true, ready: 'Сохранить имя', fullPage: true },
  {
    name: 'meeting-card',
    path: '/meetings/m-later',
    signedIn: true,
    ready: 'Интервью',
    fullPage: true,
  },
  { name: 'report', path: '/meetings/m-ended', signedIn: true, ready: 'Участники', fullPage: true },
  {
    name: 'lobby',
    path: '/j/demoactive',
    signedIn: false,
    ready: 'Войти во встречу',
    fullPage: true,
  },
  { name: 'room', path: '/room/m-active', signedIn: true, ready: 'Идет анализ эмоций' },
  {
    name: 'room-emotions',
    path: '/room/m-active',
    signedIn: true,
    ready: 'Идет анализ эмоций',
    prepare: async (page) => {
      // на 1280 панель эмоций у организатора открыта сразу, на 360 – по кнопке
      const summary = page.getByText('Сводка встречи');
      if (!(await summary.isVisible())) await page.getByRole('button', { name: 'Эмоции' }).click();
      await summary.waitFor();
    },
  },
  { name: 'ui-emotions', path: '/dev/ui', signedIn: false, ready: 'UI-кит', fullPage: true },
];

const only = process.env.SHOTS?.split(',');

for (const screen of screens) {
  if (only && !only.includes(screen.name)) continue;
  for (const size of WIDTHS) {
    test(`${screen.name} ${size.width}`, async ({ page }) => {
      await page.setViewportSize(size);
      await mockCamera(page);
      await mockApi(page, screen.signedIn ?? false);
      await page.goto(screen.path);
      await page.getByText(screen.ready, { exact: false }).first().waitFor();
      await screen.prepare?.(page);
      await page.waitForTimeout(400); // шрифты и анимации
      await page.screenshot({
        path: `${OUT}/${screen.name}-${size.width}.png`,
        fullPage: screen.fullPage ?? false,
      });
    });
  }
}
