import { useEffect } from 'react';

import { type ChatToast, TOAST_LIFETIME_MS } from './chat-notifications';

function Toast({
  toast,
  onOpen,
  onExpire,
}: {
  toast: ChatToast;
  onOpen: () => void;
  onExpire: (id: string) => void;
}) {
  useEffect(() => {
    const timer = setTimeout(() => onExpire(toast.id), TOAST_LIFETIME_MS);
    return () => clearTimeout(timer);
  }, [toast.id, onExpire]);

  return (
    <button
      type="button"
      onClick={onOpen}
      title="Открыть чат"
      className="pointer-events-auto max-w-72 truncate rounded-lg border border-room-border bg-room-surface px-3 py-2 text-left text-sm text-room-foreground shadow-lg transition-colors hover:bg-room-border"
    >
      <span className="font-medium">{toast.author}:</span> {toast.text}
    </button>
  );
}

/** Уведомления о новых сообщениях в углу области видео; клик открывает чат. */
export function ChatToasts({
  toasts,
  onOpen,
  onExpire,
}: {
  toasts: ChatToast[];
  onOpen: () => void;
  onExpire: (id: string) => void;
}) {
  return (
    <div
      role="status"
      className="pointer-events-none absolute top-3 left-3 z-20 flex flex-col items-start gap-2"
    >
      {toasts.map((toast) => (
        <Toast key={toast.id} toast={toast} onOpen={onOpen} onExpire={onExpire} />
      ))}
    </div>
  );
}
