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

/** Видимый удалённый элемент, новые представленные кадры и декодирование того же receiver. */
export async function measureRemoteVideo(page: Page, identity: string) {
  const video = page.locator(
    `[data-participant-identity="${identity}"][data-lk-local-participant="false"] video`,
  );
  await expect(video).toBeVisible();
  await expect
    .poll(() => video.evaluate((v: HTMLVideoElement) => v.videoWidth * v.videoHeight))
    .toBeGreaterThan(0);
  const result = await video.evaluate(async (element: HTMLVideoElement) => {
    const track = (element.srcObject as MediaStream).getVideoTracks()[0];
    const pcs = (window as unknown as { __pcs: RTCPeerConnection[] }).__pcs;
    const receiver = pcs.flatMap((pc) => pc.getReceivers()).find((r) => r.track.id === track?.id);
    if (!receiver) throw new Error('Нет receiver видимого видеотрека');
    const decoded = async () => {
      const report = await receiver.getStats();
      let count = 0;
      report.forEach((s) => {
        if (s.type === 'inbound-rtp' && s.kind === 'video') count += s.framesDecoded ?? 0;
      });
      return count;
    };
    const before = await decoded();
    const frames = await new Promise<number>((resolve, reject) => {
      let first: number | undefined;
      let callback = 0;
      const timeout = window.setTimeout(() => {
        element.cancelVideoFrameCallback(callback);
        reject(new Error('Нет новых представленных кадров'));
      }, 10000);
      const next: VideoFrameRequestCallback = (_, metadata) => {
        first ??= metadata.presentedFrames;
        if (metadata.presentedFrames - first >= 5) {
          clearTimeout(timeout);
          resolve(metadata.presentedFrames - first);
        } else callback = element.requestVideoFrameCallback(next);
      };
      callback = element.requestVideoFrameCallback(next);
    });
    return {
      width: element.videoWidth,
      height: element.videoHeight,
      presentedFrames: frames,
      framesDecodedBefore: before,
      framesDecodedAfter: await decoded(),
    };
  });
  expect(result.framesDecodedAfter).toBeGreaterThan(result.framesDecodedBefore);
  return result;
}

/** Типы кандидатов именно выбранных transport-пар, без IP и учётных данных TURN. */
export async function selectedIcePairs(page: Page) {
  return page.evaluate(async () => {
    const pcs = (window as unknown as { __pcs: RTCPeerConnection[] }).__pcs;
    const pairs: { local: string; remote: string; protocol: string; state: string }[] = [];
    for (const pc of pcs) {
      const report = await pc.getStats();
      report.forEach((stat) => {
        if (stat.type !== 'transport' || !stat.selectedCandidatePairId) return;
        const pair = report.get(stat.selectedCandidatePairId);
        if (!pair) return;
        const local = report.get(pair.localCandidateId);
        const remote = report.get(pair.remoteCandidateId);
        pairs.push({
          local: local?.candidateType ?? 'unknown',
          remote: remote?.candidateType ?? 'unknown',
          protocol: local?.protocol ?? 'unknown',
          state: pair.state,
        });
      });
    }
    return pairs;
  });
}
