import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';

import { ApiError, fieldOf } from '@/shared/api/problem';
import { Button } from '@/shared/ui/button';
import { Field, FormError } from '@/shared/ui/field';

import { useAuth } from './auth-context';
import { loginErrorMessage, serverFieldMessage } from './errors';
import { type LoginValues, loginSchema } from './schemas';

/** Форма входа. После успеха переход выполняет GuestOnly: сессия стала authenticated. */
export function LoginForm() {
  const { login } = useAuth();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await login(values);
    } catch (error) {
      if (error instanceof ApiError && error.code === 'validation_error') {
        const fieldIssues = error.errors.flatMap((issue) => {
          const field = fieldOf(issue);
          return field === 'email' || field === 'password'
            ? [[field, serverFieldMessage(field)] as const]
            : [];
        });
        for (const [field, message] of fieldIssues) setError(field, { message });
        if (fieldIssues.length > 0) return;
      }
      setFormError(loginErrorMessage(error));
    }
  });

  return (
    <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
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
        autoComplete="current-password"
        error={errors.password?.message}
        {...register('password')}
      />
      {formError ? <FormError>{formError}</FormError> : null}
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Входим…' : 'Войти'}
      </Button>
    </form>
  );
}
