import { Link } from 'react-router';

import { paths } from '@/shared/config/routes';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { Label } from '@/shared/ui/label';

/** UC-1. Регистрация организатора. Валидация (Zod) и отправка – EMO-39. */
export function RegisterPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h1 className="text-2xl font-semibold tracking-tight">Регистрация</h1>
        <p className="text-sm text-muted-foreground">
          Аккаунт нужен, чтобы создавать встречи и получать отчеты.
        </p>
      </div>
      <form className="flex flex-col gap-4" onSubmit={(e) => e.preventDefault()}>
        <div className="flex flex-col gap-2">
          <Label htmlFor="name">Имя</Label>
          <Input id="name" autoComplete="name" />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="email">Электронная почта</Label>
          <Input id="email" type="email" autoComplete="email" placeholder="name@example.ru" />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="password">Пароль</Label>
          <Input id="password" type="password" autoComplete="new-password" />
        </div>
        <Button type="submit" disabled title="Подключается в спринте 2 (EMO-39)">
          Создать аккаунт
        </Button>
      </form>
      <p className="text-sm text-muted-foreground">
        Уже зарегистрированы?{' '}
        <Link to={paths.login} className="font-medium text-primary hover:underline">
          Войти
        </Link>
      </p>
    </div>
  );
}
