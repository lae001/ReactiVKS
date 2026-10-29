import { act, render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import {
  encodeReaction,
  MAX_FLOATING,
  parseReaction,
  REACTION_INTERVAL_MS,
  REACTION_TOPIC,
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
  const receive = (
    hook: ReturnType<typeof setup>['hook'],
    message: Partial<
      Parameters<ReturnType<typeof setup>['hook']['result']['current']['receive']>[0]
    >,
  ) =>
    act(() =>
      hook.result.current.receive({
        topic: REACTION_TOPIC,
        payload: data('👍'),
        from: anna,
        ...message,
      }),
    );

  it('отправка: publishData с темой, reliable: false и JSON { v: 1, emoji }; у отправителя «Вы»', async () => {
    const { publish, hook } = setup();
    await act(async () => void (await hook.result.current.send('🎉')));
    expect(publish).toHaveBeenCalledTimes(1);
    const [payload, options] = publish.mock.calls[0]!;
    expect(new TextDecoder().decode(payload)).toBe('{"v":1,"emoji":"🎉"}');
    expect(options).toEqual({ reliable: false, topic: 'vks.reaction' });
    expect(hook.result.current.floating).toMatchObject([{ emoji: '🎉', name: 'Вы' }]);
  });

  it('отправка не чаще одной в 300 мс; эмодзи вне списка не уходит', async () => {
    const { publish, hook } = setup();
    await act(async () => void (await hook.result.current.send('👍')));
    await act(async () => void (await hook.result.current.send('❤️')));
    expect(publish).toHaveBeenCalledTimes(1);

    act(() => void vi.advanceTimersByTime(REACTION_INTERVAL_MS));
    await act(async () => void (await hook.result.current.send('❤️')));
    expect(publish).toHaveBeenCalledTimes(2);

    act(() => void vi.advanceTimersByTime(REACTION_INTERVAL_MS));
    await act(async () => void (await hook.result.current.send('💩')));
    expect(publish).toHaveBeenCalledTimes(2);
  });

  it('сбой publishData не ломает интерфейс', async () => {
    const { publish, hook } = setup();
    publish.mockRejectedValueOnce(new Error('offline'));
    await act(async () => void (await hook.result.current.send('👍')));
    expect(hook.result.current.floating).toHaveLength(1);
  });

  it('прием: имя берется из участника LiveKit, а не из тела сообщения', () => {
    const { hook } = setup();
    receive(hook, {
      payload: bytes('{"v":1,"emoji":"😮","name":"Директор","from":"admin"}'),
    });
    expect(hook.result.current.floating).toMatchObject([{ emoji: '😮', name: 'Анна' }]);
    expect(hook.result.current.log).toMatchObject([{ emoji: '😮', name: 'Анна' }]);
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
    expect(hook.result.current.log).toEqual([]);
  });

  it('прием: не чаще одной в 300 мс от одного участника, у другого счетчик свой', () => {
    const { hook } = setup();
    receive(hook, {});
    receive(hook, {});
    receive(hook, { from: { identity: 'p_oleg', name: 'Олег', isLocal: false } });
    expect(hook.result.current.floating).toHaveLength(2);

    act(() => void vi.advanceTimersByTime(REACTION_INTERVAL_MS));
    receive(hook, {});
    expect(hook.result.current.floating).toHaveLength(3);
  });

  it(`одновременно не больше ${MAX_FLOATING}: лишние не показываются`, () => {
    const { hook } = setup();
    for (let i = 0; i < MAX_FLOATING + 5; i += 1) {
      receive(hook, { from: { identity: `p_${i}`, name: `Гость ${i}`, isLocal: false } });
    }
    expect(hook.result.current.floating).toHaveLength(MAX_FLOATING);
    // освободилось место – следующая реакция снова показывается
    act(() => hook.result.current.expire(hook.result.current.floating[0]!.id));
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

  const item = { id: 1, emoji: '👏', name: 'Анна', left: 40 };

  it('эмодзи с подписью, без кликов и скринридера; исчезает через 2,8 с', () => {
    const onExpire = vi.fn();
    render(<ReactionsOverlay items={[item]} onExpire={onExpire} />);
    const reaction = screen.getByTestId('reaction');
    expect(reaction).toHaveTextContent('👏');
    expect(reaction).toHaveTextContent('Анна');
    expect(reaction).toHaveClass('vks-reaction');
    expect(reaction.parentElement).toHaveAttribute('aria-hidden', 'true');
    expect(reaction.parentElement).toHaveClass('pointer-events-none');

    act(() => void vi.advanceTimersByTime(FLOAT_LIFETIME_MS - 1));
    expect(onExpire).not.toHaveBeenCalled();
    act(() => void vi.advanceTimersByTime(1));
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

describe('меню «Реакции»: клавиатура', () => {
  afterEach(() => vi.useRealTimers());

  it('Enter и пробел выбирают, Esc закрывает и возвращает фокус; у каждой кнопки подпись по-русски', async () => {
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
    // фокус сразу на первой реакции
    expect(options[0]).toHaveFocus();

    await user.keyboard('{Enter}');
    expect(onPick).toHaveBeenLastCalledWith('👍');
    expect(trigger).toHaveFocus();

    await user.keyboard('{Enter}{Tab}{ }');
    expect(onPick).toHaveBeenLastCalledWith('❤️');

    await user.keyboard('{Enter}{Escape}');
    expect(screen.queryByRole('group', { name: 'Выбор реакции' })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(onPick).toHaveBeenCalledTimes(2);
  });
});
