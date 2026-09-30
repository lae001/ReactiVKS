import { CalendarClock, LoaderCircle } from 'lucide-react';
import { type FormEvent, type ReactNode, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import { ConsentFieldset } from '@/features/lobby/ConsentFieldset';
import { DevicePreview } from '@/features/lobby/DevicePreview';
import {
  type ConsentChoice,
  type JoinFormErrors,
  validateJoinForm,
} from '@/features/lobby/validate';
import { paths } from '@/shared/config/routes';
import { useLocalMedia } from '@/shared/hooks/use-local-media';
import { formatDateTime } from '@/shared/lib/format';
import type { RoomEntry } from '@/shared/lib/room-entry';
import { checkWebRtcSupport, describeWebRtcProblem } from '@/shared/lib/webrtc-support';
import { getJoinInfo, joinMeeting } from '@/shared/mocks/data';
import { Wordmark } from '@/shared/ui/brand';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { Label } from '@/shared/ui/label';

function LobbyShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col gap-8 px-4 py-6 md:px-10 md:py-8">
      <Wordmark />
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

/**
 * UC-3. Лобби участника (docs/frontend/site-structure.md, 4.2): превью камеры слева,
 * имя и явное согласие на анализ эмоций справа. Сейчас – на тестовых данных;
 * GET/POST /api/v1/join/{invite_code} – EMO-74, согласие – EMO-89.
 */
export function JoinPage() {
  const { inviteCode = '' } = useParams();
  const info = getJoinInfo(inviteCode);

  if (!info) {
    return (
      <LobbyMessage
        title="Приглашение не найдено"
        text="Проверьте ссылку: возможно, в ней опечатка или она устарела. Попросите организатора прислать ее еще раз."
      />
    );
  }
  if (info.status === 'ended' || info.status === 'cancelled') {
    return (
      <LobbyMessage
        title="Встреча завершена"
        text={`Встреча «${info.title}» уже закончилась. Если это ошибка, свяжитесь с организатором – ${info.organizer_name}.`}
      />
    );
  }
  return <Lobby inviteCode={inviteCode} info={info} />;
}

function Lobby({
  inviteCode,
  info,
}: {
  inviteCode: string;
  info: NonNullable<ReturnType<typeof getJoinInfo>>;
}) {
  const navigate = useNavigate();
  const media = useLocalMedia();
  const problem = describeWebRtcProblem(checkWebRtcSupport());

  const [displayName, setDisplayName] = useState('');
  const [consent, setConsent] = useState<ConsentChoice | null>(null);
  const [errors, setErrors] = useState<JoinFormErrors>({});
  const [waiting, setWaiting] = useState(false);

  function submit(e: FormEvent) {
    e.preventDefault();
    const found = validateJoinForm({
      displayName,
      consent,
      consentRequired: info.consent_notice !== null,
    });
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    const result = joinMeeting(inviteCode, {
      display_name: displayName.trim(),
      consent: consent ?? undefined,
    });
    if ('error' in result) {
      // meeting_not_started: meeting-service ответит 409, клиент повторяет запрос раз в 5 с
      // (повтор – вместе с API в EMO-74; на тестовых данных встреча не начнется)
      if (result.error === 'meeting_not_started') setWaiting(true);
      return;
    }

    const entry: RoomEntry = {
      role: 'guest',
      displayName: displayName.trim(),
      consent: info.consent_notice ? (consent ?? 'denied') : 'not_required',
      cameraOn: media.cameraOn,
      micOn: media.micOn,
      inviteCode,
    };
    navigate(paths.room(result.meetingId), { state: entry });
  }

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

          {waiting ? (
            <div
              role="status"
              className="flex flex-col gap-3 rounded-xl border border-primary/30 bg-accent p-4 text-sm"
            >
              <p className="flex items-center gap-2 font-medium text-accent-foreground">
                <LoaderCircle className="size-4 animate-spin" aria-hidden />
                Встреча еще не началась
              </p>
              <p className="text-muted-foreground">
                Вы войдете автоматически, как только организатор ее начнет. Не закрывайте вкладку.
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="self-start"
                onClick={() => setWaiting(false)}
              >
                Отменить ожидание
              </Button>
            </div>
          ) : (
            <Button type="submit" size="lg" disabled={problem !== null}>
              Войти во встречу
            </Button>
          )}
        </form>
      </main>
    </LobbyShell>
  );
}
