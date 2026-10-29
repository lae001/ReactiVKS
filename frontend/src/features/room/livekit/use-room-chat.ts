import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  CHAT_SYNC_TOPIC,
  chooseResponder,
  createRequestLimiter,
  encodeHistory,
  encodeRequest,
  loadChat,
  MAX_REPLY_DELAY_MS,
  mergeMessages,
  parseSync,
  REQUESTER_QUIET_MS,
  saveChat,
  type StoredMessage,
} from './chat-history';
import type { IncomingData, PublishData } from './reactions';

/** Сообщение чата LiveKit (`ReceivedChatMessage`) в том, что нужно истории. */
export interface LiveChatMessage {
  id: string;
  message: string;
  timestamp: number;
  from?: { identity?: string; name?: string; isLocal?: boolean } | null;
}

/**
 * Чат со своей историей поверх `useChat`: сообщения из LiveKit, сохраненные во вкладке (переживают обновление
 * страницы) и полученные от других участников при входе. Историческая пачка в счетчик непрочитанных и в
 * уведомления не попадает: они считаются по живому потоку `useChat`. Реакции в историю не входят.
 */
export function useRoomChat({
  meetingId,
  live,
  selfIdentity,
  humans,
  connected,
  publish,
}: {
  meetingId: string;
  live: LiveChatMessage[];
  selfIdentity: string;
  /** identity людей в комнате (без служебных участников) */
  humans: string[];
  connected: boolean;
  publish: PublishData;
}) {
  const [stored] = useState(() => loadChat(meetingId));
  const [received, setReceived] = useState<StoredMessage[]>([]);

  const liveMessages = useMemo<StoredMessage[]>(
    () =>
      live.flatMap((m) =>
        m.from?.identity && m.message
          ? [
              {
                id: m.id,
                from: m.from.identity,
                name: m.from.name || 'Участник',
                text: m.message.slice(0, 2000),
                at: m.timestamp,
              },
            ]
          : [],
      ),
    [live],
  );
  const messages = useMemo(
    () => mergeMessages(stored, received, liveMessages),
    [stored, received, liveMessages],
  );

  // Хранилище вкладки обновляется при каждом изменении (не состояние: setState здесь не нужен)
  useEffect(() => {
    saveChat(meetingId, messages);
  }, [meetingId, messages]);

  // Свежие значения для обработчиков, которые живут дольше одного рендера
  const latest = useRef({ messages, humans, selfIdentity, publish });
  useEffect(() => {
    latest.current = { messages, humans, selfIdentity, publish };
  });

  const requestLimiter = useRef(createRequestLimiter());
  /** Когда участник последний раз запросил историю: от только что вошедшего историю не принимаем */
  const requestedAt = useRef(new Map<string, number>());
  /** Когда последний раз пришел чужой ответ: ожидающий свой ответ в этом случае не отправляется */
  const lastHistoryAt = useRef(0);

  // При входе в комнату запрашиваем историю у тех, кто в ней уже есть
  const requested = useRef(false);
  useEffect(() => {
    if (!connected || requested.current) return;
    requested.current = true;
    void latest.current
      .publish(encodeRequest(), { reliable: true, topic: CHAT_SYNC_TOPIC })
      .catch(() => undefined);
  }, [connected]);

  const receive = useCallback((message: IncomingData) => {
    if (message.topic !== CHAT_SYNC_TOPIC || !message.from || message.from.isLocal) return;
    const sender = message.from.identity;
    if (!sender) return;
    const sync = parseSync(message.payload);
    if (sync === null) return;
    const now = Date.now();

    if (sync.type === 'history_request') {
      if (!requestLimiter.current(sender, now)) return;
      requestedAt.current.set(sender, now);
      const { humans: people, selfIdentity: self, messages: have, publish: send } = latest.current;
      // отвечает один: наименьшая identity среди остальных (не считая запросившего)
      if (chooseResponder([...new Set([...people, self])], sender) !== self) return;
      const asked = now;
      setTimeout(() => {
        // уже ответил другой – свой ответ не нужен
        if (lastHistoryAt.current >= asked) return;
        for (const chunk of encodeHistory(
          latest.current.messages.length > 0 ? latest.current.messages : have,
        )) {
          void send(chunk, { reliable: true, topic: CHAT_SYNC_TOPIC }).catch(() => undefined);
        }
      }, Math.random() * MAX_REPLY_DELAY_MS);
      return;
    }

    // history: не принимаем от того, кто сам только что запросил историю (своей у него еще нет)
    const asked = requestedAt.current.get(sender);
    if (asked !== undefined && now - asked < REQUESTER_QUIET_MS) return;
    lastHistoryAt.current = now;
    if (sync.messages.length > 0) setReceived((current) => mergeMessages(current, sync.messages));
  }, []);

  return { messages, receive };
}
