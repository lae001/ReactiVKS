import { useEffect, useRef } from 'react';

import { Button } from '@/shared/ui/button';

/**
 * Подтверждение необратимого действия в комнате. Кнопка подтверждения называет действие
 * тем же словом, что и исходная кнопка (ui-kit.md, раздел 6); Escape – отмена.
 */
export function ConfirmDialog({
  title,
  text,
  confirmLabel,
  onCancel,
  onConfirm,
  busy = false,
  error = null,
  confirmVariant = 'destructive',
}: {
  title: string;
  text: string;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: () => void;
  /** Запрос уже отправлен: подтверждение отключено */
  busy?: boolean;
  /** Сообщение, если запрос не удался; диалог остается открытым для повтора */
  error?: string | null;
  /** Для безопасных действий (например, «Разрешаю анализ») – не красная кнопка */
  confirmVariant?: 'destructive' | 'default';
}) {
  const confirmRef = useRef<HTMLButtonElement>(null);
  useEffect(() => confirmRef.current?.focus(), []);

  return (
    <div
      className="absolute inset-0 z-20 flex items-center justify-center bg-room/70 p-4"
      onKeyDown={(e) => e.key === 'Escape' && onCancel()}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-text"
        className="flex w-full max-w-sm flex-col gap-4 rounded-xl border border-room-border bg-room-surface p-5"
      >
        <h2 id="confirm-title" className="text-lg font-semibold">
          {title}
        </h2>
        <p id="confirm-text" className="text-sm text-room-muted">
          {text}
        </p>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="room" onClick={onCancel}>
            Отмена
          </Button>
          <Button ref={confirmRef} variant={confirmVariant} onClick={onConfirm} disabled={busy}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
