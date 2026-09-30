import { Link } from 'react-router';

import { paths } from '@/shared/config/routes';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { Label } from '@/shared/ui/label';

/** UC-1. Вход организатора. Логика формы и запрос к auth-service – EMO-39, EMO-40. */
export function LoginPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h1 className="text-2xl font-semibold tracking-tight">Вход</h1>
        <p className="text-sm text-muted-foreground">
          Для организаторов встреч. Участникам достаточно ссылки-приглашения.
        </p>
      </div>
      <form className="flex flex-col gap-4" onSubmit={(e) => e.preventDefault()}>
        <div className="flex flex-col gap-2">
          <Label htmlFor="email">Электронная почта</Label>
          <Input id="email" type="email" autoComplete="email" placeholder="name@example.ru" />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="password">Пароль</Label>
          <Input id="password" type="password" autoComplete="current-password" />
        </div>
        <Button type="submit" disabled title="Подключается в спринте 2 (EMO-39)">
          Войти
        </Button>
      </form>
      <p className="text-sm text-muted-foreground">
        Нет аккаунта?{' '}
        <Link to={paths.register} className="font-medium text-primary hover:underline">
          Зарегистрироваться
        </Link>
      </p>
    </div>
  );
}
