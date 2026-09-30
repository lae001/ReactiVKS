import { ScanFace } from 'lucide-react';

import type { JoinInfo } from '@/shared/api/types';
import { cn } from '@/shared/lib/utils';

import type { ConsentChoice } from './validate';

const OPTIONS: { value: ConsentChoice; title: string; hint: string }[] = [
  {
    value: 'granted',
    title: 'Разрешаю анализ моих эмоций',
    hint: 'Организатор увидит распознанные эмоции во время встречи и в отчете.',
  },
  {
    value: 'denied',
    title: 'Участвую без анализа',
    hint: 'Вас будут видеть и слышать как обычно, эмоции не распознаются.',
  },
];

/**
 * Явное согласие на анализ эмоций (UC-3, 05-security-privacy.md): вариант
 * по умолчанию не выбран, текст уведомления версионируется.
 */
export function ConsentFieldset({
  notice,
  value,
  onChange,
  error,
}: {
  notice: NonNullable<JoinInfo['consent_notice']>;
  value: ConsentChoice | null;
  onChange: (v: ConsentChoice) => void;
  error?: string;
}) {
  return (
    <fieldset
      className="flex flex-col gap-3 rounded-xl border bg-card p-4"
      aria-describedby={error ? 'consent-notice consent-error' : 'consent-notice'}
    >
      <legend className="flex items-center gap-2 px-1 text-sm font-semibold">
        <ScanFace className="size-4 text-primary" aria-hidden />
        Анализ эмоций во встрече
      </legend>
      <p id="consent-notice" className="text-sm leading-relaxed text-muted-foreground">
        {notice.text_md}
      </p>

      <div className="flex flex-col gap-2">
        {OPTIONS.map((o) => (
          <label
            key={o.value}
            className={cn(
              'flex cursor-pointer gap-3 rounded-lg border p-3 transition-colors hover:bg-accent/50',
              value === o.value && 'border-primary bg-accent/60',
              error && 'border-destructive/60',
            )}
          >
            <input
              type="radio"
              name="consent"
              value={o.value}
              checked={value === o.value}
              onChange={() => onChange(o.value)}
              required
              className="mt-0.5 size-4 shrink-0 accent-primary"
            />
            <span className="flex flex-col gap-0.5">
              <span className="text-sm font-medium">{o.title}</span>
              <span className="text-sm text-muted-foreground">{o.hint}</span>
            </span>
          </label>
        ))}
      </div>

      {error && (
        <p id="consent-error" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        Решение можно изменить во время встречи кнопкой «Анализ моих эмоций». Версия уведомления:{' '}
        {notice.version}.
      </p>
    </fieldset>
  );
}
