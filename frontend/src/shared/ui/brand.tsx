import { EMOTION_META, EMOTION_SPECTRUM } from '@/shared/config/emotions';
import { cn } from '@/shared/lib/utils';

/** Полоса из 7 цветов эмоций – фирменный элемент; показывает, что анализирует Система. */
export function EmotionSpectrum({ className }: { className?: string }) {
  return (
    <div className={cn('flex h-1 overflow-hidden rounded-full', className)} aria-hidden>
      {EMOTION_SPECTRUM.map((e) => (
        <span key={e} className="flex-1" style={{ background: `var(${EMOTION_META[e].cssVar})` }} />
      ))}
    </div>
  );
}

export function Wordmark({
  className,
  tone = 'ink',
}: {
  className?: string;
  tone?: 'ink' | 'light';
}) {
  return (
    <span className={cn('inline-flex w-fit flex-col gap-1', className)}>
      <span
        className={cn(
          'text-lg leading-none font-semibold tracking-tight',
          tone === 'light' ? 'text-room-foreground' : 'text-foreground',
        )}
      >
        React<span className="font-normal">ВКС</span>
      </span>
      <EmotionSpectrum className="h-[3px] w-full" />
    </span>
  );
}
