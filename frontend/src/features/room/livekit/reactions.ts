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

/** Не чаще одной реакции в 300 мс от одного участника: при отправке и при приеме. */
export const REACTION_INTERVAL_MS = 300;
/** Одновременно на экране не больше 15 эмодзи, лишние не показываются. */
export const MAX_FLOATING = 15;
/** Сколько записей реакций хранить для ленты в чате. */
const LOG_LIMIT = 200;

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
  emoji: string;
  /** Подпись: имя отправителя или «Вы» */
  name: string;
  /** Горизонтальное положение в процентах ширины области видео */
  left: number;
}

export interface ReactionLogEntry {
  id: number;
  emoji: string;
  name: string;
  at: number;
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
 * Реакции: отправка по каналу данных (без гарантии доставки), прием с проверкой, всплывающие эмодзи и лента для
 * чата. Чужие данные не доверенные: тема, формат и эмодзи проверяются, имя берется только из участника LiveKit.
 */
export function useReactions(publish: PublishData) {
  const [floating, setFloating] = useState<FloatingReaction[]>([]);
  const [log, setLog] = useState<ReactionLogEntry[]>([]);
  const lastSent = useRef(0);
  const lastFrom = useRef(new Map<string, number>());
  const sequence = useRef(0);

  const show = useCallback((name: string, emoji: string) => {
    sequence.current += 1;
    const id = sequence.current;
    setFloating((current) =>
      current.length >= MAX_FLOATING
        ? current
        : [...current, { id, emoji, name, left: 8 + Math.random() * 78 }],
    );
    setLog((current) => [...current.slice(-(LOG_LIMIT - 1)), { id, emoji, name, at: Date.now() }]);
  }, []);

  const send = useCallback(
    async (emoji: string): Promise<boolean> => {
      if (!ALLOWED.has(emoji)) return false;
      const now = Date.now();
      if (now - lastSent.current < REACTION_INTERVAL_MS) return false;
      lastSent.current = now;
      show('Вы', emoji);
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
      if (now - (lastFrom.current.get(sender) ?? 0) < REACTION_INTERVAL_MS) return;
      lastFrom.current.set(sender, now);
      show(message.from.name || 'Участник', emoji);
    },
    [show],
  );

  const expire = useCallback(
    (id: number) => setFloating((current) => current.filter((item) => item.id !== id)),
    [],
  );

  return { floating, log, send, receive, expire };
}
