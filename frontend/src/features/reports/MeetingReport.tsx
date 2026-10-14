import { Download, FileText } from 'lucide-react';

import { EmotionLegend } from '@/features/reports/EmotionLegend';
import type { Report, Series } from '@/shared/api/types';
import { EMOTION_LABELS } from '@/shared/config/emotions';
import { formatDateTime, formatDuration, formatPercent } from '@/shared/lib/format';
import { Button } from '@/shared/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card';
import { EmotionTag } from '@/shared/ui/emotion-icon';

import { EmotionDistribution } from './EmotionDistribution';
import { EmotionTimeline } from './EmotionTimeline';
import { ParticipantsTable } from './ParticipantsTable';
import { secondsFromStart } from './time';

function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border bg-card p-4">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-2xl font-semibold tracking-tight">{value}</dd>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

/** Отчет завершенной встречи (UC-5): сводка, график по времени, распределение, отметки, участники. */
export function MeetingReport({ report, series }: { report: Report; series: Series }) {
  const { overall, participants } = report.summary;
  const top = [...EMOTION_LABELS].sort(
    (a, b) => overall.distribution[b] - overall.distribution[a],
  )[0];
  const analyzed = participants.filter((p) => p.distribution).length;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">Отчет по эмоциям</h2>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" disabled title="Экспорт появится в спринте 5">
            <Download aria-hidden />
            CSV
          </Button>
          <Button variant="outline" size="sm" disabled title="Экспорт появится в спринте 5">
            <FileText aria-hidden />
            PDF
          </Button>
        </div>
      </div>

      <dl className="grid gap-3 sm:grid-cols-3">
        <Stat
          label="Чаще всего"
          value={top ? <EmotionTag label={top} surface="line" /> : '—'}
          hint={top ? formatPercent(overall.distribution[top]) + ' времени встречи' : undefined}
        />
        <Stat
          label="Доля негативных эмоций"
          value={formatPercent(overall.negative_share)}
          hint="Гнев, отвращение, страх, грусть"
        />
        <Stat
          label="Проанализировано"
          value={`${analyzed} из ${participants.length}`}
          hint={`Лицо в кадре ${formatPercent(overall.face_detected_ratio)} времени`}
        />
      </dl>

      <Card>
        <CardHeader>
          <CardTitle>Эмоции по ходу встречи</CardTitle>
          <CardDescription>
            Доли вероятностей всех участников, давших согласие. Цифры у линий — отметки моментов.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <EmotionTimeline
            series={series}
            markers={report.markers}
            startedAt={report.meeting.started_at}
            durationS={report.meeting.duration_s}
          />
          <EmotionLegend />
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Распределение за встречу</CardTitle>
            <CardDescription>Как часто встречался каждый класс.</CardDescription>
          </CardHeader>
          <CardContent>
            <EmotionDistribution distribution={overall.distribution} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Отмеченные моменты</CardTitle>
            <CardDescription>
              Ручные отметки и резкие сдвиги, найденные автоматически.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="flex flex-col gap-3">
              {report.markers.map((m, i) => (
                <li key={m.id} className="flex items-start gap-3 text-sm">
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-signal text-xs font-semibold text-signal-foreground">
                    {i + 1}
                  </span>
                  <span className="flex flex-col">
                    <span className="font-medium">{m.label}</span>
                    <span className="text-muted-foreground">
                      {formatDuration(secondsFromStart(m.ts, report.meeting.started_at))} от начала
                      · {m.kind === 'manual' ? 'отметил организатор' : 'найдено автоматически'}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      </div>

      <section className="flex flex-col gap-3" aria-labelledby="participants-title">
        <h3 id="participants-title" className="text-lg font-semibold">
          Участники
        </h3>
        <ParticipantsTable participants={participants} />
      </section>

      <p className="max-w-prose text-sm text-muted-foreground">
        {report.disclaimer} Встреча: {formatDateTime(report.meeting.started_at)}, длительность{' '}
        {formatDuration(report.meeting.duration_s)}. Модель: {report.model_version}.
      </p>
    </div>
  );
}
