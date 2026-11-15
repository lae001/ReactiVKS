import { useState } from 'react';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/shared/api/client';
import type { Meeting, MeetingStatus, Page } from '@/shared/api/meetings';
import { resolveApiMode } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';
import { Button } from '@/shared/ui/button';

interface AdminMeeting extends Meeting {
  owner_id: string;
  online_participants: number;
}
type HealthState = 'ok' | 'degraded' | 'down';
interface Health {
  status: HealthState;
  checked_at: string;
  components: Record<
    string,
    {
      status: HealthState;
      consumer_lag_s?: number;
      rooms?: number;
      participants?: number;
      last_heartbeat?: string;
    }
  >;
}
const healthLabels = { ok: 'Работает', degraded: 'Частично доступен', down: 'Недоступен' };
const statusLabels: Record<MeetingStatus, string> = {
  scheduled: 'Запланирована',
  active: 'Идет',
  ended: 'Завершена',
  cancelled: 'Отменена',
};

function unavailable(error: unknown) {
  if (error instanceof ApiError && (error.status === 403 || error.status === 401))
    return 'Нет доступа. Требуется действующая сессия администратора.';
  if (error instanceof ApiError && error.status === 404)
    return 'Сервис пока не предоставляет этот раздел.';
  return 'Не удалось связаться с сервисом. Повторите позже.';
}

/** Только GET-операции, предусмотренные контрактом meeting-service. */
export function ServiceSections() {
  const demo = resolveApiMode(import.meta.env.VITE_API_MODE) === 'mock';
  const [status, setStatus] = useState<MeetingStatus | ''>('active');
  const meetings = useInfiniteQuery({
    queryKey: ['admin', 'meetings', status, demo],
    queryFn: ({ pageParam, signal }) =>
      demo
        ? Promise.resolve<Page<AdminMeeting>>({ items: [], next_cursor: null })
        : apiFetch<Page<AdminMeeting>>('/api/v1/admin/meetings', {
            signal,
            query: { status: status || undefined, limit: 20, cursor: pageParam },
          }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    retry: false,
  });
  const health = useQuery({
    queryKey: ['admin', 'health', demo],
    queryFn: ({ signal }) =>
      demo
        ? Promise.resolve<Health>({
            status: 'degraded',
            checked_at: '2026-11-12T00:00:00Z',
            components: {
              'meeting-service': { status: 'ok' },
              'emotion-ml-service': { status: 'down' },
            },
          })
        : apiFetch<Health>('/api/v1/admin/health', { signal }),
    retry: false,
  });
  const rows = meetings.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <>
      <section aria-labelledby="admin-meetings" className="flex flex-col gap-4">
        <h2 id="admin-meetings" className="text-lg font-semibold">
          Встречи системы
        </h2>
        <label className="flex items-center gap-3 text-sm">
          Статус встреч
          <select
            className="rounded-md border bg-background p-2"
            value={status}
            onChange={(e) => setStatus(e.target.value as MeetingStatus | '')}
          >
            <option value="">Все</option>
            {Object.entries(statusLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {meetings.isPending ? (
          <p role="status">Загружаем встречи…</p>
        ) : meetings.isError ? (
          <p role="alert">{unavailable(meetings.error)}</p>
        ) : rows.length === 0 ? (
          <p>Встреч с выбранным статусом нет.</p>
        ) : (
          <ul className="divide-y rounded-xl border">
            {rows.map((meeting) => (
              <li key={meeting.id} className="flex flex-wrap justify-between gap-3 p-4">
                <span>
                  {meeting.title} · {statusLabels[meeting.status]}
                </span>
                <span>В комнате: {meeting.online_participants}</span>
              </li>
            ))}
          </ul>
        )}
        <div className="flex gap-2">
          <Button
            variant="outline"
            disabled={meetings.isFetching}
            onClick={() => void meetings.refetch()}
          >
            Обновить встречи
          </Button>
          {meetings.hasNextPage && (
            <Button
              variant="outline"
              disabled={meetings.isFetchingNextPage}
              onClick={() => void meetings.fetchNextPage()}
            >
              Ещё встречи
            </Button>
          )}
        </div>
      </section>
      <section aria-labelledby="admin-health" className="flex flex-col gap-4">
        <h2 id="admin-health" className="text-lg font-semibold">
          Состояние сервисов
        </h2>
        {health.isPending ? (
          <p role="status">Проверяем состояние…</p>
        ) : health.isError ? (
          <p role="alert">{unavailable(health.error)}</p>
        ) : (
          <>
            <p>
              Общее состояние: {healthLabels[health.data.status]}. Проверено:{' '}
              {new Date(health.data.checked_at).toLocaleString('ru-RU')}
            </p>
            <dl className="grid gap-3 sm:grid-cols-2">
              {Object.entries(health.data.components).map(([name, component]) => (
                <div key={name} className="rounded-lg border p-3">
                  <dt className="font-medium">{name}</dt>
                  <dd>
                    {healthLabels[component.status]}
                    {component.consumer_lag_s !== undefined &&
                      ` · Отставание: ${component.consumer_lag_s} с`}
                    {component.rooms !== undefined && ` · Комнат: ${component.rooms}`}
                    {component.participants !== undefined &&
                      ` · Участников: ${component.participants}`}
                    {component.last_heartbeat &&
                      ` · Последний сигнал: ${new Date(component.last_heartbeat).toLocaleString('ru-RU')}`}
                  </dd>
                </div>
              ))}
            </dl>
          </>
        )}
        <Button
          variant="outline"
          className="self-start"
          disabled={health.isFetching}
          onClick={() => void health.refetch()}
        >
          Обновить состояние
        </Button>
      </section>
    </>
  );
}
