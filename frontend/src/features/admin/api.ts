import { apiFetch } from '@/shared/api/client';
import { resolveApiMode } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';
import type { Page } from '@/shared/api/meetings';

/** `AdminUser` контракта: GET /admin/users (docs/api/rest-api.md, раздел 2). */
export interface AdminUser {
  id: string;
  email: string;
  display_name: string;
  role: 'organizer' | 'admin';
  status: 'active' | 'blocked';
  created_at: string;
  last_login_at: string | null;
}

export type UserStatus = AdminUser['status'];

export interface AdminUsersParams {
  q?: string;
  status?: UserStatus;
  limit?: number;
  cursor?: string;
}

export interface AdminUsersApi {
  list(params: AdminUsersParams, signal?: AbortSignal): Promise<Page<AdminUser>>;
  setStatus(id: string, status: UserStatus): Promise<AdminUser>;
}

const BASE = '/api/v1/admin/users';

/** Настоящий auth-service. Смену роли и удаление пользователей интерфейс пока не использует. */
export const httpAdminUsersApi: AdminUsersApi = {
  list: (params, signal) =>
    apiFetch<Page<AdminUser>>(BASE, {
      query: {
        q: params.q,
        status: params.status,
        limit: params.limit === undefined ? undefined : Math.min(Math.max(params.limit, 1), 100),
        cursor: params.cursor,
      },
      signal,
    }),
  setStatus: (id, status) =>
    apiFetch<AdminUser>(`${BASE}/${encodeURIComponent(id)}`, { method: 'PATCH', body: { status } }),
};

function seedUser(
  n: number,
  display_name: string,
  email: string,
  role: AdminUser['role'],
  status: UserStatus,
  last_login_at: string | null,
): AdminUser {
  return {
    id: `u-${n}`,
    email,
    display_name,
    role,
    status,
    created_at: '2026-09-15T10:00:00Z',
    last_login_at,
  };
}

const SEED: AdminUser[] = [
  seedUser(1, 'Иван Петров', 'ivan@example.ru', 'admin', 'active', '2026-11-20T09:00:00Z'),
  seedUser(2, 'Анна Смирнова', 'anna@example.ru', 'organizer', 'active', '2026-11-19T15:30:00Z'),
  seedUser(3, 'Олег Кузнецов', 'oleg@example.ru', 'organizer', 'blocked', '2026-10-02T08:10:00Z'),
  seedUser(4, 'Мария Орлова', 'maria@example.ru', 'organizer', 'active', null),
];

/** Мок для режима `mock`: данные в памяти, первый пользователь (администратор) – «вы». */
export function createMockAdminUsersApi(): AdminUsersApi {
  const users = SEED.map((u) => ({ ...u }));
  return {
    async list({ q, status }) {
      const text = q?.trim().toLowerCase();
      const items = users
        .filter((u) => !status || u.status === status)
        .filter(
          (u) =>
            !text ||
            u.email.toLowerCase().includes(text) ||
            u.display_name.toLowerCase().includes(text),
        )
        .map((u) => ({ ...u }));
      return { items, next_cursor: null };
    },
    async setStatus(id, status) {
      const user = users.find((u) => u.id === id);
      if (!user) {
        throw new ApiError({ status: 404, code: 'not_found', message: 'Пользователя нет' });
      }
      if (user.role === 'admin' && status === 'blocked') {
        throw new ApiError({ status: 409, code: 'last_admin', message: 'last_admin' });
      }
      user.status = status;
      return { ...user };
    },
  };
}

const mock = createMockAdminUsersApi();

/** Режим читается при вызове (как у changePassword), чтобы его можно было подменить в тесте. */
export const adminUsersApi: AdminUsersApi = {
  list: (params, signal) =>
    (resolveApiMode(import.meta.env.VITE_API_MODE) === 'http' ? httpAdminUsersApi : mock).list(
      params,
      signal,
    ),
  setStatus: (id, status) =>
    (resolveApiMode(import.meta.env.VITE_API_MODE) === 'http' ? httpAdminUsersApi : mock).setStatus(
      id,
      status,
    ),
};
