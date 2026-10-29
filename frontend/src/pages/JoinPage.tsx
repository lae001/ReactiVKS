import { useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarClock, LoaderCircle } from 'lucide-react';
import { type FormEvent, type ReactNode, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import { ConsentFieldset } from '@/features/lobby/ConsentFieldset';
import { DevicePreview } from '@/features/lobby/DevicePreview';
import { LobbyBackLink } from '@/features/lobby/LobbyBackLink';
import { POLL_INTERVAL_MS, useJoinFlow } from '@/features/lobby/use-join-flow';
import {
  type ConsentChoice,
  type JoinFormErrors,
  validateJoinForm,
} from '@/features/lobby/validate';
import { joinErrorMessage, meetingErrorMessage } from '@/features/meetings/errors';
import { type JoinInfo, meetingsApi } from '@/shared/api/meetings';
import { ApiError, fieldOf } from '@/shared/api/problem';
import { paths } from '@/shared/config/routes';
import { useLocalMedia } from '@/shared/hooks/use-local-media';
import { formatDateTime } from '@/shared/lib/format';
import { setParticipantToken } from '@/shared/lib/participant-session';
import type { RoomEntry } from '@/shared/lib/room-entry';
import { checkWebRtcSupport, describeWebRtcProblem } from '@/shared/lib/webrtc-support';
import { Wordmark } from '@/shared/ui/brand';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { Label } from '@/shared/ui/label';

function LobbyShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col gap-8 px-4 py-6 md:px-10 md:py-8">
      <Wordmark />
      <LobbyBackLink />
      {children}
    </div>
  );
}

function LobbyMessage({ title, text }: { title: string; text: string }) {
  return (
    <LobbyShell>
      <main className="flex max-w-md flex-1 flex-col justify-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="text-muted-foreground">{text}</p>
      </main>
    </LobbyShell>
  );
}

/** Экран вместо формы: после этих кодов вход по ссылке невозможен. */
function terminalScreen(code: string, info: JoinInfo): { title: string; text: string } {
  const contact = `Если это ошибка, свяжитесь с организатором – ${info.organizer_name}.`;
  switch (code) {
    case 'meeting_cancelled':
      return {
        title: 'Встреча отменена',
        text: `Встреча «${info.title}» отменена организатором. ${contact}`,
      };
    case 'participant_removed':
      return {
        title: 'Вас удалили из встречи',
        text: `Организатор удалил вас из встречи «${info.title}», вернуться по этой ссылке нельзя. ${contact}`,
      };
    case 'not_found':
      return {
        title: 'Приглашение не найдено',
        text: 'Возможно, встречу удалили или ссылка устарела. Попросите организатора прислать ее еще раз.',
      };
    case 'forbidden':
      return {
        title: 'Нет доступа',
        text: `Войти во встречу «${info.title}» по этой ссылке нельзя. ${contact}`,
      };
    case 'user_blocked':
      return {
        title: 'Доступ закрыт',
        text: 'Ваша учетная запись заблокирована. Обратитесь к администратору системы.',
      };
    default:
      return {
        title: 'Встреча завершена',
        text: `Встреча «${info.title}» уже закончилась. ${contact}`,
      };
  }
}

/**
 * UC-3. Лобби участника (docs/frontend/site-structure.md, 4.2): превью камеры слева,
 * имя и явное согласие на анализ эмоций справа. Данные – через слой API
 * (GET и POST /join/{invite_code}).
 */
export function JoinPage() {
  const { inviteCode = '' } = useParams();
  const query = useQuery({
    queryKey: ['join-info', inviteCode],
    queryFn: ({ signal }) => meetingsApi.getJoinInfo(inviteCode, signal),
  });

  if (query.isPending) {
    return (
      <LobbyShell>
        <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
          <LoaderCircle className="size-4 animate-spin" aria-hidden /> Открываем приглашение…
        </p>
      </LobbyShell>
    );
  }
  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.code === 'not_found';
    return (
      <LobbyMessage
        title={notFound ? 'Приглашение не найдено' : 'Не удалось открыть приглашение'}
        text={
          notFound
            ? 'Проверьте ссылку: возможно, в ней опечатка или она устарела. Попросите организатора прислать ее еще раз.'
            : meetingErrorMessage(query.error, 'открыть приглашение')
        }
      />
    );
  }

  const info = query.data;
  if (info.status === 'ended' || info.status === 'cancelled') {
    const screen = terminalScreen(`meeting_${info.status}`, info);
    return <LobbyMessage {...screen} />;
  }
  return <Lobby inviteCode={inviteCode} info={info} />;
}

