import type { ReactNode } from 'react';

import { cn } from '@/shared/lib/utils';

/**
 * Заглушка страницы на время каркаса (EMO-19): показывает, что будет на экране
 * и в каких задачах это реализуется. Удаляется по мере реализации страниц.
 */
export function PageStub({
  title,
  lead,
  planned,
  tasks,
  children,
  className,
}: {
  title: string;
  lead: string;
  planned: string[];
  tasks: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn('flex max-w-2xl flex-col gap-6', className)}>
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">{title}</h1>
        <p className="text-base text-muted-foreground">{lead}</p>
      </header>
      {children}
      <div className="rounded-lg border border-dashed bg-card/60 p-5">
        <p className="mb-3 text-sm font-medium">Будет на этом экране</p>
        <ul className="flex list-disc flex-col gap-1.5 pl-5 text-sm text-muted-foreground">
          {planned.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-muted-foreground">Реализация: {tasks}</p>
      </div>
    </section>
  );
}
