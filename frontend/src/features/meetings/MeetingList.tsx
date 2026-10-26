import { ScanFace, Users } from 'lucide-react';
import { Link } from 'react-router';

import type { Meeting, MeetingStatus } from '@/shared/api/types';
import { paths } from '@/shared/config/routes';
import { formatMeetingWhen } from '@/shared/lib/format';
import { Badge } from '@/shared/ui/badge';
import { Button } from '@/shared/ui/button';
import { CopyLinkButton } from '@/shared/ui/copy-link-button';

const STATUS: Record<
  MeetingStatus,
  { label: string; variant: 'default' | 'secondary' | 'outline' }
> = {
  active: { label: 'Идет', variant: 'default' },
  scheduled: { label: 'Запланирована', variant: 'secondary' },
  ended: { label: 'Завершена', variant: 'outline' },
  cancelled: { label: 'Отменена', variant: 'outline' },
};

function MeetingActions({ meeting }: { meeting: Meeting }) {
  switch (meeting.status) {
    case 'active':
      return (
        <>
          <CopyLinkButton url={meeting.invite_url} />
          <Button size="sm" asChild>
            <Link to={paths.room(meeting.id)}>Войти</Link>
          </Button>
        </>
      );
    case 'scheduled':
      return (
        <>
          <CopyLinkButton url={meeting.invite_url} />
          <Button size="sm" asChild>
            <Link to={paths.room(meeting.id)}>Начать встречу</Link>
          </Button>
        </>
      );
    default:
      return (
        <Button variant="outline" size="sm" asChild>
          <Link to={paths.meeting(meeting.id)}>
            {meeting.analysis_enabled ? 'Отчет' : 'Карточка'}
          </Link>
        </Button>
      );
  }
}

/** Список встреч на главной: строка на встречу, действия по статусу. */
export function MeetingList({ meetings, empty }: { meetings: Meeting[]; empty: string }) {
  if (meetings.length === 0) {
    return (
      <p className="rounded-lg border border-dashed p-5 text-sm text-muted-foreground">{empty}</p>
    );
  }

  return (
    <ul className="divide-y rounded-xl border bg-card">
      {meetings.map((m) => (
        <li
          key={m.id}
          className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <div className="flex min-w-0 flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <Link
                to={paths.meeting(m.id)}
                className="truncate font-medium hover:text-primary hover:underline"
              >
                {m.title}
              </Link>
              <Badge variant={STATUS[m.status].variant}>{STATUS[m.status].label}</Badge>
            </div>
            <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
              <span>{formatMeetingWhen(m)}</span>
              {m.participants_count > 0 && (
                <span className="inline-flex items-center gap-1">
                  <Users className="size-3.5" aria-hidden />
                  {m.participants_count}
                </span>
              )}
              <span className="inline-flex items-center gap-1">
                <ScanFace className="size-3.5" aria-hidden />
                {m.analysis_enabled ? 'С анализом эмоций' : 'Без анализа'}
              </span>
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <MeetingActions meeting={m} />
          </div>
        </li>
      ))}
    </ul>
  );
}
