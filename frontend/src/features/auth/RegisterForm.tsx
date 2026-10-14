import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';

import { ApiError, fieldOf } from '@/shared/api/problem';
import { Button } from '@/shared/ui/button';
import { Field, FormError } from '@/shared/ui/field';

import { useAuth } from './auth-context';
import { registerErrorMessage, serverFieldMessage } from './errors';
import { PASSWORD_MIN, type RegisterValues, registerSchema } from './schemas';

const FIELDS = ['display_name', 'email', 'password'] as const;

/** Форма регистрации. Успех = регистрация и автоматический вход; дальше работает GuestOnly. */
export function RegisterForm() {
  const { register: signUp } = useAuth();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await signUp(values);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === 'email_taken') {
          setError('email', {
            message: 'Эта почта уже зарегистрирована. Войдите или укажите другую.',
          });
          return;
        }
        if (error.code === 'validation_error') {
          let shown = false;
          for (const issue of error.errors) {
            const field = fieldOf(issue);
            const known = FIELDS.find((f) => f === field);
            if (known) {
              setError(known, { message: serverFieldMessage(known) });
              shown = true;
            }
          }
          if (shown) return;
        }
      }
      setFormError(registerErrorMessage(error));
    }
  });

  return (
    <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
      <Field
        id="display_name"
        label="Имя"
        autoComplete="name"
        error={errors.display_name?.message}
        {...register('display_name')}
      />
      <Field
        id="email"
        label="Электронная почта"
        type="email"
        autoComplete="email"
        placeholder="name@example.ru"
        error={errors.email?.message}
        {...register('email')}
      />
      <Field
        id="password"
        label="Пароль"
        type="password"
        autoComplete="new-password"
        hint={`От ${PASSWORD_MIN} символов, с буквой и цифрой`}
        error={errors.password?.message}
        {...register('password')}
      />
      {formError ? <FormError>{formError}</FormError> : null}
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Создаем аккаунт…' : 'Создать аккаунт'}
      </Button>
    </form>
  );
}
