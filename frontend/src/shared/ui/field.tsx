import type { ComponentProps, ReactNode } from 'react';

import { Input } from './input';
import { Label } from './label';

/** Поле формы: подпись, ввод, подсказка и ошибка, связанные через aria. */
export function Field({
  id,
  label,
  error,
  hint,
  ...inputProps
}: { id: string; label: ReactNode; error?: string; hint?: string } & Omit<
  ComponentProps<typeof Input>,
  'id'
>) {
  const describedBy = [error ? `${id}-error` : null, hint ? `${id}-hint` : null]
    .filter(Boolean)
    .join(' ');
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        {...inputProps}
      />
      {hint && !error ? (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** Сообщение об ошибке под формой (не привязанной к полю). */
export function FormError({ children }: { children: ReactNode }) {
  return (
    <p
      role="alert"
      className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
    >
      {children}
    </p>
  );
}
