import { act, render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import {
  createReactionLimiter,
  encodeReaction,
  MAX_FLOATING,
  MAX_SHIFT_PX,
  MERGE_WINDOW_MS,
  parseReaction,
  REACTION_BURST,
  REACTION_INTERVAL_MS,
  REACTION_TOPIC,
  REACTION_WINDOW_MS,
  REACTIONS,
  useReactions,
} from './reactions';
import { ReactionsMenu } from './ReactionsMenu';
import { FLOAT_LIFETIME_MS, REDUCED_LIFETIME_MS, ReactionsOverlay } from './ReactionsOverlay';

const bytes = (text: string) => new TextEncoder().encode(text);
const data = (emoji: string) => encodeReaction(emoji);
const anna = { identity: 'p_anna', name: 'Анна', isLocal: false };

describe('формат реакции', () => {
  it('кодирование: версия и эмодзи; разбор принимает только шесть эмодзи из списка', () => {
    expect(new TextDecoder().decode(encodeReaction('👍'))).toBe('{"v":1,"emoji":"👍"}');
    for (const { emoji } of REACTIONS) expect(parseReaction(encodeReaction(emoji))).toBe(emoji);
    expect(REACTIONS.map((r) => r.emoji)).toEqual(['👍', '❤️', '😂', '😮', '👏', '🎉']);
  });

  it.each([
    ['мусор', bytes('не json')],
    ['пустое тело', bytes('')],
    ['не объект', bytes('"👍"')],
    ['null', bytes('null')],
    ['чужая версия', bytes('{"v":2,"emoji":"👍"}')],
    ['нет версии', bytes('{"emoji":"👍"}')],
    ['чужой эмодзи', bytes('{"v":1,"emoji":"💩"}')],
    ['не строка', bytes('{"v":1,"emoji":7}')],
    ['текст вместо эмодзи', bytes('{"v":1,"emoji":"<img src=x onerror=alert(1)>"}')],
    ['слишком большое тело', bytes(JSON.stringify({ v: 1, emoji: '👍', junk: 'x'.repeat(500) }))],
    ['не UTF-8', new Uint8Array([0xff, 0xfe, 0xfd])],
  ])('отбрасывается: %s', (_name, payload) => {
    expect(parseReaction(payload)).toBeNull();
  });
});

describe('лимитер: не чаще 1 в секунду и не больше 5 за 10 секунд', () => {
  it('интервал: следующая реакция через секунду', () => {
    const limiter = createReactionLimiter();
    expect(limiter.take('a', 0)).toBe(true);
    expect(limiter.take('a', REACTION_INTERVAL_MS - 1)).toBe(false);
    expect(limiter.waitMs('a', 400)).toBe(600);
    expect(limiter.take('a', REACTION_INTERVAL_MS)).toBe(true);
  });

  it('пять за 10 секунд: шестая ждет, пока из окна уйдет первая', () => {
    const limiter = createReactionLimiter();
    for (let i = 0; i < REACTION_BURST; i += 1) expect(limiter.take('a', i * 1000)).toBe(true);
    // 5 реакций в секунды 0–4: шестая в секунду 5 не проходит, ждать до 10-й секунды (0 + 10 с)
    expect(limiter.take('a', 5000)).toBe(false);
    expect(limiter.waitMs('a', 5000)).toBe(REACTION_WINDOW_MS - 5000);
    expect(limiter.take('a', REACTION_WINDOW_MS - 1)).toBe(false);
    expect(limiter.take('a', REACTION_WINDOW_MS)).toBe(true);
  });

  it('у каждого отправителя свой счетчик', () => {
    const limiter = createReactionLimiter();
    expect(limiter.take('a', 0)).toBe(true);
    expect(limiter.take('b', 0)).toBe(true);
    expect(limiter.take('a', 10)).toBe(false);
  });
});

describe('useReactions', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-29T10:00:00Z'));
  });
  afterEach(() => vi.useRealTimers());

  const setup = () => {
    const publish = vi.fn().mockResolvedValue(undefined);
    const hook = renderHook(() => useReactions(publish));
    return { publish, hook };
  };
  type Hook = ReturnType<typeof setup>['hook'];
  const receive = (hook: Hook, message: Record<string, unknown> = {}) =>
    act(() =>
      hook.result.current.receive({
        topic: REACTION_TOPIC,
        payload: data('👍'),
        from: anna,
        ...message,
      }),
    );
  const send = (hook: Hook, emoji: string) =>
    act(async () => void (await hook.result.current.send(emoji)));
  const tick = (ms: number) => act(() => void vi.advanceTimersByTime(ms));

  it('отправка: publishData с темой, reliable: false и JSON { v: 1, emoji }; у отправителя «Вы»', async () => {
    const { publish, hook } = setup();
    await send(hook, '🎉');
    expect(publish).toHaveBeenCalledTimes(1);
    const [payload, options] = publish.mock.calls[0]!;
    expect(new TextDecoder().decode(payload)).toBe('{"v":1,"emoji":"🎉"}');
    expect(options).toEqual({ reliable: false, topic: 'vks.reaction' });
    expect(hook.result.current.floating).toMatchObject([{ emoji: '🎉', name: 'Вы', count: 1 }]);
  });

  it('отправка: 1 в секунду; эмодзи вне списка не уходит', async () => {
    const { publish, hook } = setup();
    await send(hook, '👍');
    await send(hook, '❤️');
    expect(publish).toHaveBeenCalledTimes(1);

    tick(REACTION_INTERVAL_MS);
    await send(hook, '❤️');
    expect(publish).toHaveBeenCalledTimes(2);

    tick(REACTION_INTERVAL_MS);
    await send(hook, '💩');
    expect(publish).toHaveBeenCalledTimes(2);
  });

  it('отправка: пять за 10 секунд, затем blockedUntil – до освобождения лимита, не дольше 10 с', async () => {
    const { publish, hook } = setup();
    const start = Date.now();
    for (let i = 0; i < REACTION_BURST; i += 1) {
      await send(hook, REACTIONS[i]!.emoji);
      tick(REACTION_INTERVAL_MS);
    }
    expect(publish).toHaveBeenCalledTimes(REACTION_BURST);
    // после пятой реакции лимит исчерпан: ждать до конца окна первой
    expect(hook.result.current.blockedUntil).toBe(start + REACTION_WINDOW_MS);
    await send(hook, '👍');
    expect(publish).toHaveBeenCalledTimes(REACTION_BURST);

    tick(REACTION_WINDOW_MS - REACTION_BURST * REACTION_INTERVAL_MS);
    await send(hook, '👍');
    expect(publish).toHaveBeenCalledTimes(REACTION_BURST + 1);
  });

  it('сбой publishData не ломает интерфейс', async () => {
    const { publish, hook } = setup();
    publish.mockRejectedValueOnce(new Error('offline'));
    await send(hook, '👍');
    expect(hook.result.current.floating).toHaveLength(1);
  });

  it('прием: ник берется из участника LiveKit, а не из тела сообщения', () => {
    const { hook } = setup();
    receive(hook, { payload: bytes('{"v":1,"emoji":"😮","name":"Директор","from":"admin"}') });
    expect(hook.result.current.floating).toMatchObject([{ emoji: '😮', name: 'Анна' }]);
  });

  it('прием: чужая тема, мусор, чужие эмодзи, без отправителя и собственные данные отбрасываются молча', () => {
    const { hook } = setup();
    receive(hook, { topic: 'lk.chat' });
    receive(hook, { topic: undefined });
    receive(hook, { payload: bytes('мусор') });
    receive(hook, { payload: bytes('{"v":1,"emoji":"💩"}') });
    receive(hook, { from: undefined });
    receive(hook, { from: { ...anna, isLocal: true } });
    expect(hook.result.current.floating).toEqual([]);
  });

  it('прием: те же лимиты на отправителя – 1 в секунду и 5 за 10 с, у другого счетчик свой', () => {
    const { hook } = setup();
    const emojis = REACTIONS.map((r) => r.emoji);
    receive(hook, { payload: data(emojis[0]!) });
    receive(hook, { payload: data(emojis[1]!) }); // раньше чем через секунду – отброшена
    receive(hook, {
      payload: data(emojis[2]!),
      from: { identity: 'p_oleg', name: 'Олег', isLocal: false },
    });
    expect(hook.result.current.floating.map((f) => f.name)).toEqual(['Анна', 'Олег']);

    // пять за окно: шестая отброшена, хотя интервал соблюден
    for (let i = 1; i < REACTION_BURST; i += 1) {
      tick(REACTION_INTERVAL_MS);
      receive(hook, { payload: data(emojis[(i + 2) % 6]!) });
    }
    const afterFive = hook.result.current.floating.length;
    tick(REACTION_INTERVAL_MS);
    receive(hook, { payload: data('🎉') });
    expect(hook.result.current.floating).toHaveLength(afterFive);
  });

  it('склейка: одинаковые реакции одного отправителя в течение 2 с – один элемент с «×N»', () => {
    const { hook } = setup();
    receive(hook);
    tick(REACTION_INTERVAL_MS);
    receive(hook);
    tick(REACTION_INTERVAL_MS);
    receive(hook);
    expect(hook.result.current.floating).toHaveLength(1);
    expect(hook.result.current.floating[0]).toMatchObject({ emoji: '👍', count: 3 });
  });

  it('не склеиваются: другой эмодзи, другой отправитель, пауза дольше 2 с', () => {
    const { hook } = setup();
    receive(hook);
    tick(REACTION_INTERVAL_MS);
    receive(hook, { payload: data('❤️') });
    receive(hook, { from: { identity: 'p_oleg', name: 'Олег', isLocal: false } });
    expect(hook.result.current.floating).toHaveLength(3);

    tick(MERGE_WINDOW_MS + REACTION_INTERVAL_MS);
    receive(hook);
    expect(hook.result.current.floating).toHaveLength(4);
  });

  it(`одновременно не больше ${MAX_FLOATING}: лишние не показываются; сдвиг не больше ${MAX_SHIFT_PX} px`, () => {
    const { hook } = setup();
    for (let i = 0; i < MAX_FLOATING + 4; i += 1) {
      receive(hook, { from: { identity: `p_${i}`, name: `Гость ${i}`, isLocal: false } });
    }
    const items = hook.result.current.floating;
    expect(items).toHaveLength(MAX_FLOATING);
    expect(items.every((item) => Math.abs(item.dx) <= MAX_SHIFT_PX)).toBe(true);
    // освободилось место – следующая реакция снова показывается
    act(() => hook.result.current.expire(items[0]!.id));
    receive(hook, { from: { identity: 'p_new', name: 'Новый', isLocal: false } });
    expect(hook.result.current.floating).toHaveLength(MAX_FLOATING);
  });
});

