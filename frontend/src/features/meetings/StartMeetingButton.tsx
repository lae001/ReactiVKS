import { LoaderCircle } from 'lucide-react';
import { useNavigate } from 'react-router';

import type { Meeting } from '@/shared/api/meetings';
import { paths } from '@/shared/config/routes';
import { Button } from '@/shared/ui/button';

import { meetingErrorMessage } from './errors';
import { useStartMeeting } from './queries';

/** «Начать встречу»: активирует запланированную встречу входом организатора и открывает комнату. */
export function StartMeetingButton({
  meeting,
  label = 'Начать встречу',
}: {
  meeting: Pick<Meeting, 'id' | 'analysis_enabled'>;
  label?: string;
}) {
  const navigate = useNavigate();
  const start = useStartMeeting(meeting);

  return (
    <>
      <Button
        size="sm"
        disabled={start.isPending}
        onClick={() =>
          start.mutate(undefined, { onSuccess: () => navigate(paths.room(meeting.id)) })
        }
      >
        {start.isPending && <LoaderCircle className="animate-spin" aria-hidden />}
        {label}
      </Button>
      {start.isError && (
        <p role="alert" className="w-full text-sm text-destructive">
          {meetingErrorMessage(start.error, 'начать встречу')}
        </p>
      )}
    </>
  );
}
