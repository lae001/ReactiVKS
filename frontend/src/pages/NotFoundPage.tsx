import { Link } from 'react-router';

import { paths } from '@/shared/config/routes';
import { Wordmark } from '@/shared/ui/brand';
import { Button } from '@/shared/ui/button';

export function NotFoundPage() {
  return (
    <div className="flex min-h-dvh flex-col items-start justify-center gap-6 px-6 md:px-16">
      <Wordmark />
      <h1 className="text-2xl font-semibold tracking-tight">Такой страницы нет</h1>
      <p className="max-w-md text-muted-foreground">
        Возможно, ссылка устарела или в ней опечатка. Если вас пригласили на встречу, попросите
        организатора прислать ссылку еще раз.
      </p>
      <Button asChild variant="outline">
        <Link to={paths.meetings}>К списку встреч</Link>
      </Button>
    </div>
  );
}
