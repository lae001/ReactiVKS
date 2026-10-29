import { act, renderHook } from '@testing-library/react';

import { useMicLevel } from './use-mic-level';

function stubAudioContext(samples: () => number) {
  const close = vi.fn(() => Promise.resolve());
  class FakeAnalyser {
    fftSize = 0;
    getByteTimeDomainData(data: Uint8Array) {
      data.fill(samples());
    }
  }
  class FakeContext {
    createAnalyser = () => new FakeAnalyser();
    createMediaStreamSource = () => ({ connect: vi.fn() });
    close = close;
  }
  vi.stubGlobal('AudioContext', FakeContext);
  return close;
}

const micStream = { getAudioTracks: () => [{}] } as unknown as MediaStream;

describe('уровень микрофона', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('тишина – 0, громкий звук – ближе к 1', () => {
    let sample = 128;
    stubAudioContext(() => sample);
    const { result } = renderHook(() => useMicLevel(micStream));

    act(() => void vi.advanceTimersByTime(70));
    expect(result.current).toBe(0);

    sample = 200;
    act(() => void vi.advanceTimersByTime(70));
    expect(result.current).toBeGreaterThan(0.5);
    expect(result.current).toBeLessThanOrEqual(1);
  });

  it('без потока уровень 0, при размонтировании контекст закрывается', () => {
    const close = stubAudioContext(() => 128);
    expect(renderHook(() => useMicLevel(null)).result.current).toBe(0);
    renderHook(() => useMicLevel(micStream)).unmount();
    expect(close).toHaveBeenCalled();
  });

  it('без Web Audio API уровень 0 и ничего не падает', () => {
    const { result } = renderHook(() => useMicLevel(micStream));
    expect(result.current).toBe(0);
  });
});
