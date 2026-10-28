import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { createToken, LIVEKIT_URL } from './livekit-token';

// Критерий EMO-53: два участника видят и слышат друг друга в прототипе видеовстречи через LiveKit.
// Нужен запущенный `livekit-server --dev` (README, раздел «LiveKit для e2e»). Один Chromium, два контекста.

/** Запоминает все RTCPeerConnection страницы, чтобы читать getStats(): объекта Room из теста не достать. */
const TRACK_PEER_CONNECTIONS = () => {
  const w = window as unknown as { __pcs: RTCPeerConnection[] };
  w.__pcs = [];
  const Native = window.RTCPeerConnection;
  window.RTCPeerConnection = class extends Native {
    constructor(config?: RTCConfiguration) {
      super(config);
      w.__pcs.push(this);
    }
  };
};

async function join(context: BrowserContext, room: string, identity: string, name: string) {
  const page = await context.newPage();
  await page.addInitScript(TRACK_PEER_CONNECTIONS);
  await page.goto('/dev/livekit');
  await page.getByLabel('Адрес сервера').fill(LIVEKIT_URL);
  await page.getByLabel('Токен доступа').fill(await createToken(room, identity, name));
  await page.getByRole('button', { name: 'Подключиться' }).click();
  await expect(page.getByTestId('lk-state')).toHaveAttribute('data-state', 'connected');
  return page;
}

/** Чужая плитка с реально идущим видео (есть кадры, а не только элемент `<video>`). */
async function expectRemoteVideo(page: Page, remoteName: string) {
  const tile = page.locator('[data-lk-local-participant="false"]', { hasText: remoteName });
  await expect(tile).toBeVisible();
  await expect
    .poll(() => tile.locator('video').evaluate((v: HTMLVideoElement) => v.videoWidth), {
      message: `видео участника ${remoteName} не пришло`,
      timeout: 20_000,
    })
    .toBeGreaterThan(0);
}

/** Суммарно принятые байты входящего аудио (inbound-rtp, kind=audio) по всем соединениям страницы. */
function inboundAudioBytes(page: Page): Promise<number> {
  return page.evaluate(async () => {
    const pcs = (window as unknown as { __pcs: RTCPeerConnection[] }).__pcs;
    let total = 0;
    for (const pc of pcs) {
      const report = await pc.getStats();
      report.forEach((stat) => {
        if (stat.type === 'inbound-rtp' && stat.kind === 'audio') total += stat.bytesReceived ?? 0;
      });
    }
    return total;
  });
}

/** Звук слышен: bytesReceived входящего аудио растёт (фейковый микрофон Chromium даёт сигнал). */
async function expectRemoteAudio(page: Page, remoteName: string) {
  await expect
    .poll(() => inboundAudioBytes(page), {
      message: `звук участника ${remoteName} не приходит`,
      timeout: 20_000,
    })
    .toBeGreaterThan(0);
  const before = await inboundAudioBytes(page);
  await expect
    .poll(() => inboundAudioBytes(page), {
      message: `входящий звук от ${remoteName} не растёт`,
      timeout: 10_000,
    })
    .toBeGreaterThan(before);
}

test('два участника видят и слышат друг друга', async ({ browser }) => {
  const room = `e2e-${Date.now().toString(36)}`;
  const ctxA = await browser.newContext({ permissions: ['camera', 'microphone'] });
  const ctxB = await browser.newContext({ permissions: ['camera', 'microphone'] });
  try {
    const alice = await join(ctxA, room, 'alice', 'Алиса');
    const bob = await join(ctxB, room, 'bob', 'Боб');

    await expectRemoteVideo(alice, 'Боб');
    await expectRemoteVideo(bob, 'Алиса');
    await expectRemoteAudio(alice, 'Боб');
    await expectRemoteAudio(bob, 'Алиса');
    await expect(alice.getByTestId('lk-gallery')).toHaveAttribute('data-tiles', '2');
    await expect(bob.getByTestId('lk-gallery')).toHaveAttribute('data-tiles', '2');
  } finally {
    await ctxA.close();
    await ctxB.close();
  }
});
