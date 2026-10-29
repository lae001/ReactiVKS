import { useCallback, useRef, useState } from 'react';

/** Тема данных LiveKit для реакций (docs/api/livekit-integration.md). */
export const REACTION_TOPIC = 'vks.reaction';

/** Допустимые реакции: все остальное во входящем сообщении молча отбрасывается. */
export const REACTIONS = [
  { emoji: '👍', label: 'Нравится' },
  { emoji: '❤️', label: 'Сердце' },
  { emoji: '😂', label: 'Смешно' },
  { emoji: '😮', label: 'Удивление' },
  { emoji: '👏', label: 'Аплодисменты' },
  { emoji: '🎉', label: 'Праздник' },
] as const;

const ALLOWED = new Set<string>(REACTIONS.map((r) => r.emoji));

/** Лимиты на одного участника: не чаще одной реакции в секунду и не больше пяти за 10 секунд. */
export const REACTION_INTERVAL_MS = 1000;
export const REACTION_BURST = 5;
export const REACTION_WINDOW_MS = 10_000;
/** Одновременно на экране не больше 8 эмодзи, лишние не показываются. */
export const MAX_FLOATING = 8;
/** Одинаковые реакции одного отправителя в пределах 2 секунд склеиваются в один элемент «×N». */
export const MERGE_WINDOW_MS = 2000;
/** Случайный сдвиг по горизонтали, не больше 12 px в обе стороны. */
export const MAX_SHIFT_PX = 12;

/**
 * Лимитер реакций по отправителям (скользящее окно). Работает и на отправке, и на приеме: принимающая сторона
 * не доверяет чужому клиенту и сама отбрасывает лишнее.
 */
export function createReactionLimiter() {
  const accepted = new Map<string, number[]>();

  /** Через сколько миллисекунд отправителю можно показать следующую реакцию (0 – сейчас). */
  function waitMs(key: string, now: number): number {
    const recent = (accepted.get(key) ?? []).filter((t) => now - t < REACTION_WINDOW_MS);
    accepted.set(key, recent);
    const last = recent.at(-1);
    const afterInterval = last === undefined ? 0 : last + REACTION_INTERVAL_MS - now;
    const afterWindow =
      recent.length >= REACTION_BURST
        ? recent[recent.length - REACTION_BURST]! + REACTION_WINDOW_MS - now
        : 0;
    return Math.max(0, afterInterval, afterWindow);
  }

  return {
    waitMs,
    /** Исчерпан ли лимит «пять за 10 секунд» (а не просто интервал в секунду). */
    burstReached(key: string, now: number): boolean {
      return (
        (accepted.get(key) ?? []).filter((t) => now - t < REACTION_WINDOW_MS).length >=
        REACTION_BURST
      );
    },
    /** Принимает реакцию, если лимит позволяет, и запоминает ее. */
    take(key: string, now: number): boolean {
      if (waitMs(key, now) > 0) return false;
      accepted.get(key)!.push(now);
      return true;
    },
  };
}

/** Тело сообщения: версия формата и эмодзи. Отправитель берется из участника LiveKit, а не из тела. */
export function encodeReaction(emoji: string): Uint8Array {
  return new TextEncoder().encode(JSON.stringify({ v: 1, emoji }));
}

/** Эмодзи из входящих данных или `null`, если это не реакция из белого списка. */
export function parseReaction(payload: Uint8Array): string | null {
  if (payload.byteLength === 0 || payload.byteLength > 128) return null;
  try {
    const data: unknown = JSON.parse(new TextDecoder().decode(payload));
    if (typeof data !== 'object' || data === null) return null;
    const { v, emoji } = data as { v?: unknown; emoji?: unknown };
    return v === 1 && typeof emoji === 'string' && ALLOWED.has(emoji) ? emoji : null;
  } catch {
    return null;
  }
}

