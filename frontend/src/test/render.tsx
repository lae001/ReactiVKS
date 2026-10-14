import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';

import { routes } from '@/app/routes';
import { AuthProvider } from '@/features/auth/AuthProvider';
import { useSessionStore } from '@/shared/api/session';
import type { User } from '@/shared/api/types';

/**
 * Рисует приложение целиком (провайдеры + маршруты) по адресу `path`.
 * `user` – сразу вошедший пользователь; без него AuthProvider сам делает POST /auth/refresh,
 * и тест должен задать ответ через api-mocks.
 */
export function renderApp(path: string, options: { user?: User; state?: unknown } = {}) {
  if (options.user) {
    useSessionStore.setState({
      status: 'authenticated',
      accessToken: 'access-1',
      user: options.user,
    });
  }
  const router = createMemoryRouter(routes, {
    initialEntries: [{ pathname: path, state: options.state }],
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  );
  return router;
}
