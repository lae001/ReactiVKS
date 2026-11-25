import { useState } from 'react';
import { apiFetch } from '@/shared/api/client';
import type { Marker } from '@/shared/api/types';
import { Button } from '@/shared/ui/button';
import type { EmotionData } from './stream';
import { EmotionIndicator, ProbabilityBar } from './EmotionIndicator';

const states = {
  active: 'Анализ идёт',
  degraded: 'Анализ замедлен',
  unavailable: 'Анализ недоступен',
  off: 'Анализ выключен',
};
export function LiveEmotionPanel({
  meetingId,
  data,
  status,
}: {
  meetingId: string;
  data: EmotionData;
  status: string;
}) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [label, setLabel] = useState('');
  async function mark() {
    if (busy || !label.trim()) return;
    setBusy(true);
    setNotice('');
    try {
      await apiFetch<Marker>(`/api/v1/reports/${meetingId}/markers`, {
        method: 'POST',
        body: { label: label.trim(), ts: null },
      });
      setNotice('Отметка сохранена в отчёте');
      setLabel('');
    } catch {
      setNotice('Не удалось сохранить отметку. Проверьте доступность сервиса и повторите.');
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="flex flex-col gap-4">
      <p role="status">
        {status} · {states[data.analysis]}
      </p>
      {data.participants.length === 0 && <p>Данных участников пока нет.</p>}
      {data.participants.map((p) => {
        const points = (data.history[p.participant_id] ?? []).filter(
          (x) => Date.parse(x.ts) >= Date.now() - 300000,
        );
        return (
          <article key={p.participant_id} className="rounded-lg border border-room-border p-3">
            <h3>{p.display_name}</h3>
            <EmotionIndicator data={p} />
            {p.last && <ProbabilityBar p={p.last.p} />}
            {points.length > 1 && (
              <svg
                viewBox="0 0 300 50"
                role="img"
                aria-label="Уверенность доминирующей эмоции за последние пять минут"
              >
                <polyline
                  fill="none"
                  stroke="var(--signal)"
                  points={points
                    .map(
                      (x) =>
                        `${300 - (Date.now() - Date.parse(x.ts)) / 1000},${50 - x.confidence * 50}`,
                    )
                    .join(' ')}
                />
              </svg>
            )}
          </article>
        );
      })}
      <label>
        Название отметки
        <input
          className="w-full rounded border border-room-border bg-room-surface p-2"
          maxLength={200}
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
      </label>
      <Button variant="room" disabled={busy || !label.trim()} onClick={() => void mark()}>
        Отметить момент
      </Button>
      {notice && <p role="status">{notice}</p>}
      <p className="text-xs text-room-muted">
        Результаты отражают внешнее выражение лица и носят рекомендательный характер.
      </p>
    </section>
  );
}
