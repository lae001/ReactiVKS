import { useQueryClient } from '@tanstack/react-query';
import { type ReactNode, useEffect, useMemo } from 'react';

import { restoreSession, useSessionStore } from '@/shared/api/session';

import * as authApi from './api';
import { AuthContext, type AuthContextValue } from './auth-context';

/**
 * Сессия приложения. При старте выясняет, жива ли cookie vks_refresh (POST /auth/refresh);
 * если состояние уже известно (например, задано в тесте) – не вмешивается.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const status = useSessionStore((s) => s.status);
  const user = useSessionStore((s) => s.user);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (useSessionStore.getState().status === 'unknown') void restoreSession();
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      login: authApi.login,
      register: async (data) => {
        await authApi.register(data);
        return authApi.login({ email: data.email, password: data.password });
      },
      logout: async () => {
        try {
          await authApi.logout();
        } finally {
          // данные кэша принадлежат прошлому пользователю
          queryClient.clear();
        }
      },
      retry: async () => {
        useSessionStore.setState({ status: 'unknown' });
        await restoreSession();
      },
    }),
    [status, user, queryClient],
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}
