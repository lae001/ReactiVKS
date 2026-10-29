import { type CSSProperties, useEffect } from 'react';

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
  // Склейка (изменился `count`) перезапускает таймер: у «×N» срок жизни продлевается
  useEffect(() => {
    const timer = setTimeout(
      () => onExpire(item.id),
      prefersReducedMotion() ? REDUCED_LIFETIME_MS : FLOAT_LIFETIME_MS,
    );
    return () => clearTimeout(timer);
  }, [item.id, item.count, onExpire]);

  return (
    <span
      data-testid="reaction"
      className="vks-reaction absolute bottom-0 left-0 flex flex-col items-center gap-0.5"
      style={{ '--vks-dx': `${item.dx}px` } as CSSProperties}
    >
      <span className="text-5xl leading-none">
        {item.emoji}
        {item.count > 1 && <span className="ml-1 text-xl font-semibold">×{item.count}</span>}
      </span>
      <span className="max-w-32 truncate rounded-full bg-room/70 px-2 py-0.5 text-xs text-room-foreground">
        {item.name}
      </span>
    </span>
  );
}

/**
 * Эмодзи, всплывающие поверх области видео в одной полосе внизу слева, над панелью управления: поднимаются вверх
 * друг над другом. Не принимает клики и скрыт от скринридеров.
 */
export function ReactionsOverlay({
  items,
  onExpire,
}: {
  items: FloatingReaction[];
  onExpire: (id: number) => void;
}) {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 z-10 overflow-hidden">
      <div className="absolute bottom-3 left-6 w-24">
        {items.map((item) => (
          <Floating key={`${item.id}-${item.count}`} item={item} onExpire={onExpire} />
        ))}
      </div>
    </div>
  );
}
