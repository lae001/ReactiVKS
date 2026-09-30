import { describeWebRtcProblem, isWebRtcSupported } from './webrtc-support';

describe('проверка поддержки WebRTC', () => {
  const ok = { peerConnection: true, getUserMedia: true, secureContext: true };

  it('все есть – проблем нет', () => {
    expect(isWebRtcSupported(ok)).toBe(true);
    expect(describeWebRtcProblem(ok)).toBeNull();
  });

  it('без HTTPS – подсказка про https', () => {
    expect(describeWebRtcProblem({ ...ok, secureContext: false })).toMatch(/https/);
  });

  it('нет RTCPeerConnection – подсказка про браузер', () => {
    expect(describeWebRtcProblem({ ...ok, peerConnection: false })).toMatch(/Chrome/);
  });
});
