import type { User } from '@/shared/api/types';

import { MOCK_ORGANIZER_NAME } from './data';

/**
 * Текущий пользователь на тестовых данных. Роль задается переменной VITE_MOCK_ROLE
 * (organizer | admin, по умолчанию organizer); в EMO-40 заменяется AuthProvider.
 */
export function getMockUser(): User {
  const role = import.meta.env.VITE_MOCK_ROLE === 'admin' ? 'admin' : 'organizer';
  return { id: 'u-mock', email: 'ivan@example.ru', display_name: MOCK_ORGANIZER_NAME, role };
}
