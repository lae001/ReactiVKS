import { ArrowLeft, CalendarClock, LoaderCircle, ScanFace, Users } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';

import { ConfirmInline } from '@/features/meetings/ConfirmInline';
import { meetingErrorMessage } from '@/features/meetings/errors';
import { MeetingEditForm } from '@/features/meetings/MeetingEditForm';
import { useDeleteMeeting, useEndMeeting, useMeeting } from '@/features/meetings/queries';
import { StartMeetingButton } from '@/features/meetings/StartMeetingButton';
import { MeetingReport } from '@/features/reports/MeetingReport';
import type { Meeting } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';
import { paths } from '@/shared/config/routes';
import { formatDateTime, formatDuration, formatMeetingWhen } from '@/shared/lib/format';
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

type Confirm = 'delete' | 'end' | null;

/** Карточка встречи (UC-2, UC-5): ссылка, правка, удаление, начало и завершение; у завершенной – отчет. */
export function MeetingPage() {
  const { id = '' } = useParams();
  const query = useMeeting(id);

  if (query.isPending) {
    return (
      <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" aria-hidden /> Загружаем встречу…
      </p>
    );
  }

  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.code === 'not_found';
    return (
      <section className="flex max-w-lg flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">
          {notFound ? 'Встреча не найдена' : 'Не удалось загрузить встречу'}
        </h1>
        <p className="text-muted-foreground">
          {notFound
            ? 'Встреча не найдена или у вас нет к ней доступа. Вернитесь к списку встреч.'
            : meetingErrorMessage(query.error, 'загрузить встречу')}
        </p>
        <div className="flex gap-2">
          <Button asChild>
            <Link to={paths.meetings}>К встречам</Link>
          </Button>
          {!notFound && (
            <Button variant="outline" onClick={() => void query.refetch()}>
              Повторить
            </Button>
          )}
        </div>
      </section>
    );
  }

  return <MeetingDetails meeting={query.data} />;
}

function MeetingDetails({ meeting }: { meeting: Meeting }) {
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState<Confirm>(null);
  const end = useEndMeeting(meeting.id);
  const remove = useDeleteMeeting(meeting.id);
  const open = meeting.status === 'active' || meeting.status === 'scheduled';

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

      {open && (
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
              {meeting.status === 'active' ? (
                <Button size="sm" asChild>
                  <Link to={paths.room(meeting.id)}>Войти во встречу</Link>
                </Button>
              ) : (
                <StartMeetingButton meeting={meeting} />
              )}
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

      <section aria-label="Управление встречей" className="flex max-w-2xl flex-col gap-3">
        {editing ? (
          <Card>
            <CardHeader>
              <CardTitle>Изменить встречу</CardTitle>
            </CardHeader>
            <CardContent>
              <MeetingEditForm meeting={meeting} onDone={() => setEditing(false)} />
            </CardContent>
          </Card>
        ) : (
          <div className="flex flex-wrap gap-2">
            {meeting.status !== 'cancelled' && (
              <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                Изменить
              </Button>
            )}
            {meeting.status === 'active' && (
              <Button variant="outline" size="sm" onClick={() => setConfirm('end')}>
                Завершить встречу
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => setConfirm('delete')}>
              Удалить
            </Button>
          </div>
        )}
        {confirm === 'end' && (
          <ConfirmInline
            text="Встреча закончится для всех участников. Это действие нельзя отменить."
            confirmLabel="Завершить встречу"
            pending={end.isPending}
            onCancel={() => setConfirm(null)}
            onConfirm={() => end.mutate(undefined, { onSettled: () => setConfirm(null) })}
          />
        )}
        {confirm === 'delete' && (
          <ConfirmInline
            text={`Удалить встречу «${meeting.title}»? ${
              meeting.status === 'ended'
                ? 'Вместе с ней удалится отчет.'
                : 'Ссылка-приглашение перестанет работать.'
            } Это действие нельзя отменить.`}
            confirmLabel="Удалить"
            pending={remove.isPending}
            onCancel={() => setConfirm(null)}
            onConfirm={() =>
              remove.mutate(undefined, {
                onSuccess: () => navigate(paths.meetings),
                onError: () => setConfirm(null),
              })
            }
          />
        )}
        {(end.isError || remove.isError) && (
          <p role="alert" className="text-sm text-destructive">
            {meetingErrorMessage(end.error ?? remove.error, 'выполнить действие')}
          </p>
        )}
      </section>

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
