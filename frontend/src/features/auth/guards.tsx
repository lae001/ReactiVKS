import { Link, Navigate, Outlet, useLocation } from 'react-router';

import type { UserRole } from '@/shared/api/types';
import { paths } from '@/shared/config/routes';
import { readRoomEntry } from '@/shared/lib/room-entry';
import { Button } from '@/shared/ui/button';

import { useAuth } from './auth-context';

function SessionCheck() {
  return (
    <div className="grid min-h-dvh place-items-center text-sm text-muted-foreground" role="status">
      Проверяем вход…
    </div>
  );
}

function SessionUnavailable() {
  const { retry } = useAuth();
  return (
    <div className="grid min-h-dvh place-items-center px-6">
      <div className="flex max-w-sm flex-col items-start gap-4" role="alert">
        <h1 className="text-xl font-semibold">Нет связи с сервером</h1>
        <p className="text-sm text-muted-foreground">
          Не удалось проверить вход. Проверьте соединение и повторите.
        </p>
        <Button onClick={() => void retry()}>Повторить</Button>
      </div>
    </div>
  );
}

/** Маршруты для вошедших: гостя отправляет на /login и запоминает, куда он шел. */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === 'unknown') return <SessionCheck />;
  if (status === 'unavailable') return <SessionUnavailable />;
  if (status === 'anonymous') {
    return (
      <Navigate to={paths.login} replace state={{ from: location.pathname + location.search }} />
    );
  }
  return <Outlet />;
}

/**
 * Комната: организатор и администратор входят по сессии, гость – из лобби (/j/:inviteCode),
 * которое передает вход через state навигации. Пока нет meeting-service, это единственный признак гостя;
 * настоящий допуск даст participant_token / токен LiveKit (EMO-74, EMO-89).
 */
export function RequireRoomAccess() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === 'anonymous' && readRoomEntry(location.state)?.role === 'guest') return <Outlet />;
  return <RequireAuth />;
}

/** Маршруты для определенных ролей. Ставится внутри RequireAuth. */
export function RequireRole({ roles }: { roles: UserRole[] }) {
  const { user } = useAuth();
  if (user && !roles.includes(user.role)) {
    return (
      <div className="flex max-w-lg flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Нет доступа</h1>
        <p className="text-muted-foreground">
          Этот раздел доступен администраторам. Вернитесь к списку встреч.
        </p>
        <Button asChild className="self-start">
          <Link to={paths.meetings}>К встречам</Link>
        </Button>
      </div>
    );
  }
  return <Outlet />;
}

/** /login и /register: вошедшего пользователя возвращаем в приложение. */
export function GuestOnly() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === 'unknown') return <SessionCheck />;
  if (status === 'authenticated') {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from ?? paths.meetings} replace />;
  }
  return <Outlet />;
}
