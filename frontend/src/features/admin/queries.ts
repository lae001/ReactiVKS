import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';

import type { Page } from '@/shared/api/meetings';

import { type AdminUser, adminUsersApi, type UserStatus } from './api';

export const USERS_PAGE_SIZE = 20;

export interface UsersFilters {
  q?: string;
  status?: UserStatus;
}

const usersKey = ['admin', 'users'] as const;

export function useAdminUsers(filters: UsersFilters) {
  return useInfiniteQuery({
    queryKey: [...usersKey, filters],
    queryFn: ({ pageParam, signal }) =>
      adminUsersApi.list({ ...filters, limit: USERS_PAGE_SIZE, cursor: pageParam }, signal),
    placeholderData: keepPreviousData,
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: Page<AdminUser>) => last.next_cursor ?? undefined,
    retry: false,
  });
}

export function useSetUserStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: UserStatus }) =>
      adminUsersApi.setStatus(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}
