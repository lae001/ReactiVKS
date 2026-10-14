import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  type TooltipContentProps,
  XAxis,
  YAxis,
} from 'recharts';

import type { Marker, Series } from '@/shared/api/types';
import { EMOTION_LABELS, EMOTION_META, emotionColor } from '@/shared/config/emotions';
import { formatDuration, formatPercent } from '@/shared/lib/format';
import { EmotionTag } from '@/shared/ui/emotion-icon';

import { secondsFromStart } from './time';

type Row = { t: number } & Record<(typeof EMOTION_LABELS)[number], number>;

function toRows(series: Series, startedAt: string): Row[] {
  return series.points.flatMap((pt) => {
    if (!pt.p) return [];
    const row = { t: secondsFromStart(pt.ts, startedAt) } as Row;
    EMOTION_LABELS.forEach((e, i) => {
      row[e] = pt.p?.[i] ?? 0;
    });
    return [row];
  });
}

function ChartTooltip({ active, payload, label }: TooltipContentProps) {
  if (!active || !payload?.length) return null;
  const items = [...payload].sort((a, b) => Number(b.value ?? 0) - Number(a.value ?? 0));
  return (
    <div className="rounded-lg border bg-popover p-3 text-xs shadow-md">
      <p className="mb-2 font-medium">{formatDuration(Number(label))} от начала</p>
      <ul className="flex flex-col gap-1">
        {items.map((it) => {
          const key = it.dataKey as (typeof EMOTION_LABELS)[number];
          return (
            <li key={key} className="flex items-center justify-between gap-4">
              <EmotionTag label={key} surface="line" />
              <span className="tabular-nums">{formatPercent(Number(it.value))}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/**
 * Стековая площадь вероятностей эмоций по времени встречи (docs/frontend/emotion-visualization.md, раздел 6):
 * 7 слоев в порядке EMOTION_LABELS, белый разделитель 1 px, отметки моментов – сигнальные линии с номером.
 */
export function EmotionTimeline({
  series,
  markers,
  startedAt,
  durationS,
}: {
  series: Series;
  markers: Marker[];
  startedAt: string;
  durationS: number;
}) {
  const rows = toRows(series, startedAt);
  const description = `График вероятностей эмоций за ${formatDuration(durationS)}. Подробности – в таблице участников и списке отметок.`;

  return (
    <div role="img" aria-label={description} className="h-72 w-full md:h-80">
      <ResponsiveContainer
        width="100%"
        height="100%"
        initialDimension={{ width: 640, height: 320 }}
      >
        <AreaChart
          data={rows}
          stackOffset="expand"
          margin={{ top: 18, right: 12, bottom: 0, left: 0 }}
        >
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis
            dataKey="t"
            type="number"
            domain={[0, durationS]}
            tickFormatter={(v: number) => formatDuration(v)}
            tickCount={6}
            stroke="var(--muted-foreground)"
            fontSize={12}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            stroke="var(--muted-foreground)"
            fontSize={12}
            tickLine={false}
            axisLine={false}
            width={44}
          />
          <Tooltip content={ChartTooltip} />
          {EMOTION_LABELS.map((e) => (
            <Area
              key={e}
              type="monotone"
              dataKey={e}
              name={EMOTION_META[e].title}
              stackId="emotions"
              stroke="var(--card)"
              strokeWidth={1}
              fill={emotionColor(e, 'fill')}
              fillOpacity={1}
              isAnimationActive={false}
            />
          ))}
          {markers.map((m, i) => (
            <ReferenceLine
              key={m.id}
              x={secondsFromStart(m.ts, startedAt)}
              stroke="var(--foreground)"
              strokeWidth={2}
              strokeDasharray="4 3"
              label={{
                value: String(i + 1),
                position: 'top',
                fill: 'var(--foreground)',
                fontSize: 12,
              }}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
