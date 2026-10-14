import { type ChildProcess, spawn } from 'node:child_process';

import { expect, test } from '@playwright/test';

import { createToken, LIVEKIT_URL } from './livekit-token';

// Дымовая проверка раскладки на 6–10 участниках (EMO-53, сверх критерия): `lk load-test` публикует
// синтетическое видео от N участников, один браузер подключается зрителем-участником и смотрит на сетку.
// N задается LK_SMOKE_PUBLISHERS (по умолчанию 9 + браузер = 10). Нужен установленный `lk` (livekit-cli).
const PUBLISHERS = Number(process.env.LK_SMOKE_PUBLISHERS ?? 9);

test(`галерея держит ${PUBLISHERS + 1} участников`, async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const room = `smoke-${Date.now().toString(36)}`;
  const lk: ChildProcess = spawn(
    'lk',
    [
      'load-test',
      '--dev',
      '--url',
      LIVEKIT_URL.replace(/^ws/, 'http'),
      '--room',
      room,
      '--video-publishers',
      String(PUBLISHERS),
      '--video-resolution',
      'low',
      '--num-per-second',
      '2',
      '--duration',
      '90s',
    ],
    { stdio: 'ignore' },
  );
  try {
    await page.goto('/dev/livekit');
    await page.getByLabel('Адрес сервера').fill(LIVEKIT_URL);
    await page.getByLabel('Токен доступа').fill(await createToken(room, 'viewer', 'Зритель'));
    await page.getByRole('button', { name: 'Подключиться' }).click();
    await expect(page.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');

    const gallery = page.getByTestId('lk-gallery');
    await expect(gallery).toHaveAttribute('data-tiles', String(PUBLISHERS + 1), {
      timeout: 60_000,
    });

    // Все плитки на странице целиком внутри контейнера и не нулевого размера
    const box = await gallery.boundingBox();
    expect(box).not.toBeNull();
    const tiles = page.locator('[data-testid="lk-gallery"] .lk-participant-tile');
    const count = await tiles.count();
    expect(count).toBe(PUBLISHERS + 1);
    for (let i = 0; i < count; i++) {
      const t = await tiles.nth(i).boundingBox();
      expect(t?.width).toBeGreaterThan(40);
      expect(t?.height).toBeGreaterThan(30);
      expect(t!.x).toBeGreaterThanOrEqual(box!.x - 1);
      expect(t!.y + t!.height).toBeLessThanOrEqual(box!.y + box!.height + 1);
    }
    await page.screenshot({ path: testInfo.outputPath(`gallery-${PUBLISHERS + 1}.png`) });
  } finally {
    // Останавливаем только свой дочерний процесс по дескриптору
    lk.kill('SIGTERM');
  }
});
