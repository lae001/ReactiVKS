import { zodResolver } from '@hookform/resolvers/zod';
import { CalendarClock, Check, LoaderCircle } from 'lucide-react';
import { useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { Link } from 'react-router';

import {
  type MeetingFormValues,
  meetingFormSchema,
  toCreateRequest,
} from '@/features/meetings/schemas';
import { meetingErrorMessage } from '@/features/meetings/errors';
import { useCreateMeeting, useSettings } from '@/features/meetings/queries';
import type { Meeting, Settings } from '@/shared/api/meetings';
import { ApiError, fieldOf } from '@/shared/api/problem';
import { paths } from '@/shared/config/routes';
import { cn } from '@/shared/lib/utils';
import { Button } from '@/shared/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card';
import { CopyLinkButton } from '@/shared/ui/copy-link-button';
import { Field } from '@/shared/ui/field';

const FPS_OPTIONS = [2, 3, 4, 5] as const;

/** Значения по умолчанию из GET /settings; пока настройки не загрузились или сервис не ответил – как в контракте. */
const CONTRACT_DEFAULTS: Settings = { analysis_enabled_default: true, analysis_fps_default: 3 };

/**
 * UC-2. Создание встречи: название, время, анализ эмоций. Цель – создать встречу и скопировать
 * ссылку за три действия: ввести название, нажать «Создать», нажать «Копировать ссылку».
 */
export function MeetingNewPage() {
  const settings = useSettings();
  if (settings.isPending) {
    return (
      <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" aria-hidden /> Загружаем настройки…
      </p>
    );
  }
  return <NewMeeting defaults={settings.data ?? CONTRACT_DEFAULTS} />;
}

function NewMeeting({ defaults }: { defaults: Settings }) {
  const [created, setCreated] = useState<Meeting | null>(null);
  const create = useCreateMeeting();
  // Один ключ на попытку: повторная отправка той же формы (двойной клик, сбой сети) не создаст
  // вторую встречу; после успеха ключ меняется.
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());
  const {
    register,
    handleSubmit,
    control,
    setValue,
    setError,
    reset,
    formState: { errors },
  } = useForm<MeetingFormValues>({
    resolver: zodResolver(meetingFormSchema),
    defaultValues: {
      title: '',
      scheduled_at: '',
      analysis_enabled: defaults.analysis_enabled_default,
      analysis_fps: defaults.analysis_fps_default,
    },
  });
  const analysis = useWatch({ control, name: 'analysis_enabled' });
  const fps = useWatch({ control, name: 'analysis_fps' });
  const scheduled = useWatch({ control, name: 'scheduled_at' });

  const onSubmit = handleSubmit((values) => {
    create.mutate(
      { body: toCreateRequest(values), key: idempotencyKey },
      {
        onSuccess: (meeting) => {
          setIdempotencyKey(crypto.randomUUID());
          setCreated(meeting);
        },
        onError: (error) => {
          if (error instanceof ApiError) {
            for (const issue of error.errors) {
              const field = fieldOf(issue);
              if (field === 'title' || field === 'scheduled_at') {
                setError(field, { message: issue.msg });
              }
            }
          }
        },
      },
    );
  });

  if (created) {
    return (
      <section className="flex max-w-2xl flex-col gap-6" aria-labelledby="created-title">
        <header className="flex flex-col gap-2">
          <p className="inline-flex items-center gap-2 text-sm font-medium text-primary">
            <Check className="size-4" aria-hidden /> Встреча создана
          </p>
          <h1 id="created-title" className="text-2xl font-semibold tracking-tight md:text-3xl">
            {created.title}
          </h1>
          <p className="text-muted-foreground">
            Отправьте ссылку участникам — войти можно без регистрации.
          </p>
        </header>
        <Card>
          <CardContent className="flex flex-col gap-3 pt-6">
            <p className="rounded-md border bg-muted px-3 py-2 text-sm break-all">
              {created.invite_url}
            </p>
            <div className="flex flex-wrap gap-2">
              <CopyLinkButton url={created.invite_url} variant="default" />
              <Button variant="outline" size="sm" asChild>
                <Link to={paths.meeting(created.id)}>Открыть карточку</Link>
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  reset();
                  setCreated(null);
                }}
              >
                Создать еще одну
              </Button>
            </div>
          </CardContent>
        </Card>
      </section>
    );
  }

  return (
    <section className="flex max-w-2xl flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">Новая встреча</h1>
        <p className="text-muted-foreground">
          Задайте название и время — ссылка-приглашение появится сразу после создания.
        </p>
      </header>

      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Что и когда</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <Field
              id="title"
              label="Название"
              placeholder="Еженедельная планерка"
              error={errors.title?.message}
              {...register('title')}
            />
            <Field
              id="scheduled_at"
              label="Дата и время начала"
              type="datetime-local"
              hint={
                scheduled
                  ? undefined
                  : 'Оставьте пустым, чтобы начать сразу: время можно не задавать.'
              }
              error={errors.scheduled_at?.message}
              {...register('scheduled_at')}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Анализ эмоций</CardTitle>
            <CardDescription>
              Работает только с согласия каждого участника. Видео не записывается, сохраняются лишь
              итоги распознавания для отчета.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            <label className="flex cursor-pointer items-start gap-3">
              <input
                type="checkbox"
                className="mt-0.5 size-5 shrink-0 accent-primary"
                {...register('analysis_enabled')}
              />
              <span className="flex flex-col gap-0.5">
                <span className="text-sm font-medium">Анализировать эмоции участников</span>
                <span className="text-sm text-muted-foreground">
                  Участники увидят уведомление и выберут, участвовать ли в анализе.
                </span>
              </span>
            </label>

            <fieldset className="flex flex-col gap-2" disabled={!analysis}>
              <legend className="text-sm font-medium">Частота анализа, кадров в секунду</legend>
              <div className="flex gap-2" role="radiogroup" aria-label="Кадров в секунду">
                {FPS_OPTIONS.map((n) => (
                  <label
                    key={n}
                    className={cn(
                      'flex h-10 w-14 cursor-pointer items-center justify-center rounded-md border text-sm font-medium transition-colors has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-ring/40',
                      fps === n
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'bg-card hover:bg-accent',
                      !analysis && 'cursor-not-allowed opacity-50',
                    )}
                  >
                    <input
                      type="radio"
                      name="analysis_fps"
                      value={n}
                      checked={fps === n}
                      onChange={() => setValue('analysis_fps', n)}
                      className="sr-only"
                    />
                    {n}
                  </label>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                3 кадра в секунду достаточно для большинства встреч; больше — выше нагрузка на
                сервер.
              </p>
            </fieldset>
          </CardContent>
        </Card>

        {create.isError && (
          <p role="alert" className="text-sm text-destructive">
            {meetingErrorMessage(create.error, 'создать встречу')}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" size="lg" disabled={create.isPending}>
            {create.isPending ? (
              <LoaderCircle className="animate-spin" aria-hidden />
            ) : (
              <CalendarClock aria-hidden />
            )}
            {scheduled ? 'Создать встречу' : 'Создать и получить ссылку'}
          </Button>
          <Button variant="ghost" size="lg" asChild>
            <Link to={paths.meetings}>Отмена</Link>
          </Button>
        </div>
      </form>
    </section>
  );
}
