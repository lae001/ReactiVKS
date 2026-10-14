import { ArrowLeft, CalendarClock, ScanFace, Users } from 'lucide-react';
import { Link, useParams } from 'react-router';

import { MeetingReport } from '@/features/reports/MeetingReport';
import type { Meeting } from '@/shared/api/types';
import { paths } from '@/shared/config/routes';
import { formatDateTime, formatDuration, formatMeetingWhen } from '@/shared/lib/format';
import { findMeetingById } from '@/shared/mocks/data';
import { getMockReport } from '@/shared/mocks/report';
import { Badge } from '@/shared/ui/badge';
import { Button } from '@/shared/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/ui/card';
import { CopyLinkButton } from '@/shared/ui/copy-link-button';

const STATUS_LABEL: Record<Meeting['status'], string> = {
  active: 'Идет',
  scheduled: 'Запланирована',
  ended: 'Завершена',
  cancelled: 'Отменена',
};

function Param({ icon: Icon, children }: { icon: typeof Users; children: React.ReactNode }) {
  return (
    <li className="flex items-center gap-2 text-sm">
      <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      {children}
    </li>
  );
}

/** Карточка встречи (UC-2, UC-5): параметры и ссылка; у завершенной встречи с анализом – отчет. */
export function MeetingPage() {
  const { id = '' } = useParams();
  const meeting = findMeetingById(id);

  if (!meeting) {
    return (
      <section className="flex max-w-lg flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Встреча не найдена</h1>
        <p className="text-muted-foreground">
          Возможно, ее удалили или ссылка введена с ошибкой. Вернитесь к списку встреч.
        </p>
        <Button asChild className="self-start">
          <Link to={paths.meetings}>К встречам</Link>
        </Button>
      </section>
    );
  }

  const data = meeting.status === 'ended' ? getMockReport(meeting.id) : undefined;
  const duration =
    meeting.started_at && meeting.ended_at
      ? (Date.parse(meeting.ended_at) - Date.parse(meeting.started_at)) / 1000
      : null;

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-3">
        <Link
          to={paths.meetings}
          className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" aria-hidden /> Встречи
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">{meeting.title}</h1>
          <Badge variant={meeting.status === 'ended' ? 'outline' : 'secondary'}>
            {STATUS_LABEL[meeting.status]}
          </Badge>
        </div>
        <ul className="flex flex-wrap gap-x-6 gap-y-2">
          <Param icon={CalendarClock}>
            {formatMeetingWhen(meeting)}
            {duration !== null && ` · ${formatDuration(duration)}`}
          </Param>
          <Param icon={Users}>Участников: {meeting.participants_count}</Param>
          <Param icon={ScanFace}>
            {meeting.analysis_enabled
              ? `Анализ эмоций, ${meeting.analysis_fps} кадра в секунду`
              : 'Без анализа эмоций'}
          </Param>
        </ul>
      </header>

      {meeting.status !== 'ended' && meeting.status !== 'cancelled' && (
        <Card className="max-w-2xl">
          <CardHeader>
            <CardTitle>Ссылка-приглашение</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <p className="rounded-md border bg-muted px-3 py-2 text-sm break-all">
              {meeting.invite_url}
            </p>
            <div className="flex flex-wrap gap-2">
              <CopyLinkButton url={meeting.invite_url} />
              <Button size="sm" asChild>
                <Link to={paths.room(meeting.id)}>
                  {meeting.status === 'active' ? 'Войти во встречу' : 'Начать встречу'}
                </Link>
              </Button>
            </div>
            {meeting.scheduled_at && meeting.status === 'scheduled' && (
              <p className="text-sm text-muted-foreground">
                Начало по плану: {formatDateTime(meeting.scheduled_at)}. Участники смогут войти,
                когда вы начнете встречу.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {meeting.status === 'ended' &&
        (data ? (
          <MeetingReport report={data.report} series={data.series} />
        ) : (
          <p className="max-w-prose rounded-lg border border-dashed p-5 text-sm text-muted-foreground">
            {meeting.analysis_enabled
              ? 'Отчет еще не готов. Он появится здесь, когда закончится обработка.'
              : 'Анализ эмоций в этой встрече был выключен, поэтому отчета нет.'}
          </p>
        ))}
    </div>
  );
}