export interface FloatingReaction {
  id: number;
  /** Отправитель (identity участника LiveKit или `self`): по нему склеиваются одинаковые реакции */
  sender: string;
  emoji: string;
  /** Подпись: ник отправителя или «Вы» */
  name: string;
  /** Сколько одинаковых реакций склеено («×N» при N > 1) */
  count: number;
  /** Случайный сдвиг по горизонтали в пикселях, |dx| ≤ 12 */
  dx: number;
  /** Когда пришла последняя из склеенных реакций */
  lastAt: number;
}

/** Что нужно от входящего сообщения данных: тема, тело и отправитель (участник LiveKit). */
export interface IncomingData {
  topic?: string;
  payload: Uint8Array;
  from?: { identity?: string; name?: string; isLocal?: boolean } | null;
}

export type PublishData = (
  data: Uint8Array,
  options: { reliable: boolean; topic: string },
) => Promise<void>;

/**
 * Реакции: отправка по каналу данных (без гарантии доставки), прием с проверкой, всплывающие эмодзи. Чужие данные
 * не доверенные: тема, формат и эмодзи проверяются, имя берется только из участника LiveKit, лимиты действуют и на
 * приеме. В чат реакции не попадают.
 */
export function useReactions(publish: PublishData) {
  const [floating, setFloating] = useState<FloatingReaction[]>([]);
  // Когда снова можно отправить реакцию (мс, Date.now()); 0 – можно сейчас
  const [block, setBlock] = useState({ until: 0, tooFrequent: false });
  const limiter = useRef(createReactionLimiter());
  const sequence = useRef(0);

  const show = useCallback((sender: string, name: string, emoji: string, now: number) => {
    sequence.current += 1;
    const id = sequence.current;
    setFloating((current) => {
      const same = current.find(
        (item) =>
          item.sender === sender && item.emoji === emoji && now - item.lastAt <= MERGE_WINDOW_MS,
      );
      if (same) {
        return current.map((item) =>
          item === same ? { ...item, count: item.count + 1, lastAt: now } : item,
        );
      }
      if (current.length >= MAX_FLOATING) return current;
      const dx = Math.round((Math.random() * 2 - 1) * MAX_SHIFT_PX);
      return [...current, { id, sender, emoji, name, count: 1, dx, lastAt: now }];
    });
  }, []);

  const send = useCallback(
    async (emoji: string): Promise<boolean> => {
      if (!ALLOWED.has(emoji)) return false;
      const now = Date.now();
      if (!limiter.current.take('self', now)) return false;
      // Следующая реакция возможна не раньше, чем освободится лимит (интервал или окно из пяти)
      const wait = limiter.current.waitMs('self', now);
      setBlock(
        wait > 0
          ? { until: now + wait, tooFrequent: limiter.current.burstReached('self', now) }
          : { until: 0, tooFrequent: false },
      );
      show('self', 'Вы', emoji, now);
      try {
        await publish(encodeReaction(emoji), { reliable: false, topic: REACTION_TOPIC });
      } catch {
        // потеря реакции не критична: ее никто не ждет
      }
      return true;
    },
    [publish, show],
  );

  const receive = useCallback(
    (message: IncomingData) => {
      if (message.topic !== REACTION_TOPIC || !message.from || message.from.isLocal) return;
      const emoji = parseReaction(message.payload);
      if (emoji === null) return;
      const sender = message.from.identity ?? message.from.name ?? '';
      const now = Date.now();
      if (!limiter.current.take(sender, now)) return;
      show(sender, message.from.name || 'Участник', emoji, now);
    },
    [show],
  );

  const expire = useCallback(
    (id: number) => setFloating((current) => current.filter((item) => item.id !== id)),
    [],
  );

  return {
    floating,
    /** Когда снова можно отправить реакцию (`Date.now()`); 0 – можно сейчас */
    blockedUntil: block.until,
    /** Исчерпан лимит «пять за 10 секунд»: подпись «Слишком часто» вместо обычного ожидания */
    tooFrequent: block.tooFrequent,
    send,
    receive,
    expire,
  };
}
