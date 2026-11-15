import { useEffect, useRef, useState } from 'react';

/** Что нужно от сообщения чата LiveKit (`ReceivedChatMessage`): автор, текст и «свое ли это сообщение». */
export interface IncomingChatMessage {
  id: string;
  message: string;
  from?: { isLocal?: boolean; name?: string } | null;
}

export interface ChatToast {
  id: string;
  author: string;
  text: string;
}

/** Сколько всплывающее уведомление живет и сколько их может быть на экране одновременно. */
export const TOAST_LIFETIME_MS = 4000;
export const MAX_TOASTS = 3;
/** Длина текста в уведомлении: длинное сообщение обрезается, полностью его видно в чате. */
export const TOAST_TEXT_LIMIT = 80;

/** «9+» после девяти: счетчик на кнопке не должен раздвигать панель управления. */
export const unreadBadge = (count: number) => (count > 9 ? '9+' : String(count));

const clip = (text: string) =>
  text.length > TOAST_TEXT_LIMIT ? `${text.slice(0, TOAST_TEXT_LIMIT).trimEnd()}…` : text;

/**
 * Непрочитанные сообщения чата и всплывающие уведомления. Пока панель чата не видна, чужие сообщения
 * копятся в счетчике и показываются уведомлением; свои не считаются; при открытом чате не копится ничего.
 * Сообщения, пришедшие до появления хука, непрочитанными не считаются (история чата живет только во
 * вкладке, ADR-008).
 */
export function useChatNotifications(messages: IncomingChatMessage[], chatVisible: boolean) {
  const [processed, setProcessed] = useState(messages.length);
  const [unread, setUnread] = useState(0);
  const [toasts, setToasts] = useState<ChatToast[]>([]);

  // Новые сообщения разбираются при отрисовке (а не в эффекте): так состояние не отстает на кадр
  if (messages.length !== processed) {
    const fresh = messages.slice(processed).filter((m) => !m.from?.isLocal);
    setProcessed(messages.length);
    if (!chatVisible && fresh.length > 0) {
      setUnread((count) => count + fresh.length);
      setToasts((current) =>
        [
          ...current,
          ...fresh.map((m) => ({
            id: m.id,
            author: m.from?.name || 'Участник',
            text: clip(m.message),
          })),
        ].slice(-MAX_TOASTS),
      );
    }
  }

  return {
    unread,
    toasts,
    /** Чат открыт: все прочитано, уведомления не нужны */
    markRead: () => {
      setUnread(0);
      setToasts([]);
    },
    dismissToast: (id: string) => setToasts((current) => current.filter((t) => t.id !== id)),
  };
}

/** Заголовок вкладки «(3) ReactiVKS» при непрочитанных; при размонтировании комнаты возвращается исходный. */
export function useUnreadTitle(unread: number) {
  const original = useRef<string | null>(null);

  useEffect(() => {
    original.current ??= document.title;
    document.title = unread > 0 ? `(${unreadBadge(unread)}) ${original.current}` : original.current;
  }, [unread]);

  useEffect(
    () => () => {
      if (original.current !== null) document.title = original.current;
    },
    [],
  );
}
