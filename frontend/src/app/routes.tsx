import { Navigate, type RouteObject } from 'react-router';

import { AppLayout } from '@/app/layouts/AppLayout';
import { AuthLayout } from '@/app/layouts/AuthLayout';
import { GuestOnly, RequireAuth, RequireRole, RequireRoomAccess } from '@/features/auth/guards';
import { AdminPage } from '@/pages/AdminPage';
import { JoinPage } from '@/pages/JoinPage';
import { LoginPage } from '@/pages/LoginPage';
import { MeetingNewPage } from '@/pages/MeetingNewPage';
import { MeetingPage } from '@/pages/MeetingPage';
import { MeetingsPage } from '@/pages/MeetingsPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { RegisterPage } from '@/pages/RegisterPage';
import { SettingsPage } from '@/pages/SettingsPage';

/**
 * Маршруты приложения (docs/frontend/README.md). Страницы организатора закрыты RequireAuth,
 * /admin – еще и RequireRole('admin'); /login и /register доступны только без сессии (GuestOnly).
 * Тяжелые страницы (комната с LiveKit SDK) загружаются лениво.
 */
export const routes: RouteObject[] = [
  { index: true, element: <Navigate to="/meetings" replace /> },
  {
    element: <GuestOnly />,
    children: [
      {
        element: <AuthLayout />,
        children: [
          { path: 'login', element: <LoginPage /> },
          { path: 'register', element: <RegisterPage /> },
        ],
      },
    ],
  },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: 'meetings', element: <MeetingsPage /> },
          { path: 'meetings/new', element: <MeetingNewPage /> },
          { path: 'meetings/:id', element: <MeetingPage /> },
          { path: 'settings', element: <SettingsPage /> },
          {
            element: <RequireRole roles={['admin']} />,
            children: [{ path: 'admin', element: <AdminPage /> }],
          },
        ],
      },
    ],
  },
  {
    element: <RequireRoomAccess />,
    children: [
      {
        path: 'room/:meetingId',
        lazy: async () => ({ Component: (await import('@/pages/RoomPage')).default }),
      },
    ],
  },
  { path: 'j/:inviteCode', element: <JoinPage /> },
  ...(import.meta.env.DEV
    ? [
        {
          path: 'dev/ui',
          lazy: async () => ({ Component: (await import('@/pages/dev/UiKitPage')).default }),
        },
        {
          path: 'dev/livekit',
          lazy: async () => ({
            Component: (await import('@/pages/dev/LivekitSandboxPage')).default,
          }),
        },
      ]
    : []),
  { path: '*', element: <NotFoundPage /> },
];
