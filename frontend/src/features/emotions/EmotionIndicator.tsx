import type { SnapshotParticipant } from '@/shared/api/types';
import { EMOTION_LABELS, EMOTION_META, emotionColor } from '@/shared/config/emotions';
import { formatPercent } from '@/shared/lib/format';
import { cn } from '@/shared/lib/utils';
import { EmotionIcon } from '@/shared/ui/emotion-icon';

import { STATE_LABEL } from './summary';

/**
 * Индикатор на плитке (ui-kit.md, вывод 2): маленький цветной значок, подпись и процент –
 * плитка собеседника не «окрашивается». Цвет всегда дублируется формой значка и подписью.
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
      <EmotionIcon label={data.last.dominant} className="size-3.5" />
      {meta.title}
      <span className="text-room-muted">{formatPercent(data.last.confidence)}</span>
    </span>
  );
}

/** Распределение вероятностей одной полосой; текстовая расшифровка – для скринридеров. */
export function ProbabilityBar({
  p,
  className,
  surface = 'dark',
}: {
  p: number[];
  className?: string;
  /** Фон под полосой: комната (dark) или светлая страница (fill) */
  surface?: 'dark' | 'fill';
}) {
  const description = EMOTION_LABELS.map(
    (e, i) => `${EMOTION_META[e].title} ${formatPercent(p[i] ?? 0)}`,
  ).join(', ');

  return (
    <div
      role="img"
      aria-label={`Распределение: ${description}`}
      className={cn(
        'flex h-2 overflow-hidden rounded-full',
        // на светлом фоне сегменты разделяет белая линия в 1 px (emotion-visualization.md, раздел 4)
        surface === 'dark' ? 'bg-room-border' : 'gap-px bg-card',
        className,
      )}
    >
      {EMOTION_LABELS.map((e, i) => (
        <span
          key={e}
          style={{ width: `${(p[i] ?? 0) * 100}%`, background: emotionColor(e, surface) }}
        />
      ))}
    </div>
  );
}
