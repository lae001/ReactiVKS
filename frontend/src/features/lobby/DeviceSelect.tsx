import { useId } from 'react';

import type { DeviceOption } from '@/shared/hooks/use-local-media';
import { Label } from '@/shared/ui/label';

/** Список устройств одного вида (камера, микрофон, динамик) на нативном <select>. */
export function DeviceSelect({
  label,
  options,
  value,
  onChange,
  disabled,
  emptyText,
}: {
  label: string;
  options: DeviceOption[];
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
  /** Что показать, когда устройств нет */
  emptyText: string;
}) {
  const id = useId();
  const empty = options.length === 0;
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        value={value}
        disabled={disabled || empty}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full rounded-md border bg-card px-3 text-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40 disabled:opacity-50"
      >
        {empty ? (
          <option value="">{emptyText}</option>
        ) : (
          options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))
        )}
      </select>
    </div>
  );
}