describe('оверлей реакций', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  const item = { id: 1, sender: 'p_anna', emoji: '👏', name: 'Анна', count: 1, dx: 5, lastAt: 0 };

  it('эмодзи и ник отправителя, без кликов и скринридера; исчезает через 2,8 с', () => {
    const onExpire = vi.fn();
    render(<ReactionsOverlay items={[item]} onExpire={onExpire} />);
    const reaction = screen.getByTestId('reaction');
    expect(reaction).toHaveTextContent('👏');
    expect(reaction).toHaveTextContent('Анна');
    expect(reaction).not.toHaveTextContent('×');
    expect(reaction).toHaveClass('vks-reaction');
    expect(reaction).toHaveStyle({ '--vks-dx': '5px' });
    const overlay = reaction.closest('[aria-hidden]');
    expect(overlay).toHaveAttribute('aria-hidden', 'true');
    expect(overlay).toHaveClass('pointer-events-none');

    act(() => void vi.advanceTimersByTime(FLOAT_LIFETIME_MS - 1));
    expect(onExpire).not.toHaveBeenCalled();
    act(() => void vi.advanceTimersByTime(1));
    expect(onExpire).toHaveBeenCalledWith(1);
  });

  it('все реакции – в одной полосе внизу слева над панелью управления', () => {
    render(
      <ReactionsOverlay
        items={[item, { ...item, id: 2, emoji: '🎉', sender: 'p_oleg', name: 'Олег' }]}
        onExpire={vi.fn()}
      />,
    );
    const lanes = new Set(screen.getAllByTestId('reaction').map((el) => el.parentElement));
    expect(lanes.size).toBe(1);
    expect([...lanes][0]).toHaveClass('bottom-3', 'left-6');
  });

  it('склейка: «×3» и таймер жизни продлевается', () => {
    const onExpire = vi.fn();
    const { rerender } = render(<ReactionsOverlay items={[item]} onExpire={onExpire} />);
    act(() => void vi.advanceTimersByTime(FLOAT_LIFETIME_MS - 100));
    rerender(<ReactionsOverlay items={[{ ...item, count: 3 }]} onExpire={onExpire} />);
    expect(screen.getByTestId('reaction')).toHaveTextContent('×3');
    act(() => void vi.advanceTimersByTime(FLOAT_LIFETIME_MS - 100));
    expect(onExpire).not.toHaveBeenCalled();
    act(() => void vi.advanceTimersByTime(100));
    expect(onExpire).toHaveBeenCalledWith(1);
  });

  it('prefers-reduced-motion: короткий показ без движения', () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: query.includes('reduce'),
      media: query,
    }));
    const onExpire = vi.fn();
    render(<ReactionsOverlay items={[item]} onExpire={onExpire} />);
    act(() => void vi.advanceTimersByTime(REDUCED_LIFETIME_MS));
    expect(onExpire).toHaveBeenCalledWith(1);
    expect(REDUCED_LIFETIME_MS).toBeLessThan(FLOAT_LIFETIME_MS);
  });
});

