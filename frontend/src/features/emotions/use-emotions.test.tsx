import { act, renderHook } from '@testing-library/react';
import { useSessionStore } from '@/shared/api/session';
import { useEmotions } from './use-emotions';
import { EMOTION_LABELS } from '@/shared/config/emotions';

class Socket {
  static OPEN = 1;
  static instances: Socket[] = [];
  readyState = 1;
  sent: Record<string, unknown>[] = [];
  onopen?: () => void;
  onmessage?: (event: { data: string }) => void;
  onclose?: (event: { code: number }) => void;
  constructor(
    readonly url: string,
    readonly protocol: string,
  ) {
    Socket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(JSON.parse(data));
  }
  close() {
    this.readyState = 3;
  }
  receive(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}
beforeEach(() => {
  vi.useFakeTimers();
  Socket.instances = [];
  vi.stubGlobal('WebSocket', Socket);
  useSessionStore.setState({ accessToken: 'test-only', status: 'authenticated' });
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
it('гость не открывает канал', () => {
  renderHook(() => useEmotions('m', false));
  expect(Socket.instances).toHaveLength(0);
});
it('auth → welcome → subscribe; обновление токена и запрет доступа', () => {
  const { result } = renderHook(() => useEmotions('m', true));
  const socket = Socket.instances[0]!;
  expect(socket.protocol).toBe('vks.v1');
  expect(socket.url).not.toContain('test-only');
  act(() => socket.onopen?.());
  expect(socket.sent[0]).toEqual({ type: 'auth', token: 'test-only' });
  act(() => socket.receive({ type: 'welcome' }));
  expect(socket.sent[1]).toEqual({ type: 'subscribe', meeting_id: 'm' });
  act(() =>
    socket.receive({
      type: 'subscribed',
      meeting_id: 'm',
      snapshot: { labels: EMOTION_LABELS, analysis: { state: 'active' }, participants: [] },
    }),
  );
  expect(result.current.data.analysis).toBe('active');
  act(() => useSessionStore.setState({ accessToken: 'new-test-only' }));
  expect(socket.sent.at(-1)).toEqual({ type: 'auth.refresh', token: 'new-test-only' });
  act(() => {
    void socket.onclose?.({ code: 4403 });
  });
  expect(result.current.data.participants).toEqual([]);
  expect(result.current.status).toContain('Нет доступа');
  act(() => vi.advanceTimersByTime(30000));
  expect(Socket.instances).toHaveLength(1);
});
it('смена встречи сразу скрывает предыдущие данные, разрыв вызывает повторное подключение', () => {
  const { result, rerender } = renderHook(({ id }) => useEmotions(id, true), {
    initialProps: { id: 'm' },
  });
  const old = Socket.instances[0]!;
  rerender({ id: 'n' });
  expect(result.current.meetingId).toBe('n');
  expect(old.readyState).toBe(3);
  act(() => {
    void Socket.instances[1]!.onclose?.({ code: 1012 });
  });
  act(() => vi.advanceTimersByTime(600));
  expect(Socket.instances).toHaveLength(3);
});
