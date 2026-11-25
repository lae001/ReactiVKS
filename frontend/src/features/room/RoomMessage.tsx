import type { ReactNode } from 'react';

/** Полноэкранное сообщение в тёмной комнате: загрузка, ошибка, выход, конец встречи. */
export function RoomMessage({
  title,
  text,
  detail,
  action,
  secondary,
}: {
  title: string;
  text: string;
  /** Техническая причина мелким шрифтом: для обращения в поддержку и журнала дефектов */
  detail?: string;
  action: ReactNode;
  /** Вторая кнопка рядом с главной: выход «к встречам» или «к приглашению», чтобы не было тупика */
  secondary?: ReactNode;
}) {
  return (
    <div className="flex min-h-dvh flex-col items-start justify-center gap-4 bg-room px-6 text-room-foreground md:px-16">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="max-w-md text-room-muted">{text}</p>
      {detail && <p className="max-w-md font-mono text-xs text-room-muted">Причина: {detail}</p>}
      {(action || secondary) && (
        <div className="flex flex-wrap gap-3">
          {action}
          {secondary}
        </div>
      )}
    </div>
  );
}
