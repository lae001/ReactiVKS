import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';

import type { Meeting, UpdateMeetingRequest } from '@/shared/api/meetings';
import { ApiError, fieldOf } from '@/shared/api/problem';
import { Button } from '@/shared/ui/button';
import { Field } from '@/shared/ui/field';

import { meetingErrorMessage } from './errors';
import { useUpdateMeeting } from './queries';
import { type MeetingFormValues, meetingFormSchema, toDatetimeLocal } from './schemas';

const FPS_OPTIONS = [2, 3, 4, 5] as const;

/**
 * Правка встречи (PATCH /meetings/{id}): название меняется в любом статусе, время и анализ –
 * только у запланированной (иначе сервер ответит `meeting_not_editable`).
 */
export function MeetingEditForm({ meeting, onDone }: { meeting: Meeting; onDone: () => void }) {
  const update = useUpdateMeeting(meeting.id);
  const editable = meeting.status === 'scheduled';
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<MeetingFormValues>({
    resolver: zodResolver(meetingFormSchema),
    defaultValues: {
      title: meeting.title,
      scheduled_at: toDatetimeLocal(meeting.scheduled_at),
      analysis_enabled: meeting.analysis_enabled,
      analysis_fps: meeting.analysis_fps,
    },
  });

  const onSubmit = handleSubmit((values) => {
    const body: UpdateMeetingRequest = {};
    if (values.title.trim() !== meeting.title) body.title = values.title.trim();
    if (editable) {
      const scheduledAt = values.scheduled_at ? new Date(values.scheduled_at).toISOString() : null;
      if (scheduledAt !== meeting.scheduled_at) body.scheduled_at = scheduledAt;
      if (values.analysis_enabled !== meeting.analysis_enabled) {
        body.analysis_enabled = values.analysis_enabled;
      }
      if (values.analysis_fps !== meeting.analysis_fps) body.analysis_fps = values.analysis_fps;
    }
    if (Object.keys(body).length === 0) return onDone();
    update.mutate(body, {
      onSuccess: onDone,
      onError: (error) => {
        if (!(error instanceof ApiError)) return;
        for (const issue of error.errors) {
          const field = fieldOf(issue);
          if (field === 'title' || field === 'scheduled_at') {
            setError(field, { message: issue.msg });
          }
        }
      },
    });
  });

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      className="flex flex-col gap-4"
      aria-label="Правка встречи"
    >
      <Field
        id="edit-title"
        label="Название"
        error={errors.title?.message}
        {...register('title')}
      />
      {editable ? (
        <>
          <Field
            id="edit-scheduled"
            label="Дата и время начала"
            type="datetime-local"
            error={errors.scheduled_at?.message}
            {...register('scheduled_at')}
          />
          <label className="flex items-center gap-3 text-sm">
            <input
              type="checkbox"
              className="size-5 accent-primary"
              {...register('analysis_enabled')}
            />
            Анализировать эмоции участников
          </label>
          <div className="flex flex-col gap-1">
            <label htmlFor="edit-fps" className="text-sm font-medium">
              Кадров в секунду
            </label>
            <select
              id="edit-fps"
              className="h-9 w-24 rounded-md border bg-card px-2 text-sm"
              {...register('analysis_fps', { valueAsNumber: true })}
            >
              {FPS_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">
          У начатой встречи можно изменить только название.
        </p>
      )}
      {update.isError && (
        <p role="alert" className="text-sm text-destructive">
          {meetingErrorMessage(update.error, 'сохранить изменения')}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={update.isPending}>
          Сохранить
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onDone}>
          Отмена
        </Button>
      </div>
    </form>
  );
}
