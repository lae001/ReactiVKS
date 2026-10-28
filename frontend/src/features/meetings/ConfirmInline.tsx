import { useEffect, useRef } from 'react';

import { Button } from '@/shared/ui/button';

/**
 * Подтверждение необратимого действия прямо в карточке (светлая тема страниц организатора;
 * в темной комнате – ConfirmDialog). Кнопка подтверждения называет действие тем же словом,
 * что и исходная кнопка; Escape – отмена.
 */
export function ConfirmInline({
  text,
  confirmLabel,
  pending,
  onConfirm,
  onCancel,
}: {
  text: string;
  confirmLabel: string;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  // Фокус – на безопасное действие: случайный Enter не уничтожит встречу
  useEffect(() => cancelRef.current?.focus(), []);

  return (
    <div
      role="alertdialog"
      aria-label={confirmLabel}
      aria-describedby="confirm-inline-text"
      className="flex flex-col gap-3 rounded-lg border border-destructive/40 bg-destructive/5 p-4"
      onKeyDown={(e) => e.key === 'Escape' && onCancel()}
    >
      <p id="confirm-inline-text" className="text-sm">
        {text}
      </p>
      <div className="flex gap-2">
        <Button variant="destructive" size="sm" disabled={pending} onClick={onConfirm}>
          {confirmLabel}
        </Button>
        <Button ref={cancelRef} variant="outline" size="sm" onClick={onCancel}>
          Отмена
        </Button>
      </div>
    </div>
  );
}
