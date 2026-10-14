import { Flag } from 'lucide-react';
import { useState } from 'react';

import type { SnapshotParticipant } from '@/shared/api/types';
import { EMOTION_LABELS, EMOTION_META } from '@/shared/config/emotions';
import { formatDuration, formatPercent } from '@/shared/lib/format';
import { Button } from '@/shared/ui/button';
import { EmotionIcon } from '@/shared/ui/emotion-icon';

import { EmotionIndicator, ProbabilityBar } from './EmotionIndicator';
import { summarize } from './summary';

/**
 * Панель эмоций организатора (docs/frontend/README.md, «Панель эмоций»): сводка встречи,
 * карточки участников, отметки моментов. Сейчас – снимок тестовых данных;
 * WebSocket и мини-графики за 5 минут – EMO-90, EMO-91.
 */
export function EmotionPanel({
  participants,
  elapsed,
}: {
  participants: SnapshotParticipant[];
  /** Длительность встречи, с – для отметок моментов */
  elapsed: number;
}) {
  const summary = summarize(participants);
  const [markers, setMarkers] = useState<number[]>([]);

  return (
    <div className="flex flex-col gap-5">
      <section aria-labelledby="summary-title" className="flex flex-col gap-3">
        <h3
          id="summary-title"
          className="text-xs font-medium tracking-wide text-room-muted uppercase"
        >
          Сводка встречи
        </h3>
        {summary ? (
          <>
            <ProbabilityBar p={summary.mean} className="h-3" />
            <ul className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              {EMOTION_LABELS.map((e, i) => (
                <li key={e} className="flex items-center gap-1.5">
                  <EmotionIcon label={e} className="size-3.5" />
                  {EMOTION_META[e].title}
                  <span className="ml-auto text-room-muted">
                    {formatPercent(summary.mean[i] ?? 0)}
                  </span>
                </li>
              ))}
            </ul>
            <p className="text-sm">
              Доля негативных эмоций:{' '}
              <span className="font-semibold">{formatPercent(summary.negativeShare)}</span>
              <span className="text-room-muted"> · анализируется {summary.analyzed}</span>
            </p>
          </>
        ) : (
          <p className="text-sm text-room-muted">Пока некого анализировать.</p>
        )}
      </section>

      <section aria-labelledby="people-title" className="flex flex-col gap-2">
        <h3
          id="people-title"
          className="text-xs font-medium tracking-wide text-room-muted uppercase"
        >
          Участники
        </h3>
        <ul className="flex flex-col gap-2">
          {participants.map((p) => (
            <li
              key={p.participant_id}
              className="flex flex-col gap-2 rounded-lg border border-room-border bg-room-surface p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium">{p.display_name}</span>
                <EmotionIndicator data={p} className="shrink-0 bg-transparent px-0" />
              </div>
              {p.state === 'analyzing' && p.last && <ProbabilityBar p={p.last.p} />}
            </li>
          ))}
        </ul>
      </section>

      <section className="flex flex-col gap-2">
        <Button
          variant="room"
          className="self-start"
          onClick={() => setMarkers((m) => [...m, elapsed])}
        >
          <Flag aria-hidden />
          Отметить момент
        </Button>
        {markers.length > 0 && (
          <p className="text-xs text-room-muted" aria-live="polite">
            Отмечено для отчета: {markers.map(formatDuration).join(', ')}
          </p>
        )}
      </section>

      <p className="rounded-md border border-room-border p-3 text-xs leading-relaxed text-room-muted">
        Результаты отражают внешнее выражение лица и носят рекомендательный характер. Это не оценка
        личности.
      </p>
    </div>
  );
}
