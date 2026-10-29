import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useForm } from 'react-hook-form';

import { resolveApiMode } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';
import { clearSession } from '@/shared/api/session';
import { Badge } from '@/shared/ui/badge';
import { Button } from '@/shared/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card';
import { Field, FormError } from '@/shared/ui/field';

import { changePassword } from './api';
import { genericErrorMessage } from './errors';
import { setLoginNotice } from './notices';
import { type ChangePasswordValues, changePasswordSchema, PASSWORD_MIN } from './schemas';

/**
 * Смена пароля. В режиме `http` – POST /users/me/password: сервер завершает все сессии, поэтому после
 * успеха сессия в памяти очищается, и охранник RequireAuth уводит пользователя на /login. В режиме `mock` пароль не меняется:
 * форма и проверки настоящие.
 */
export function PasswordCard() {
  const live = resolveApiMode(import.meta.env.VITE_API_MODE) === 'http';
  const queryClient = useQueryClient();
  const [done, setDone] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ChangePasswordValues>({ resolver: zodResolver(changePasswordSchema) });

  const onSubmit = handleSubmit(async (values) => {
    setDone(false);
    setFormError(null);
    try {
      await changePassword(values);
      reset();
      if (live) {
        // Refresh-токены отозваны сервером: старый access-токен и кэш больше не нужны
        setLoginNotice('password_changed');
        clearSession();
        queryClient.clear();
        return; // на /login уведет RequireAuth
      }
      setDone(true);
    } catch (error) {
      if (error instanceof ApiError && error.code === 'invalid_credentials') {
        setError('current_password', { message: 'Текущий пароль неверный. Введите его еще раз.' });
        return;
      }
      setFormError(genericErrorMessage(error, 'сменить пароль'));
    }
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Пароль {live ? null : <Badge variant="outline">Тестовый режим</Badge>}
        </CardTitle>
        <CardDescription>
          {live
            ? 'После смены пароля все сессии завершатся, и нужно будет войти заново.'
            : 'Тестовый режим: форма-макет, проверки работают, пароль не меняется.'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="flex max-w-sm flex-col gap-4" onSubmit={onSubmit} noValidate>
          <Field
            id="current-password"
            label="Текущий пароль"
            type="password"
            autoComplete="current-password"
            error={errors.current_password?.message}
            {...register('current_password')}
          />
          <Field
            id="new-password"
            label="Новый пароль"
            type="password"
            autoComplete="new-password"
            hint={`От ${PASSWORD_MIN} символов, с буквой и цифрой`}
            error={errors.new_password?.message}
            {...register('new_password')}
          />
          {formError ? <FormError>{formError}</FormError> : null}
          {done ? (
            <p role="status" className="text-sm text-muted-foreground">
              Проверки пройдены. Пароль не изменен: смена пароля подключится вместе с сервером.
            </p>
          ) : null}
          <Button type="submit" variant="outline" className="self-start" disabled={isSubmitting}>
            {isSubmitting ? 'Меняем…' : 'Сменить пароль'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
