import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';

import { ApiError } from '@/shared/api/problem';
import { Badge } from '@/shared/ui/badge';
import { Button } from '@/shared/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card';
import { Field, FormError } from '@/shared/ui/field';

import { changePassword } from './api';
import { genericErrorMessage } from './errors';
import { type ChangePasswordValues, changePasswordSchema, PASSWORD_MIN } from './schemas';

/**
 * Смена пароля. Эндпоинт POST /users/me/password в auth-service еще не реализован,
 * поэтому changePassword – мок: форма и проверки настоящие, пароль не меняется.
 */
export function PasswordCard() {
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
          Пароль <Badge variant="outline">Тестовый режим</Badge>
        </CardTitle>
        <CardDescription>
          Сервер пока не умеет менять пароль, поэтому здесь форма-макет: проверки работают, пароль
          не меняется.
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
