import { LoaderCircle, Search } from 'lucide-react';
import { useEffect, useState } from 'react';

import { useAuth } from '@/features/auth/auth-context';
import { ConfirmInline } from '@/features/meetings/ConfirmInline';
import { formatDateTime } from '@/shared/lib/format';
import { Badge } from '@/shared/ui/badge';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';

import type { AdminUser, UserStatus } from './api';
import { adminErrorMessage } from './errors';
import { useAdminUsers, useSetUserStatus } from './queries';

const SEARCH_DEBOUNCE_MS = 300;

const FILTERS: { value: UserStatus | ''; label: string }[] = [
  { value: '', label: 'Все' },
  { value: 'active', label: 'Активные' },
  { value: 'blocked', label: 'Заблокированные' },
];

const ROLE: Record<AdminUser['role'], string> = {
  admin: 'Администратор',
  organizer: 'Организатор',
};

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

/** Пользователи (UC-7): поиск, фильтр по статусу, блокировка и разблокировка с подтверждением. */
export function UsersSection() {
  const { user: me } = useAuth();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<UserStatus | ''>('');
  const [target, setTarget] = useState<AdminUser | null>(null);
  const q = useDebounced(search.trim(), SEARCH_DEBOUNCE_MS);
  const list = useAdminUsers({ q: q || undefined, status: status || undefined });
  const change = useSetUserStatus();
  const users = list.data?.pages.flatMap((p) => p.items) ?? [];

  const blocking = target?.status === 'active';

  return (
    <section aria-labelledby="admin-users" className="flex flex-col gap-4">
      <h2 id="admin-users" className="text-lg font-semibold">
        Пользователи
      </h2>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative sm:w-80">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            type="search"
            aria-label="Поиск по почте или имени"
            placeholder="Поиск по почте или имени"
            maxLength={100}
            className="pl-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div role="group" aria-label="Статус" className="flex flex-wrap gap-2">
          {FILTERS.map((f) => (
            <Button
              key={f.value}
              size="sm"
              variant={status === f.value ? 'default' : 'outline'}
              aria-pressed={status === f.value}
              onClick={() => setStatus(f.value)}
            >
              {f.label}
            </Button>
          ))}
        </div>
      </div>

      {target && (
        <ConfirmInline
          text={
            blocking
              ? `Заблокировать ${target.display_name} (${target.email})? Все его сессии завершатся, а вход во встречи закроется.`
              : `Разблокировать ${target.display_name} (${target.email})? Он снова сможет входить.`
          }
          confirmLabel={blocking ? 'Заблокировать' : 'Разблокировать'}
          pending={change.isPending}
          onCancel={() => {
            setTarget(null);
            change.reset();
          }}
          onConfirm={() =>
            change.mutate(
              { id: target.id, status: blocking ? 'blocked' : 'active' },
              { onSuccess: () => setTarget(null) },
            )
          }
        />
      )}
      {change.isError && (
        <p role="alert" className="text-sm text-destructive">
          {adminErrorMessage(change.error, blocking ? 'заблокировать' : 'разблокировать')}
        </p>
      )}

      {list.isPending ? (
        <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
          <LoaderCircle className="size-4 animate-spin" aria-hidden /> Загружаем пользователей…
        </p>
      ) : list.isError ? (
        <div role="alert" className="flex flex-col items-start gap-2 text-sm">
          <p className="text-destructive">
            {adminErrorMessage(list.error, 'загрузить пользователей')}
          </p>
          <Button variant="outline" size="sm" onClick={() => void list.refetch()}>
            Повторить
          </Button>
        </div>
      ) : users.length === 0 ? (
        <p className="rounded-lg border border-dashed p-5 text-sm text-muted-foreground">
          {q || status ? 'Никого не нашли. Измените поиск или фильтр.' : 'Пользователей пока нет.'}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border bg-card">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Пользователи Системы</caption>
            <thead className="border-b text-muted-foreground">
              <tr>
                <th scope="col" className="px-4 py-3 font-medium">
                  Пользователь
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  Роль
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  Статус
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  Последний вход
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  <span className="sr-only">Действия</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {users.map((u) => {
                const self = u.id === me?.id;
                return (
                  <tr key={u.id}>
                    <td className="px-4 py-3">
                      <div className="font-medium">
                        {u.display_name}
                        {self && <span className="font-normal text-muted-foreground"> (вы)</span>}
                      </div>
                      <div className="text-muted-foreground">{u.email}</div>
                    </td>
                    <td className="px-4 py-3">{ROLE[u.role]}</td>
                    <td className="px-4 py-3">
                      <Badge variant={u.status === 'blocked' ? 'outline' : 'secondary'}>
                        {u.status === 'blocked' ? 'Заблокирован' : 'Активен'}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {u.last_login_at ? formatDateTime(u.last_login_at) : 'Не входил'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={self && u.status === 'active'}
                        title={self ? 'Нельзя заблокировать себя' : undefined}
                        aria-label={`${u.status === 'active' ? 'Заблокировать' : 'Разблокировать'}: ${u.display_name}`}
                        onClick={() => {
                          change.reset();
                          setTarget(u);
                        }}
                      >
                        {u.status === 'active' ? 'Заблокировать' : 'Разблокировать'}
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

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
    </section>
  );
}
