import { ScanFace, Users } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';

import type { Meeting, MeetingStatus } from '@/shared/api/meetings';
import { paths } from '@/shared/config/routes';
import { formatMeetingWhen } from '@/shared/lib/format';
import { Badge } from '@/shared/ui/badge';
import { Button } from '@/shared/ui/button';
import { CopyLinkButton } from '@/shared/ui/copy-link-button';

import { ConfirmInline } from './ConfirmInline';
import { meetingErrorMessage } from './errors';
import { useEndMeeting } from './queries';
import { StartMeetingButton } from './StartMeetingButton';

const STATUS: Record<
  MeetingStatus,
  { label: string; variant: 'default' | 'secondary' | 'outline' }
> = {
  active: { label: 'Идет', variant: 'default' },
  scheduled: { label: 'Запланирована', variant: 'secondary' },
  ended: { label: 'Завершена', variant: 'outline' },
  cancelled: { label: 'Отменена', variant: 'outline' },
};

function MeetingActions({ meeting, onEnd }: { meeting: Meeting; onEnd: () => void }) {
  switch (meeting.status) {
    case 'active':
      return (
        <>
          <CopyLinkButton url={meeting.invite_url} />
          <Button size="sm" asChild>
            <Link to={paths.room(meeting.id)}>Войти</Link>
          </Button>
          <Button variant="outline" size="sm" onClick={onEnd}>
            Завершить
          </Button>
        </>
      );
    case 'scheduled':
      return (
        <>
          <CopyLinkButton url={meeting.invite_url} />
          <StartMeetingButton meeting={meeting} />
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
        <MeetingRow key={m.id} meeting={m} />
      ))}
    </ul>
  );
}

/** Строка списка. «Завершить» у идущей встречи спрашивает подтверждение прямо под строкой. */
function MeetingRow({ meeting: m }: { meeting: Meeting }) {
  const [confirming, setConfirming] = useState(false);
  const end = useEndMeeting(m.id);

  return (
    <li className="flex flex-col gap-3 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
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
          <MeetingActions meeting={m} onEnd={() => setConfirming(true)} />
        </div>
      </div>
      {confirming && (
        <ConfirmInline
          text={`Встреча «${m.title}» закончится для всех участников. Это действие нельзя отменить.`}
          confirmLabel="Завершить встречу"
          pending={end.isPending}
          onCancel={() => setConfirming(false)}
          onConfirm={() => end.mutate(undefined, { onSettled: () => setConfirming(false) })}
        />
      )}
      {end.isError && (
        <p role="alert" className="text-sm text-destructive">
          {meetingErrorMessage(end.error, 'завершить встречу')}
        </p>
      )}
    </li>
  );
}
