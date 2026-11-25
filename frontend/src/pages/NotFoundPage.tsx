import { Link, useNavigate } from 'react-router';

import { paths } from '@/shared/config/routes';
import { useCanGoBack } from '@/shared/hooks/use-can-go-back';
import { Wordmark } from '@/shared/ui/brand';
import { Button } from '@/shared/ui/button';

export function NotFoundPage() {
  const navigate = useNavigate();
  const canGoBack = useCanGoBack();
  return (
    <div className="flex min-h-dvh flex-col items-start justify-center gap-6 px-6 md:px-16">
      <Wordmark />
      <h1 className="text-2xl font-semibold tracking-tight">Такой страницы нет</h1>
      <p className="max-w-md text-muted-foreground">
        Возможно, ссылка устарела или в ней опечатка. Если вас пригласили на встречу, попросите
        организатора прислать ссылку еще раз.
      </p>
      <div className="flex flex-wrap gap-3">
        <Button asChild variant="outline">
          <Link to={paths.meetings}>К списку встреч</Link>
        </Button>
        {/* вернуться можно только на страницу этого же приложения: после прямой ссылки истории нет */}
        {canGoBack && (
          <Button type="button" variant="ghost" onClick={() => void navigate(-1)}>
            Назад
          </Button>
        )}
      </div>
    </div>
  );
}
