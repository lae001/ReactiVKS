import { Smile } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { cn } from '@/shared/lib/utils';

import { ControlButton } from '../ControlBar';

import { REACTIONS } from './reactions';

/**
 * Кнопка «Реакции» с панелью из шести реакций. Фокус уходит на первую реакцию, Enter и пробел выбирают
 * (это обычные кнопки), Esc закрывает панель и возвращает фокус на кнопку «Реакции».
 */
export function ReactionsMenu({
  onPick,
  blockedUntil = 0,
}: {
  onPick: (emoji: string) => void;
  /** Когда снова можно отправить реакцию (Date.now()); 0 – можно сейчас */
  blockedUntil?: number;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null);
  const now = useNow(blockedUntil);
  const waitSeconds = Math.min(10, Math.max(0, Math.ceil((blockedUntil - now) / 1000)));
  const blocked = waitSeconds > 0;

  useEffect(() => {
    if (open) root.current?.querySelector<HTMLButtonElement>('[data-reaction]')?.focus();
  }, [open]);

  function close() {
    setOpen(false);
    root.current?.querySelector<HTMLButtonElement>('button[aria-haspopup]')?.focus();
  }

  return (
    <span
      ref={root}
      className="relative"
      onKeyDown={(e) => {
        if (e.key === 'Escape' && open) {
          e.stopPropagation();
          close();
        }
      }}
    >
      <ControlButton
        icon={Smile}
        label="Реакции"
        onClick={() => setOpen((value) => !value)}
        pressed={open}
        tone={open ? 'active' : 'default'}
        popup
      />
      {open && (
        // fixed: панель управления прокручивается по горизонтали, и absolute-панель обрезалась бы ее краем
        <div
          role="group"
          aria-label="Выбор реакции"
          className="fixed bottom-20 left-1/2 z-30 flex -translate-x-1/2 flex-col gap-2 rounded-xl border border-room-border bg-room-surface p-2 text-room-foreground"
        >
          <div className="flex gap-1">
            {REACTIONS.map(({ emoji, label }) => (
              <button
                key={emoji}
                type="button"
                data-reaction
                // aria-disabled, а не disabled: кнопки остаются в порядке обхода, и скринридер их читает
                aria-disabled={blocked || undefined}
                aria-label={`Реакция: ${label.toLowerCase()}`}
                title={label}
                onClick={() => {
                  if (!blocked) onPick(emoji);
                }}
                className={cn(
                  'grid size-11 place-items-center rounded-lg text-2xl transition-colors hover:bg-room-border focus-visible:bg-room-border focus-visible:outline-2 focus-visible:outline-primary',
                  blocked && 'opacity-40 hover:bg-transparent',
                )}
              >
                <span aria-hidden>{emoji}</span>
              </button>
            ))}
          </div>
          {/* Область объявления есть всегда: скринридер зачитывает текст, когда он появляется */}
          <p aria-live="polite" className="px-1 text-center text-xs text-room-muted">
            {blocked ? `Слишком часто. Подождите ещё ${waitSeconds} с` : ''}
          </p>
        </div>
      )}
    </span>
  );
}

/** Текущее время, пока лимит не освободится: раз в 250 мс, чтобы «Подождите ещё N с» убывало. */
function useNow(blockedUntil: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (blockedUntil <= Date.now()) return;
    const timer = setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (current >= blockedUntil) clearInterval(timer);
    }, 250);
    return () => clearInterval(timer);
  }, [blockedUntil]);
  return now;
}
