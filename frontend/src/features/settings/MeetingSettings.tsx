import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { meetingKeys, useSettings } from '@/features/meetings/queries';
import { meetingErrorMessage } from '@/features/meetings/errors';
import { meetingsApi } from '@/shared/api/meetings';
import type { Settings } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';

export function MeetingSettings() {
  const query = useSettings();
  return (
    <section
      className="flex flex-col gap-4 rounded-xl border p-6"
      aria-labelledby="meeting-settings-title"
    >
      <h2 id="meeting-settings-title" className="text-lg font-semibold">
        Настройки новых встреч
      </h2>
      <p className="text-sm text-muted-foreground">
        Применяются к новым встречам. Каждый участник самостоятельно решает, давать ли согласие на
        анализ.
      </p>
      {query.isPending ? (
        <p role="status">Загружаем настройки…</p>
      ) : query.isError ? (
        <div role="alert">
          {meetingErrorMessage(query.error, 'загрузить настройки')}{' '}
          <Button variant="outline" onClick={() => void query.refetch()}>
            Повторить
          </Button>
        </div>
      ) : (
        <SettingsForm initial={query.data} />
      )}
    </section>
  );
}

function SettingsForm({ initial }: { initial: Settings }) {
  const client = useQueryClient();
  const [enabled, setEnabled] = useState(initial.analysis_enabled_default);
  const [fps, setFps] = useState(String(initial.analysis_fps_default));
  const [error, setError] = useState('');
  const save = useMutation({
    mutationFn: (settings: Settings) => meetingsApi.putSettings(settings),
    onSuccess: (settings) => {
      client.setQueryData(meetingKeys.settings, settings);
      setEnabled(settings.analysis_enabled_default);
      setFps(String(settings.analysis_fps_default));
    },
  });
  return (
    <form
      className="flex flex-col items-start gap-4"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        setError('');
        const value = Number(fps);
        if (!Number.isInteger(value) || value < 2 || value > 5) {
          setError('Укажите целое число от 2 до 5.');
          return;
        }
        save.mutate({ analysis_enabled_default: enabled, analysis_fps_default: value });
      }}
    >
      <label className="flex items-center gap-3 text-sm">
        <input
          type="checkbox"
          className="size-5 accent-primary"
          checked={enabled}
          disabled={save.isPending}
          onChange={(e) => {
            setEnabled(e.target.checked);
            save.reset();
          }}
        />
        Включать анализ в новых встречах
      </label>
      <label className="flex flex-col gap-2 text-sm">
        Частота анализа по умолчанию
        <Input
          type="number"
          min={2}
          max={5}
          step={1}
          value={fps}
          disabled={save.isPending}
          onChange={(e) => {
            setFps(e.target.value);
            setError('');
            save.reset();
          }}
          aria-invalid={Boolean(error)}
        />
      </label>
      <Button disabled={save.isPending} type="submit">
        Сохранить настройки встреч
      </Button>
      {error && (
        <p role="alert" className="text-destructive">
          {error}
        </p>
      )}
      {save.isError && (
        <p role="alert" className="text-destructive">
          {save.error instanceof ApiError && save.error.status === 422
            ? 'Сервер отклонил настройки. Частота должна быть целым числом от 2 до 5. Изменения не сохранены.'
            : meetingErrorMessage(save.error, 'сохранить настройки')}
        </p>
      )}
      {save.isSuccess && <p role="status">Настройки встреч сохранены.</p>}
    </form>
  );
}
