import { EMOTION_LABELS, emotionColor } from '@/shared/config/emotions';
import type { EmotionDistribution as Distribution } from '@/shared/api/types';
import { formatPercent } from '@/shared/lib/format';
import { EmotionTag } from '@/shared/ui/emotion-icon';

/**
 * Распределение эмоций за встречу: горизонтальные столбцы по убыванию (docs/frontend/emotion-visualization.md, раздел 6).
 * Сделано обычной разметкой, а не SVG: подпись и процент остаются текстом, столбцы – только заливка.
 */
export function EmotionDistribution({ distribution }: { distribution: Distribution }) {
  const rows = [...EMOTION_LABELS].sort((a, b) => distribution[b] - distribution[a]);
  const max = Math.max(...rows.map((e) => distribution[e]), 0.01);

  return (
    <ul className="flex flex-col gap-2.5" aria-label="Распределение эмоций за встречу">
      {rows.map((e) => (
        <li
          key={e}
          className="grid grid-cols-[7.5rem_minmax(0,1fr)_3rem] items-center gap-3 text-sm sm:grid-cols-[9rem_minmax(0,1fr)_3rem]"
        >
          <EmotionTag label={e} surface="line" className="truncate" />
          <span className="h-3 rounded-full bg-muted" aria-hidden>
            <span
              className="block h-full rounded-full"
              style={{
                width: `${(distribution[e] / max) * 100}%`,
                background: emotionColor(e, 'fill'),
              }}
            />
          </span>
          <span className="text-right tabular-nums">{formatPercent(distribution[e])}</span>
        </li>
      ))}
    </ul>
  );
}
