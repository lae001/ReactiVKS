import { Link } from 'react-router';

import { useLoginNotice } from '@/features/auth/notices';
import { LoginForm } from '@/features/auth/LoginForm';
import { useAuthConfig } from '@/features/auth/use-auth-config';
import { paths } from '@/shared/config/routes';

/** UC-1. Вход организатора. */
export function LoginPage() {
  const { registrationEnabled } = useAuthConfig();
  const passwordChanged = useLoginNotice((s) => s.notice) === 'password_changed';
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h1 className="text-2xl font-semibold tracking-tight">Вход</h1>
        <p className="text-sm text-muted-foreground">
          Для организаторов встреч. Участникам достаточно ссылки-приглашения.
        </p>
      </div>
      {passwordChanged ? (
        <p role="status" className="rounded-md bg-muted px-3 py-2 text-sm">
          Пароль изменён, войдите снова.
        </p>
      ) : null}
      <LoginForm />
      {registrationEnabled ? (
        <p className="text-sm text-muted-foreground">
          Нет аккаунта?{' '}
          <Link to={paths.register} className="font-medium text-primary hover:underline">
            Зарегистрироваться
          </Link>
        </p>
      ) : null}
    </div>
  );
}