describe('меню «Реакции»', () => {
  afterEach(() => vi.useRealTimers());

  it('клавиатура: Enter и пробел выбирают, Esc закрывает и возвращает фокус; у кнопок русские подписи', async () => {
    const user = userEvent.setup();
    const onPick = vi.fn();
    render(<ReactionsMenu onPick={onPick} />);
    const trigger = screen.getByRole('button', { name: 'Реакции' });
    expect(trigger).toHaveAttribute('aria-haspopup', 'true');

    await user.keyboard('{Tab}{Enter}');
    expect(trigger).toHaveAttribute('aria-pressed', 'true');
    const options = screen.getAllByRole('button', { name: /^Реакция: / });
    expect(options.map((b) => b.getAttribute('aria-label'))).toEqual([
      'Реакция: нравится',
      'Реакция: сердце',
      'Реакция: смешно',
      'Реакция: удивление',
      'Реакция: аплодисменты',
      'Реакция: праздник',
    ]);
    expect(options[0]).toHaveFocus();

    await user.keyboard('{Enter}');
    expect(onPick).toHaveBeenLastCalledWith('👍');
    await user.keyboard('{Tab}{ }');
    expect(onPick).toHaveBeenLastCalledWith('❤️');

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('group', { name: 'Выбор реакции' })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(onPick).toHaveBeenCalledTimes(2);
  });

  it('при превышении лимита: aria-disabled, «Слишком часто. Подождите ещё N с» с таймером, клики не проходят', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date('2026-10-29T10:00:00Z'));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onPick = vi.fn();
    render(<ReactionsMenu onPick={onPick} blockedUntil={Date.now() + 3000} />);
    await user.click(screen.getByRole('button', { name: 'Реакции' }));

    const group = screen.getByRole('group', { name: 'Выбор реакции' });
    const first = screen.getByRole('button', { name: 'Реакция: нравится' });
    expect(first).toHaveAttribute('aria-disabled', 'true');
    expect(first).not.toBeDisabled(); // остается в порядке обхода: скринридер ее читает
    expect(group).toHaveTextContent('Слишком часто. Подождите ещё 3 с');
    expect(group.querySelector('[aria-live="polite"]')).not.toBeNull();

    await user.click(first);
    expect(onPick).not.toHaveBeenCalled();

    act(() => void vi.advanceTimersByTime(1100));
    expect(group).toHaveTextContent('Подождите ещё 2 с');
    act(() => void vi.advanceTimersByTime(2000));
    expect(group).not.toHaveTextContent('Слишком часто');
    expect(first).not.toHaveAttribute('aria-disabled');
    await user.click(first);
    expect(onPick).toHaveBeenCalledWith('👍');
  });

  it('ожидание в подписи не больше 10 с', async () => {
    const user = userEvent.setup();
    render(<ReactionsMenu onPick={vi.fn()} blockedUntil={Date.now() + 60_000} />);
    await user.click(screen.getByRole('button', { name: 'Реакции' }));
    expect(screen.getByRole('group', { name: 'Выбор реакции' })).toHaveTextContent('ещё 10 с');
  });
});
