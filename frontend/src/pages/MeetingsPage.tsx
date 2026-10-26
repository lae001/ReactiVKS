import { ArrowRight, CalendarPlus, Link2, Video } from 'lucide-react';
import { type FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { MeetingList } from '@/features/meetings/MeetingList';
import { paths } from '@/shared/config/routes';
import { parseInviteCode } from '@/shared/lib/invite';
import { cn } from '@/shared/lib/utils';
import { MOCK_MEETINGS } from '@/shared/mocks/data';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { Label } from '@/shared/ui/label';

/** id «быстрой» встречи на тестовых данных; в EMO-73 – POST /meetings без scheduled_at. */
const INSTANT_MEETING_ID = 'instant';

const tileClass = 'flex flex-col gap-4 rounded-xl border p-5 text-left transition-colors';

/**
 * Главная организатора (docs/frontend/site-structure.md, 4.1): плитки действий,
 * ближайшие и прошедшие встречи. Сейчас – на тестовых данных; API – EMO-73.
 */
export function MeetingsPage() {
  const navigate = useNavigate();
  const [invite, setInvite] = useState('');
  const [inviteError, setInviteError] = useState<string | null>(null);

  const upcoming = MOCK_MEETINGS.filter((m) => m.status === 'active' || m.status === 'scheduled');
  const past = MOCK_MEETINGS.filter((m) => m.status === 'ended');

  function joinByLink(e: FormEvent) {
    e.preventDefault();
    const code = parseInviteCode(invite);
    if (!code) {
      setInviteError(
        'Не похоже на ссылку-приглашение. Вставьте ссылку целиком или код из 10 символов.',
      );
      return;
    }
    navigate(paths.join(code));
  }

  return (
    <div className="flex flex-col gap-10">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">Встречи</h1>
        <p className="text-muted-foreground">
          Начните встречу сразу или запланируйте ее и отправьте ссылку участникам.
        </p>
      </header>

      <section aria-label="Действия" className="grid gap-4 md:grid-cols-3">
        <button
          type="button"
          onClick={() => navigate(paths.room(INSTANT_MEETING_ID))}
          className={cn(
            tileClass,
            'border-transparent bg-primary text-primary-foreground hover:bg-primary/90',
          )}
        >
          <Video className="size-6" aria-hidden />
          <span className="flex flex-col gap-1">
            <span className="text-lg font-semibold">Начать сейчас</span>
            <span className="text-sm text-primary-foreground/80">
              Встреча без времени – ссылку можно отправить уже из комнаты
            </span>
          </span>
        </button>

        <Link to={paths.meetingNew} className={cn(tileClass, 'bg-card hover:bg-accent')}>
          <CalendarPlus className="size-6 text-primary" aria-hidden />
          <span className="flex flex-col gap-1">
            <span className="text-lg font-semibold">Запланировать</span>
            <span className="text-sm text-muted-foreground">
              Название, время и анализ эмоций – ссылка появится сразу
            </span>
          </span>
        </Link>

        <form onSubmit={joinByLink} className={cn(tileClass, 'bg-card')} noValidate>
          <Link2 className="size-6 text-primary" aria-hidden />
          <div className="flex flex-col gap-2">
            <Label htmlFor="invite" className="text-lg font-semibold">
              Войти по ссылке
            </Label>
            <div className="flex gap-2">
              <Input
                id="invite"
                value={invite}
                onChange={(e) => {
                  setInvite(e.target.value);
                  setInviteError(null);
                }}
                placeholder="Ссылка или код"
                aria-invalid={inviteError ? true : undefined}
                aria-describedby={inviteError ? 'invite-error' : undefined}
              />
              <Button type="submit" size="icon" aria-label="Перейти в лобби">
                <ArrowRight />
              </Button>
            </div>
            {inviteError && (
              <p id="invite-error" className="text-sm text-destructive">
                {inviteError}
              </p>
            )}
          </div>
        </form>
      </section>

      <section aria-labelledby="upcoming" className="flex flex-col gap-3">
        <h2 id="upcoming" className="text-lg font-semibold">
          Ближайшие
        </h2>
        <MeetingList meetings={upcoming} empty="Запланированных встреч нет." />
      </section>

      <section aria-labelledby="past" className="flex flex-col gap-3">
        <h2 id="past" className="text-lg font-semibold">
          Прошедшие
        </h2>
        <MeetingList meetings={past} empty="Прошедших встреч пока нет." />
      </section>
    </div>
  );
}
