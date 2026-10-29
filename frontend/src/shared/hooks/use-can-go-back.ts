import { useLocation } from 'react-router';

/**
 * Есть ли в истории этого приложения страница, на которую можно вернуться. React Router даёт первой
 * записи истории ключ `default`: пользователь, пришедший по прямой ссылке (или после перезагрузки),
 * возвращаться никуда не может, и `navigate(-1)` увёл бы его из приложения.
 */
export function useCanGoBack(): boolean {
  return useLocation().key !== 'default';
}
