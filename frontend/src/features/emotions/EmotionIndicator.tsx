import type { SnapshotParticipant } from '@/shared/api/types';
import { EMOTION_LABELS, EMOTION_META } from '@/shared/config/emotions';
import { formatPercent } from '@/shared/lib/format';
import { cn } from '@/shared/lib/utils';

import { STATE_LABEL } from './summary';

/**
 * Индикатор на плитке (ui-kit.md, вывод 2): маленькая цветная метка, подпись и процент –
 * плитка собеседника не «окрашивается». Цвет всегда дублируется подписью.
 */
export function EmotionIndicator({
  data,
  className,
}: {
  data: SnapshotParticipant;
  className?: string;
}) {
  const base = cn(
    'inline-flex items-center gap-1.5 rounded-md bg-room/85 px-2 py-1 text-xs',
    className,
  );

  if (data.state !== 'analyzing' || !data.last) {
    const label = data.state === 'analyzing' ? 'Нет данных' : STATE_LABEL[data.state];
    return <span className={cn(base, 'text-room-muted')}>{label}</span>;
  }

  const meta = EMOTION_META[data.last.dominant];
  return (
    <span className={cn(base, 'text-room-foreground')}>
      <span
        className="size-2 rounded-full"
        style={{ background: `var(${meta.cssVar})` }}
        aria-hidden
      />
      {meta.title}
      <span className="text-room-muted">{formatPercent(data.last.confidence)}</span>
    </span>
  );
}

/** Распределение вероятностей одной полосой; текстовая расшифровка – для скринридеров. */
export function ProbabilityBar({ p, className }: { p: number[]; className?: string }) {
  const description = EMOTION_LABELS.map(
    (e, i) => `${EMOTION_META[e].title} ${formatPercent(p[i] ?? 0)}`,
  ).join(', ');

  return (
    <div
      role="img"
      aria-label={`Распределение: ${description}`}
      className={cn('flex h-2 overflow-hidden rounded-full bg-room-border', className)}
    >
      {EMOTION_LABELS.map((e, i) => (
        <span
          key={e}
          style={{ width: `${(p[i] ?? 0) * 100}%`, background: `var(${EMOTION_META[e].cssVar})` }}
        />
      ))}
    </div>
  );
}
