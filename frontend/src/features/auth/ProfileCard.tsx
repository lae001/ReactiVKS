import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';

import { ApiError, fieldOf } from '@/shared/api/problem';
import { updateSessionUser } from '@/shared/api/session';
import { Button } from '@/shared/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card';
import { Field, FormError } from '@/shared/ui/field';

import { fetchProfile, updateProfile } from './api';
import { genericErrorMessage, serverFieldMessage } from './errors';
import { type ProfileValues, profileSchema } from './schemas';

/** Профиль: GET и PATCH /users/me. Меняется только отображаемое имя, почта – для чтения. */
export function ProfileCard() {
  const profile = useQuery({ queryKey: ['profile'], queryFn: fetchProfile });
  const [saved, setSaved] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isDirty },
  } = useForm<ProfileValues>({ resolver: zodResolver(profileSchema) });

  useEffect(() => {
    if (profile.data) reset({ display_name: profile.data.display_name });
  }, [profile.data, reset]);

  const save = useMutation({
    mutationFn: updateProfile,
    onSuccess: (user) => {
      updateSessionUser(user);
      profile.refetch().catch(() => undefined);
      reset({ display_name: user.display_name });
      setSaved(true);
    },
  });

  const onSubmit = handleSubmit(async (values) => {
    setSaved(false);
    setFormError(null);
    try {
      await save.mutateAsync(values);
    } catch (error) {
      if (error instanceof ApiError && error.code === 'validation_error') {
        if (error.errors.some((issue) => fieldOf(issue) === 'display_name')) {
          setError('display_name', { message: serverFieldMessage('display_name') });
          return;
        }
      }
      setFormError(genericErrorMessage(error, 'сохранить профиль'));
    }
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Профиль</CardTitle>
        <CardDescription>Имя видят участники ваших встреч и получатели отчетов.</CardDescription>
      </CardHeader>
      <CardContent>
        {profile.isPending ? (
          <p className="text-sm text-muted-foreground" role="status">
            Загружаем профиль…
          </p>
        ) : profile.isError ? (
          <div className="flex flex-col items-start gap-3">
            <FormError>{genericErrorMessage(profile.error, 'загрузить профиль')}</FormError>
            <Button variant="outline" onClick={() => void profile.refetch()}>
              Повторить
            </Button>
          </div>
        ) : (
          <form className="flex max-w-sm flex-col gap-4" onSubmit={onSubmit} noValidate>
            <Field
              id="profile-email"
              label="Электронная почта"
              value={profile.data.email}
              readOnly
            />
            <Field
              id="profile-name"
              label="Имя"
              autoComplete="name"
              error={errors.display_name?.message}
              {...register('display_name')}
            />
            {formError ? <FormError>{formError}</FormError> : null}
            {saved ? (
              <p role="status" className="text-sm text-muted-foreground">
                Имя сохранено. В токене оно обновится при следующем входе.
              </p>
            ) : null}
            <Button type="submit" className="self-start" disabled={!isDirty || save.isPending}>
              {save.isPending ? 'Сохраняем…' : 'Сохранить имя'}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
