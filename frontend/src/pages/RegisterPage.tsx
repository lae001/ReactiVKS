import { Link } from 'react-router';

import { RegisterForm } from '@/features/auth/RegisterForm';
import { useAuthConfig } from '@/features/auth/use-auth-config';
import { paths } from '@/shared/config/routes';

/** UC-1. Регистрация организатора; при выключенной регистрации (GET /auth/config) формы нет. */
export function RegisterPage() {
  const { registrationEnabled } = useAuthConfig();
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h1 className="text-2xl font-semibold tracking-tight">Регистрация</h1>
        <p className="text-sm text-muted-foreground">
          {registrationEnabled
            ? 'Аккаунт нужен, чтобы создавать встречи и получать отчеты.'
            : 'Сейчас регистрация закрыта. Обратитесь к администратору системы, если нужен аккаунт.'}
        </p>
      </div>
      {registrationEnabled ? <RegisterForm /> : null}
      <p className="text-sm text-muted-foreground">
        {registrationEnabled ? 'Уже зарегистрированы? ' : 'Есть аккаунт? '}
        <Link to={paths.login} className="font-medium text-primary hover:underline">
          Войти
        </Link>
      </p>
    </div>
  );
}
