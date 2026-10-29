import { useEffect } from 'react';

import type { FloatingReaction } from './reactions';

/** Сколько живет всплывшая реакция; без движения (prefers-reduced-motion) – короткий показ. */
export const FLOAT_LIFETIME_MS = 2800;
export const REDUCED_LIFETIME_MS = 1200;

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false;
}

function Floating({ item, onExpire }: { item: FloatingReaction; onExpire: (id: number) => void }) {
  useEffect(() => {
    const timer = setTimeout(
      () => onExpire(item.id),
      prefersReducedMotion() ? REDUCED_LIFETIME_MS : FLOAT_LIFETIME_MS,
    );
    return () => clearTimeout(timer);
  }, [item.id, onExpire]);

  return (
    <span
      data-testid="reaction"
      className="vks-reaction absolute bottom-4 flex -translate-x-1/2 flex-col items-center gap-0.5"
      style={{ left: `${item.left}%` }}
    >
      <span className="text-5xl leading-none">{item.emoji}</span>
      <span className="max-w-32 truncate rounded-full bg-room/70 px-2 py-0.5 text-xs text-room-foreground">
        {item.name}
      </span>
    </span>
  );
}

/** Эмодзи, всплывающие поверх области видео. Не принимает клики и скрыт от скринридеров. */
export function ReactionsOverlay({
  items,
  onExpire,
}: {
  items: FloatingReaction[];
  onExpire: (id: number) => void;
}) {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 z-10 overflow-hidden">
      {items.map((item) => (
        <Floating key={item.id} item={item} onExpire={onExpire} />
      ))}
    </div>
  );
}
