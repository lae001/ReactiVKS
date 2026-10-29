import { act, renderHook } from '@testing-library/react';

import {
  CHAT_SYNC_TOPIC,
  encodeHistory,
  encodeRequest,
  loadChat,
  MAX_REPLY_DELAY_MS,
  REQUEST_INTERVAL_MS,
  REQUESTER_QUIET_MS,
  saveChat,
  type StoredMessage,
} from './chat-history';
import { type LiveChatMessage, useRoomChat } from './use-room-chat';

const NOW = Date.parse('2026-10-29T10:00:00Z');
const stored = (n: number, extra: Partial<StoredMessage> = {}): StoredMessage => ({
  id: `m${n}`,
  from: 'p_b',
  name: 'Борис',
  text: `текст ${n}`,
  at: NOW - 60_000 + n * 1000,
  ...extra,
});
const liveMsg = (n: number, identity = 'p_b'): LiveChatMessage => ({
  id: `m${n}`,
  message: `текст ${n}`,
  timestamp: NOW - 60_000 + n * 1000,
  from: { identity, name: identity === 'p_b' ? 'Борис' : 'Анна', isLocal: identity === 'p_self' },
});
const from = (identity: string) => ({ identity, name: identity, isLocal: false });
const request = (sender: string) => ({
  topic: CHAT_SYNC_TOPIC,
  payload: encodeRequest(),
  from: from(sender),
});
const history = (sender: string, messages: StoredMessage[]) =>
  encodeHistory(messages).map((payload) => ({
    topic: CHAT_SYNC_TOPIC,
    payload,
    from: from(sender),
  }));

function setup(
  props: {
    live?: LiveChatMessage[];
    humans?: string[];
    selfIdentity?: string;
    connected?: boolean;
  } = {},
) {
  const publish = vi.fn().mockResolvedValue(undefined);
  const hook = renderHook(
    (p: typeof props) =>
      useRoomChat({
        meetingId: 'm-1',
        live: p.live ?? [],
        selfIdentity: p.selfIdentity ?? 'p_self',
        humans: p.humans ?? ['p_self', 'p_b'],
        connected: p.connected ?? true,
        publish,
      }),
    { initialProps: props },
  );
  return { publish, hook };
}

const syncCalls = (publish: ReturnType<typeof vi.fn>) =>
  publish.mock.calls.filter(([, options]) => options.topic === CHAT_SYNC_TOPIC);

