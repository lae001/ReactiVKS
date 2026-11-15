import { act, renderHook } from '@testing-library/react';

import { estimateStart, useMeetingElapsed } from './meeting-timer';
import { roomKey } from './room-state';

const T0 = Date.parse('2026-10-29T10:00:00Z');

describe('начало встречи', () => {
  it('started_at с сервера важнее всего остального', () => {
    expect(
      estimateStart({
        startedAt: '2026-10-29T09:00:00Z',
        joinedAt: [new Date(T0)],
        stored: T0 - 1,
        fallback: T0,
      }),
    ).toBe(Date.parse('2026-10-29T09:00:00Z'));
  });

  it('без started_at (гость): самый ранний вход участника, но не позже запомненного', () => {
    const joined = [new Date(T0 + 5000), new Date(T0 + 1000), undefined];
    expect(estimateStart({ joinedAt: joined, stored: null, fallback: T0 + 9000 })).toBe(T0 + 1000);
    expect(estimateStart({ joinedAt: joined, stored: T0 - 3000, fallback: T0 + 9000 })).toBe(
      T0 - 3000,
    );
  });

  it('ничего не известно – момент открытия страницы; нечитаемый started_at игнорируется', () => {
    expect(estimateStart({ joinedAt: [], stored: null, fallback: T0 })).toBe(T0);
    expect(estimateStart({ startedAt: 'не дата', joinedAt: [], stored: null, fallback: T0 })).toBe(
      T0,
    );
  });
});

describe('таймер встречи', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.useFakeTimers();
    vi.setSystemTime(T0);
  });
  afterEach(() => vi.useRealTimers());

  it('считает от started_at, а не от монтирования: после «обновления страницы» не обнуляется', () => {
    const started = new Date(T0 - 125_000).toISOString(); // встреча идет 2:05
    const first = renderHook(() => useMeetingElapsed('m-1', started, []));
    expect(first.result.current).toBe(125);
    act(() => void vi.advanceTimersByTime(3000));
    expect(first.result.current).toBe(128);

    first.unmount(); // обновление страницы
    const second = renderHook(() => useMeetingElapsed('m-1', started, []));
    expect(second.result.current).toBe(128);
  });

  it('гость: от самого раннего входа в комнату; запомненное начало переживает обновление', () => {
    const organizerJoined = new Date(T0 - 60_000);
    const first = renderHook(() => useMeetingElapsed('m-1', undefined, [organizerJoined]));
    expect(first.result.current).toBe(60);
    expect(sessionStorage.getItem(roomKey.startedAt('m-1'))).toBe(String(T0 - 60_000));

    first.unmount();
    act(() => void vi.advanceTimersByTime(10_000));
    // после обновления в комнате уже нет данных о входе организатора: берется запомненное
    const second = renderHook(() => useMeetingElapsed('m-1', undefined, []));
    expect(second.result.current).toBe(70);
  });

  it('идет раз в секунду; без источников считает от открытия страницы', () => {
    const view = renderHook(() => useMeetingElapsed('m-9', null, []));
    expect(view.result.current).toBe(0);
    act(() => void vi.advanceTimersByTime(5000));
    expect(view.result.current).toBe(5);
  });

  it('у каждой встречи свое начало', () => {
    sessionStorage.setItem(roomKey.startedAt('m-1'), String(T0 - 500_000));
    const other = renderHook(() => useMeetingElapsed('m-2', undefined, []));
    expect(other.result.current).toBe(0);
  });
});
