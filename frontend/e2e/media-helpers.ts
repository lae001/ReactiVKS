import { expect, type Page } from '@playwright/test';

/** Запоминает все RTCPeerConnection страницы, чтобы читать getStats(): объекта Room из теста не достать. */
export const TRACK_PEER_CONNECTIONS = () => {
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

/** Чужая плитка с реально идущим видео (есть кадры, а не только элемент `<video>`). */
export async function expectRemoteVideo(page: Page, remoteName: string) {
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
export function inboundAudioBytes(page: Page): Promise<number> {
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
export async function expectRemoteAudio(page: Page, remoteName: string) {
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