function Lobby({ inviteCode, info }: { inviteCode: string; info: JoinInfo }) {
  const navigate = useNavigate();
  const media = useLocalMedia();
  const problem = describeWebRtcProblem(checkWebRtcSupport());

  const [displayName, setDisplayName] = useState('');
  const [consent, setConsent] = useState<ConsentChoice | null>(null);
  const [errors, setErrors] = useState<JoinFormErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const flow = useJoinFlow({
    inviteCode,
    onJoined: (result) => {
      setParticipantToken(result.participant_token);
      const entry: RoomEntry = {
        role: 'guest',
        displayName: displayName.trim(),
        consent: info.consent_notice ? (consent ?? 'denied') : 'not_required',
        cameraOn: media.cameraOn,
        micOn: media.micOn,
        inviteCode,
        participantId: result.participant_id,
        meeting: result.meeting,
      };
      navigate(paths.room(result.meeting.id), { state: entry });
    },
    onFailed: (error) => {
      if (error instanceof ApiError && error.code === 'notice_outdated') {
        // Текст уведомления сменился: показываем новый и просим выбрать заново
        setConsent(null);
        void queryClient.invalidateQueries({ queryKey: ['join-info', inviteCode] });
      }
      if (error instanceof ApiError && error.code === 'validation_error') {
        const issue = error.errors.find((i) => fieldOf(i) === 'display_name');
        if (issue) return setErrors({ displayName: issue.msg });
      }
      setFormError(joinErrorMessage(error));
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const found = validateJoinForm({
      displayName,
      consent,
      consentRequired: info.consent_notice !== null,
    });
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setFormError(null);
    flow.submit({
      display_name: displayName.trim(),
      consent: consent ?? undefined,
      notice_version: info.consent_notice?.version,
    });
  }

  if (flow.terminal) return <LobbyMessage {...terminalScreen(flow.terminal.code, info)} />;

  return (
    <LobbyShell>
      <main className="mx-auto grid w-full max-w-6xl flex-1 items-start gap-8 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] md:gap-10 lg:content-center">
        <DevicePreview media={media} displayName={displayName} />

        <form onSubmit={submit} noValidate className="flex flex-col gap-5">
          <div className="flex flex-col gap-1">
            <p className="text-sm text-muted-foreground">Приглашение от {info.organizer_name}</p>
            <h1 className="text-2xl font-semibold tracking-tight">{info.title}</h1>
            {info.status === 'scheduled' && info.scheduled_at && (
              <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
                <CalendarClock className="size-4" aria-hidden />
                Начало: {formatDateTime(info.scheduled_at)}
              </p>
            )}
          </div>

          {problem && (
            <p
              role="alert"
              className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm"
            >
              {problem}
            </p>
          )}

          <div className="flex flex-col gap-2">
            <Label htmlFor="display-name">Как вас представить</Label>
            <Input
              id="display-name"
              autoComplete="name"
              placeholder="Имя и фамилия"
              maxLength={64}
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              aria-invalid={errors.displayName ? true : undefined}
              aria-describedby={errors.displayName ? 'display-name-error' : undefined}
            />
            {errors.displayName && (
              <p id="display-name-error" className="text-sm text-destructive">
                {errors.displayName}
              </p>
            )}
          </div>

          {info.consent_notice && (
            <ConsentFieldset
              notice={info.consent_notice}
              value={consent}
              onChange={(v) => {
                setConsent(v);
                setErrors(({ consent: _, ...rest }) => rest);
              }}
              error={errors.consent}
            />
          )}

          {flow.phase === 'waiting' ? (
            <div
              role="status"
              className="flex flex-col gap-3 rounded-xl border border-primary/30 bg-accent p-4 text-sm"
            >
              <p className="flex items-center gap-2 font-medium text-accent-foreground">
                <LoaderCircle className="size-4 animate-spin" aria-hidden />
                Встреча еще не началась
              </p>
              <p className="text-muted-foreground">
                Проверяем каждые {POLL_INTERVAL_MS / 1000} секунд и войдем сами, как только
                организатор начнет встречу. Эту страницу можно не обновлять.
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="self-start"
                onClick={flow.cancel}
              >
                Отменить ожидание
              </Button>
            </div>
          ) : (
            <>
              {flow.phase === 'timed_out' && (
                <p role="alert" className="text-sm text-destructive">
                  Встреча не началась за 10 минут, ждать мы перестали. Узнайте у организатора, когда
                  она начнется, и нажмите «Войти во встречу» снова.
                </p>
              )}
              {formError && (
                <p role="alert" className="text-sm text-destructive">
                  {formError}
                </p>
              )}
              <Button type="submit" size="lg" disabled={problem !== null || flow.pending}>
                Войти во встречу
              </Button>
            </>
          )}
        </form>
      </main>
    </LobbyShell>
  );
}
