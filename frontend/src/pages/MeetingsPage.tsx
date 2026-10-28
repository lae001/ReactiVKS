import { ArrowRight, CalendarPlus, LoaderCircle, Link2, Search, Video } from 'lucide-react';
import { type FormEvent, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { meetingErrorMessage } from '@/features/meetings/errors';
import { MeetingList } from '@/features/meetings/MeetingList';
import {
  flattenPages,
  type MeetingsFilters,
  useMeetingsList,
  useStartInstantMeeting,
} from '@/features/meetings/queries';
import type { MeetingStatus } from '@/shared/api/meetings';
import { paths } from '@/shared/config/routes';
import { parseInviteCode } from '@/shared/lib/invite';
import { cn } from '@/shared/lib/utils';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { Label } from '@/shared/ui/label';

const tileClass = 'flex gap-4 rounded-xl border p-4 text-left transition-colors md:flex-col md:p-5';

const STATUS_FILTERS: { label: string; status?: MeetingStatus[] }[] = [
  { label: 'Все' },
  { label: 'Идут', status: ['active'] },
  { label: 'Запланированы', status: ['scheduled'] },
  { label: 'Завершены', status: ['ended'] },
];

/** Пауза после последнего символа поиска, чтобы не слать запрос на каждую букву. */
const SEARCH_DEBOUNCE_MS = 300;

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

/**
 * Главная организатора (docs/frontend/site-structure.md, 4.1): плитки действий и список встреч
 * с поиском, фильтром по статусу и подгрузкой «Ещё» (GET /meetings, курсор).
 */
export function MeetingsPage() {
  const navigate = useNavigate();
  const [invite, setInvite] = useState('');
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState(0);

  const q = useDebounced(search.trim(), SEARCH_DEBOUNCE_MS);
  const filters: MeetingsFilters = { status: STATUS_FILTERS[filter]?.status, q: q || undefined };
  const list = useMeetingsList(filters);
  const meetings = flattenPages(list.data);
  const instant = useStartInstantMeeting();
  const filtered = filter !== 0 || q !== '';

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
          disabled={instant.isPending}
          onClick={() =>
            instant.mutate(crypto.randomUUID(), {
              onSuccess: (m) => navigate(paths.room(m.id)),
            })
          }
          className={cn(
            tileClass,
            'border-transparent bg-primary text-primary-foreground hover:bg-primary/90',
          )}
        >
          {instant.isPending ? (
            <LoaderCircle className="size-6 shrink-0 animate-spin" aria-hidden />
          ) : (
            <Video className="size-6 shrink-0" aria-hidden />
          )}
          <span className="flex flex-col gap-1">
            <span className="text-lg font-semibold">Начать сейчас</span>
            <span className="text-sm text-primary-foreground/80">
              Встреча без времени – ссылку можно отправить уже из комнаты
            </span>
          </span>
        </button>

        <Link to={paths.meetingNew} className={cn(tileClass, 'bg-card hover:bg-accent')}>
          <CalendarPlus className="size-6 shrink-0 text-primary" aria-hidden />
          <span className="flex flex-col gap-1">
            <span className="text-lg font-semibold">Запланировать</span>
            <span className="text-sm text-muted-foreground">
              Название, время и анализ эмоций – ссылка появится сразу
            </span>
          </span>
        </Link>

        <form onSubmit={joinByLink} className={cn(tileClass, 'bg-card')} noValidate>
          <Link2 className="size-6 shrink-0 text-primary" aria-hidden />
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

      {instant.isError && (
        <p role="alert" className="text-sm text-destructive">
          {meetingErrorMessage(instant.error, 'начать встречу')}
        </p>
      )}

      <section aria-labelledby="meetings-title" className="flex flex-col gap-4">
        <h2 id="meetings-title" className="text-lg font-semibold">
          Все встречи
        </h2>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative sm:w-80">
            <Search
              className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <Input
              type="search"
              aria-label="Поиск по названию"
              placeholder="Поиск по названию"
              maxLength={100}
              className="pl-9"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div role="group" aria-label="Статус встречи" className="flex flex-wrap gap-2">
            {STATUS_FILTERS.map((f, i) => (
              <Button
                key={f.label}
                type="button"
                size="sm"
                variant={filter === i ? 'default' : 'outline'}
                aria-pressed={filter === i}
                onClick={() => setFilter(i)}
              >
                {f.label}
              </Button>
            ))}
          </div>
        </div>

        {list.isPending ? (
          <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle className="size-4 animate-spin" aria-hidden /> Загружаем встречи…
          </p>
        ) : list.isError ? (
          <div role="alert" className="flex flex-col items-start gap-2 text-sm">
            <p className="text-destructive">
              {meetingErrorMessage(list.error, 'загрузить встречи')}
            </p>
            <Button variant="outline" size="sm" onClick={() => void list.refetch()}>
              Повторить
            </Button>
          </div>
        ) : (
          <>
            <MeetingList
              meetings={meetings}
              empty={
                filtered ? 'Ничего не найдено. Измените поиск или фильтр.' : 'Встреч пока нет.'
              }
            />
            {list.hasNextPage && (
              <Button
                variant="outline"
                className="self-center"
                disabled={list.isFetchingNextPage}
                onClick={() => void list.fetchNextPage()}
              >
                {list.isFetchingNextPage ? 'Загружаем…' : 'Ещё'}
              </Button>
            )}
          </>
        )}
      </section>
    </div>
  );
}
