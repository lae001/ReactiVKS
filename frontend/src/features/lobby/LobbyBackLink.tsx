import { ArrowLeft } from 'lucide-react';
import { Link, useNavigate } from 'react-router';

import { useAuth } from '@/features/auth/auth-context';
import { paths } from '@/shared/config/routes';
import { useCanGoBack } from '@/shared/hooks/use-can-go-back';
import { Button } from '@/shared/ui/button';

/**
 * «Назад» в лобби и на его экранах-заглушках, чтобы не было тупика. Вошедшему организатору – «К встречам»;
 * иначе, если в истории приложения есть предыдущая страница, – возврат на неё; гость, пришедший по прямой
 * ссылке, возвращаться некуда, и кнопки у него нет.
 */
export function LobbyBackLink() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const canGoBack = useCanGoBack();

  if (user) {
    return (
      <Button asChild variant="ghost" size="sm" className="self-start">
        <Link to={paths.meetings}>
          <ArrowLeft aria-hidden /> К встречам
        </Link>
      </Button>
    );
  }
  if (!canGoBack) return null;
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="self-start"
      onClick={() => void navigate(-1)}
    >
      <ArrowLeft aria-hidden /> Назад
    </Button>
  );
}
