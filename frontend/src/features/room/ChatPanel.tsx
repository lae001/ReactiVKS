import { Send } from 'lucide-react';
import { type FormEvent, useState } from 'react';

import { Button } from '@/shared/ui/button';

export interface ChatMessage {
  id: string;
  author: string;
  text: string;
  /** Время от начала встречи, «мм:сс» */
  at: string;
  /** Системная строка о реакции участника («Анна: 👍»): показывается иначе, чем сообщение */
  kind?: 'reaction';
}

/**
 * Вкладка «Чат». С LiveKit – компонент чата на текстовых потоках (тема `lk.chat`, ADR-008);
 * история хранится только в памяти вкладки.
 */
export function ChatPanel({
  messages,
  onSend,
}: {
  messages: ChatMessage[];
  onSend: (text: string) => void;
}) {
  const [text, setText] = useState('');

  function submit(e: FormEvent) {
    e.preventDefault();
    const value = text.trim();
    if (!value) return;
    onSend(value);
    setText('');
  }

  return (
    <div className="flex h-full flex-col gap-3">
      <ol className="flex flex-1 flex-col gap-3" aria-live="polite">
        {messages.map((m) =>
          m.kind === 'reaction' ? (
            <li key={m.id} className="text-xs text-room-muted italic">
              {m.author}: <span aria-label="реакция">{m.text}</span>
            </li>
          ) : (
            <li key={m.id} className="flex flex-col gap-0.5 text-sm">
              <span className="text-xs text-room-muted">
                {m.author} · {m.at}
              </span>
              <span className="break-words">{m.text}</span>
            </li>
          ),
        )}
      </ol>
      <p className="text-xs text-room-muted">Сообщения не сохраняются после встречи.</p>
      <form onSubmit={submit} className="flex gap-2">
        <label htmlFor="chat-input" className="sr-only">
          Сообщение
        </label>
        <input
          id="chat-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Сообщение всем"
          autoComplete="off"
          className="h-9 min-w-0 flex-1 rounded-md border border-room-border bg-room-surface px-3 text-sm outline-none placeholder:text-room-muted focus-visible:border-primary"
        />
        <Button type="submit" size="icon" aria-label="Отправить">
          <Send />
        </Button>
      </form>
    </div>
  );
}
