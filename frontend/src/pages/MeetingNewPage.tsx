import { zodResolver } from '@hookform/resolvers/zod';
import { CalendarClock, Check } from 'lucide-react';
import { useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { Link } from 'react-router';

import {
  type MeetingFormValues,
  meetingFormSchema,
  toCreateRequest,
} from '@/features/meetings/schemas';
import type { Meeting } from '@/shared/api/types';
import { paths } from '@/shared/config/routes';
import { cn } from '@/shared/lib/utils';
import { createMockMeeting } from '@/shared/mocks/data';
import { Button } from '@/shared/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card';
import { CopyLinkButton } from '@/shared/ui/copy-link-button';
import { Field } from '@/shared/ui/field';

const FPS_OPTIONS = [2, 3, 4, 5] as const;

/** UC-2. Создание встречи: название, время, анализ эмоций. Запрос – на тестовых данных, API в EMO-73. */
export function MeetingNewPage() {
  const [created, setCreated] = useState<Meeting | null>(null);
  const {
    register,
    handleSubmit,
    control,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<MeetingFormValues>({
    resolver: zodResolver(meetingFormSchema),
    // Значения по умолчанию – из /settings (GET /settings), пока их там нет – как в контракте
    defaultValues: { title: '', scheduled_at: '', analysis_enabled: true, analysis_fps: 3 },
  });
  const analysis = useWatch({ control, name: 'analysis_enabled' });
  const fps = useWatch({ control, name: 'analysis_fps' });
  const scheduled = useWatch({ control, name: 'scheduled_at' });

  const onSubmit = handleSubmit((values) => {
    setCreated(createMockMeeting(toCreateRequest(values)));
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
              <Button variant="ghost" size="sm" onClick={() => setCreated(null)}>
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

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" size="lg" disabled={isSubmitting}>
            <CalendarClock aria-hidden />
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
