import type { ReactNode } from 'react';

/** Полноэкранное сообщение в тёмной комнате: загрузка, ошибка, выход, конец встречи. */
export function RoomMessage({
  title,
  text,
  action,
}: {
  title: string;
  text: string;
  action: ReactNode;
}) {
  return (
    <div className="flex min-h-dvh flex-col items-start justify-center gap-4 bg-room px-6 text-room-foreground md:px-16">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="max-w-md text-room-muted">{text}</p>
      {action}
    </div>
  );
}
