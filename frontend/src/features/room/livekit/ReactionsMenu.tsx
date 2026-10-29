import { cn } from '@/shared/lib/utils';

import { REACTIONS } from './reactions';

/**
 * Панель из шести реакций (содержимое всплывающей панели «Реакции»; кнопка, открытие и закрытие – в `ControlBar`).
 * Кнопки получают `aria-disabled`, пока действует лимит: они остаются в порядке обхода, и скринридер их читает.
 */
export function ReactionsPanel({
  onPick,
  blocked,
}: {
  onPick: (emoji: string) => void;
  blocked: boolean;
}) {
  return (
    <div className="flex gap-1">
      {REACTIONS.map(({ emoji, label }) => (
        <button
          key={emoji}
          type="button"
          data-reaction
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
  );
}
