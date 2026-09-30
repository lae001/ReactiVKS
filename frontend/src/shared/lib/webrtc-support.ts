/**
 * Проверка возможностей браузера перед входом во встречу
 * (docs/frontend/README.md, «Поддержка браузеров»). Используется в лобби и песочнице LiveKit.
 */
export interface WebRtcSupport {
  peerConnection: boolean;
  getUserMedia: boolean;
  secureContext: boolean;
}

export function checkWebRtcSupport(win: Window & typeof globalThis = window): WebRtcSupport {
  return {
    peerConnection: typeof win.RTCPeerConnection === 'function',
    getUserMedia: typeof win.navigator?.mediaDevices?.getUserMedia === 'function',
    // getUserMedia доступен только по HTTPS или на localhost
    secureContext: win.isSecureContext,
  };
}

export function isWebRtcSupported(s: WebRtcSupport): boolean {
  return s.peerConnection && s.getUserMedia && s.secureContext;
}

/** Понятное пользователю сообщение, если чего-то не хватает; null – все в порядке. */
export function describeWebRtcProblem(s: WebRtcSupport): string | null {
  if (!s.secureContext) {
    return 'Страница открыта без HTTPS. Браузер не разрешит доступ к камере — откройте ссылку, начинающуюся с https://.';
  }
  if (!s.peerConnection || !s.getUserMedia) {
    return 'Этот браузер не поддерживает видеовстречи. Откройте ссылку в Chrome, Edge, Яндекс Браузере, Firefox или Safari 17+.';
  }
  return null;
}
