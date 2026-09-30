import { Navigate, type RouteObject } from 'react-router-dom'
import { Layout } from './Layout'
import { LoginPage } from '@/pages/LoginPage'
import { RegisterPage } from '@/pages/RegisterPage'
import { MeetingsPage } from '@/pages/MeetingsPage'
import { MeetingNewPage } from '@/pages/MeetingNewPage'
import { MeetingDetailsPage } from '@/pages/MeetingDetailsPage'
import { RoomPage } from '@/pages/RoomPage'
import { LobbyPage } from '@/pages/LobbyPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { AdminPage } from '@/pages/AdminPage'
import { NotFoundPage } from '@/pages/NotFoundPage'

/** Маршруты из docs/frontend/README.md. Guard'ы доступа появятся вместе с auth (спринт 2). */
export const routes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      { path: '/', element: <Navigate to="/meetings" replace /> },
      { path: '/login', element: <LoginPage /> },
      { path: '/register', element: <RegisterPage /> },
      { path: '/meetings', element: <MeetingsPage /> },
      { path: '/meetings/new', element: <MeetingNewPage /> },
      { path: '/meetings/:id', element: <MeetingDetailsPage /> },
      { path: '/room/:meetingId', element: <RoomPage /> },
      { path: '/j/:inviteCode', element: <LobbyPage /> },
      { path: '/settings', element: <SettingsPage /> },
      { path: '/admin', element: <AdminPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
