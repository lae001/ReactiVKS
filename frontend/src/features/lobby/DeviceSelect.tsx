import { useId } from 'react';

import type { DeviceOption } from '@/shared/hooks/use-local-media';
import { cn } from '@/shared/lib/utils';
import { Label } from '@/shared/ui/label';

const optionRoom = 'bg-room-surface text-room-foreground';

/** Список устройств одного вида (камера, микрофон, динамик) на нативном <select>. */
export function DeviceSelect({
  label,
  options,
  value,
  onChange,
  disabled,
  emptyText,
  tone = 'light',
}: {
  label: string;
  options: DeviceOption[];
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
  /** Что показать, когда устройств нет */
  emptyText: string;
  /** `room` – тёмная тема комнаты: светлый текст на тёмном фоне (контраст не ниже 4.5:1) */
  tone?: 'light' | 'room';
}) {
  const id = useId();
  const empty = options.length === 0;
  const room = tone === 'room';
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id} className={room ? 'text-room-foreground' : undefined}>
        {label}
      </Label>
      <select
        id={id}
        value={value}
        disabled={disabled || empty}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          'h-9 w-full rounded-md border bg-card px-3 text-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40 disabled:opacity-50',
          // светлый текст на тёмном фоне (#e8eef1 на #121a20 – около 15:1); отключенный список читается (#93a4b0 – около 6,7:1)
          room &&
            'border-room-border bg-room text-room-foreground scheme-dark disabled:text-room-muted disabled:opacity-100',
        )}
      >
        {empty ? (
          <option value="" className={room ? optionRoom : undefined}>
            {emptyText}
          </option>
        ) : (
          options.map((o) => (
            <option key={o.id} value={o.id} className={room ? optionRoom : undefined}>
              {o.label}
            </option>
          ))
        )}
      </select>
    </div>
  );
}
