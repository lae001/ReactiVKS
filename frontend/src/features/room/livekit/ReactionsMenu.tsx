import { Smile } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { ControlButton } from '../ControlBar';

import { REACTIONS } from './reactions';

/**
 * Кнопка «Реакции» с панелью из шести реакций. Фокус уходит на первую реакцию, Enter и пробел выбирают
 * (это обычные кнопки), Esc закрывает панель и возвращает фокус на кнопку «Реакции».
 */
export function ReactionsMenu({ onPick }: { onPick: (emoji: string) => void }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null);

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
          className="fixed bottom-20 left-1/2 z-30 flex -translate-x-1/2 gap-1 rounded-xl border border-room-border bg-room-surface p-2 text-room-foreground"
        >
          {REACTIONS.map(({ emoji, label }) => (
            <button
              key={emoji}
              type="button"
              data-reaction
              aria-label={`Реакция: ${label.toLowerCase()}`}
              title={label}
              onClick={() => {
                onPick(emoji);
                close();
              }}
              className="grid size-11 place-items-center rounded-lg text-2xl transition-colors hover:bg-room-border focus-visible:bg-room-border focus-visible:outline-2 focus-visible:outline-primary"
            >
              <span aria-hidden>{emoji}</span>
            </button>
          ))}
        </div>
      )}
    </span>
  );
}
