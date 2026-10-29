import { genericErrorMessage } from '@/features/auth/errors';
import { ApiError } from '@/shared/api/problem';

/** Сообщение по коду ошибки админки пользователей (auth-service, docs/api/rest-api.md). */
export function adminErrorMessage(error: unknown, action: string): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 'last_admin':
        return 'Администратор не может заблокировать себя или последнего администратора.';
      case 'forbidden':
        return 'Недостаточно прав: раздел доступен только администратору.';
      case 'unauthorized':
        return 'Сессия закончилась. Войдите снова.';
      case 'not_found':
        return 'Пользователя уже нет в списке. Обновите страницу.';
      case 'validation_error':
        return 'Сервер не принял запрос. Проверьте поиск и фильтр.';
    }
    if (error.status === 409) {
      return 'Состояние пользователя уже изменилось. Обновите страницу и повторите.';
    }
  }
  return genericErrorMessage(error, action);
}
