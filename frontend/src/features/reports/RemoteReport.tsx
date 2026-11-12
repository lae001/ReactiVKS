import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/shared/api/client';
import type { Report, SeriesPoint } from '@/shared/api/types';
import { EMOTION_LABELS } from '@/shared/config/emotions';
import { Button } from '@/shared/ui/button';
import { MeetingReport } from './MeetingReport';

export interface ReportSeries {
  resolution: '1s' | '5s' | '30s';
  labels: string[];
  series: { participant_id: string; points: SeriesPoint[] }[];
}

/** Ряды участников сохраняются отдельно: усреднение без количества samples исказило бы результат. */
export function RemoteReport({ meetingId }: { meetingId: string }) {
  const report = useQuery({
    queryKey: ['report', meetingId],
    queryFn: ({ signal }) => apiFetch<Report>(`/api/v1/reports/${meetingId}`, { signal }),
    retry: false,
    refetchInterval: (query) => (query.state.data?.status === 'pending' ? 3000 : false),
  });
  const series = useQuery({
    queryKey: ['report-series', meetingId],
    queryFn: ({ signal }) =>
      apiFetch<ReportSeries>(`/api/v1/reports/${meetingId}/series`, { signal }),
    enabled: report.data?.status === 'ready',
    retry: false,
  });
  if (report.isError)
    return (
      <div role="alert">
        Отчёт недоступен: нет данных, доступа или связи с сервисом.{' '}
        <Button onClick={() => void report.refetch()}>Повторить</Button>
      </div>
    );
  if (!report.data || report.data.status === 'pending')
    return <p role="status">Отчёт готовится…</p>;
  if (report.data.status === 'failed') return <p role="alert">Не удалось сформировать отчёт.</p>;
  if (!report.data.summary || !report.data.summary.participants.some((p) => p.analyzed_seconds > 0))
    return <p>Нет данных анализа для отчёта.</p>;
  if (series.isError)
    return (
      <div role="alert">
        Не удалось загрузить временные ряды.{' '}
        <Button onClick={() => void series.refetch()}>Повторить</Button>
      </div>
    );
  if (!series.data) return <p role="status">Загружаем графики…</p>;
  if (series.data.labels.join() !== EMOTION_LABELS.join())
    return <p role="alert">Формат классов эмоций несовместим.</p>;
  return (
    <div className="flex flex-col gap-6">
      {series.data.series.length === 0 ? (
        <p>Временных рядов нет.</p>
      ) : (
        series.data.series.map((row) => (
          <section key={row.participant_id}>
            <h2>
              {report.data.summary.participants.find((p) => p.participant_id === row.participant_id)
                ?.display_name ?? 'Участник'}
            </h2>
            <MeetingReport
              report={report.data}
              series={{ resolution: series.data.resolution, points: row.points }}
            />
          </section>
        ))
      )}
    </div>
  );
}