describe('история чата', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => vi.useRealTimers());

  it('после обновления страницы своя история видна и дальше дополняется живыми сообщениями', () => {
    saveChat('m-1', [stored(1), stored(2)]);
    const { hook } = setup();
    expect(hook.result.current.messages.map((m) => m.id)).toEqual(['m1', 'm2']);

    hook.rerender({ live: [liveMsg(3)] });
    expect(hook.result.current.messages.map((m) => m.id)).toEqual(['m1', 'm2', 'm3']);
    // записано во вкладку: переживет следующее обновление
    expect(loadChat('m-1').map((m) => m.id)).toEqual(['m1', 'm2', 'm3']);
  });

  it('одно и то же сообщение из хранилища и из живого потока не дублируется', () => {
    saveChat('m-1', [stored(1)]);
    const { hook } = setup({ live: [liveMsg(1)] });
    expect(hook.result.current.messages).toHaveLength(1);
  });

  it('при входе отправляется запрос истории (reliable, vks.chat.sync), один раз', () => {
    const { publish, hook } = setup({ connected: false });
    expect(syncCalls(publish)).toHaveLength(0);
    hook.rerender({ connected: true });
    hook.rerender({ connected: true, live: [liveMsg(1)] });
    const calls = syncCalls(publish);
    expect(calls).toHaveLength(1);
    expect(calls[0]![1]).toEqual({ reliable: true, topic: CHAT_SYNC_TOPIC });
    expect(new TextDecoder().decode(calls[0]![0])).toBe('{"v":1,"type":"history_request"}');
  });

  it('новый участник получает ответ, дедуплицированный и по времени; история не считается живым потоком', () => {
    const { hook } = setup({ humans: ['p_self', 'p_b'] });
    const messages = [stored(2), stored(1), stored(3)];
    act(() => {
      for (const part of history('p_b', messages)) hook.result.current.receive(part);
      for (const part of history('p_b', messages)) hook.result.current.receive(part); // повтор
    });
    expect(hook.result.current.messages.map((m) => m.id)).toEqual(['m1', 'm2', 'm3']);
  });

  describe('кто отвечает', () => {
    it('отвечает только участник с наименьшей identity среди остальных, с задержкой 0–300 мс', () => {
      saveChat('m-1', [stored(1), stored(2)]);
      // p_a (я) – наименьшая среди остальных, кроме запросившего p_z
      const mine = setup({ selfIdentity: 'p_a', humans: ['p_a', 'p_m', 'p_z'] });
      const baseline = syncCalls(mine.publish).length; // собственный запрос при входе
      act(() => mine.hook.result.current.receive(request('p_z')));
      expect(syncCalls(mine.publish)).toHaveLength(baseline); // еще не отправлено: ждем задержку
      act(() => void vi.advanceTimersByTime(MAX_REPLY_DELAY_MS));
      expect(syncCalls(mine.publish).length).toBeGreaterThan(baseline);
      const reply = syncCalls(mine.publish).at(-1)!;
      expect(reply[1]).toEqual({ reliable: true, topic: CHAT_SYNC_TOPIC });

      // p_m – не наименьшая (p_a меньше): молчит
      const other = setup({ selfIdentity: 'p_m', humans: ['p_a', 'p_m', 'p_z'] });
      const before = syncCalls(other.publish).length;
      act(() => other.hook.result.current.receive(request('p_z')));
      act(() => void vi.advanceTimersByTime(1000));
      expect(syncCalls(other.publish)).toHaveLength(before);
    });

    it('запросивший не отвечает сам себе: если остальных нет – ответа нет', () => {
      saveChat('m-1', [stored(1)]);
      const { publish, hook } = setup({ selfIdentity: 'p_a', humans: ['p_a'] });
      const before = syncCalls(publish).length;
      act(() => hook.result.current.receive(request('p_a')));
      act(() => void vi.advanceTimersByTime(1000));
      expect(syncCalls(publish)).toHaveLength(before);
    });

    it('если до отправки пришел чужой ответ, свой не отправляется', () => {
      saveChat('m-1', [stored(1)]);
      const { publish, hook } = setup({ selfIdentity: 'p_a', humans: ['p_a', 'p_m', 'p_z'] });
      const before = syncCalls(publish).length;
      act(() => hook.result.current.receive(request('p_z')));
      act(() => void vi.advanceTimersByTime(1));
      for (const part of history('p_m', [stored(5)])) act(() => hook.result.current.receive(part));
      act(() => void vi.advanceTimersByTime(MAX_REPLY_DELAY_MS));
      expect(syncCalls(publish)).toHaveLength(before);
    });

    it('запросы истории не чаще одного в 5 секунд от одного участника', () => {
      saveChat('m-1', [stored(1)]);
      const { publish, hook } = setup({ selfIdentity: 'p_a', humans: ['p_a', 'p_z'] });
      const before = syncCalls(publish).length;
      act(() => hook.result.current.receive(request('p_z')));
      act(() => void vi.advanceTimersByTime(MAX_REPLY_DELAY_MS));
      const afterFirst = syncCalls(publish).length;
      expect(afterFirst).toBeGreaterThan(before);

      act(() => hook.result.current.receive(request('p_z')));
      act(() => void vi.advanceTimersByTime(MAX_REPLY_DELAY_MS));
      expect(syncCalls(publish)).toHaveLength(afterFirst);

      act(() => void vi.advanceTimersByTime(REQUEST_INTERVAL_MS));
      act(() => hook.result.current.receive(request('p_z')));
      act(() => void vi.advanceTimersByTime(MAX_REPLY_DELAY_MS));
      expect(syncCalls(publish).length).toBeGreaterThan(afterFirst);
    });
  });

  describe('чужие данные не доверенные', () => {
    it('история от участника, который сам только что запросил ее, не принимается', () => {
      const { hook } = setup({ humans: ['p_self', 'p_x'] });
      act(() => hook.result.current.receive(request('p_x')));
      for (const part of history('p_x', [stored(1)])) act(() => hook.result.current.receive(part));
      expect(hook.result.current.messages).toEqual([]);

      // спустя время он уже мог получить историю и может ей делиться
      act(() => void vi.advanceTimersByTime(REQUESTER_QUIET_MS + 1));
      for (const part of history('p_x', [stored(1)])) act(() => hook.result.current.receive(part));
      expect(hook.result.current.messages).toHaveLength(1);
    });

    it('чужая тема, собственные данные, мусор и подделка схемы отбрасываются', () => {
      const { hook } = setup();
      const bad = [
        { topic: 'lk.chat', payload: encodeRequest(), from: from('p_b') },
        { topic: CHAT_SYNC_TOPIC, payload: encodeRequest(), from: undefined },
        {
          topic: CHAT_SYNC_TOPIC,
          payload: encodeRequest(),
          from: { ...from('p_self'), isLocal: true },
        },
        { topic: CHAT_SYNC_TOPIC, payload: new TextEncoder().encode('мусор'), from: from('p_b') },
        {
          topic: CHAT_SYNC_TOPIC,
          payload: new TextEncoder().encode(
            JSON.stringify({
              v: 1,
              type: 'history',
              part: 1,
              parts: 1,
              messages: [{ id: 'x', text: 1 }],
            }),
          ),
          from: from('p_b'),
        },
        {
          topic: CHAT_SYNC_TOPIC,
          payload: new TextEncoder().encode(
            JSON.stringify({
              v: 1,
              type: 'history',
              part: 1,
              parts: 1,
              messages: [{ ...stored(1), text: 'я'.repeat(3000) }],
            }),
          ),
          from: from('p_b'),
        },
      ];
      act(() => bad.forEach((message) => hook.result.current.receive(message)));
      expect(hook.result.current.messages).toEqual([]);
    });
  });
});
