import { useQuery } from '@tanstack/react-query';

import { fetchAuthConfig } from './api';

/** Публичные флаги auth-service. Пока флаги не получены, регистрацию считаем доступной: сервер ответит 404, если нет. */
export function useAuthConfig() {
  const query = useQuery({
    queryKey: ['auth-config'],
    queryFn: fetchAuthConfig,
    staleTime: 5 * 60_000,
  });
  return {
    registrationEnabled: query.data?.registration_enabled ?? true,
    isLoaded: query.isSuccess,
  };
}
