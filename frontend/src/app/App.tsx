import { createBrowserRouter, RouterProvider } from 'react-router';

import { routes } from '@/app/routes';

const router = createBrowserRouter(routes);

/**
 * Корневой компонент. Провайдеры (QueryClientProvider, AuthProvider)
 * добавляются здесь по мере появления: EMO-40.
 */
export function App() {
  return <RouterProvider router={router} />;
}
