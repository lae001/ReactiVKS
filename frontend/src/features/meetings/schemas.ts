import { z } from 'zod';

/** Форма создания встречи по контракту POST /meetings (docs/api/rest-api.md). */
export const meetingFormSchema = z.object({
  title: z.string().trim().min(1, 'Укажите название встречи').max(200, 'Не длиннее 200 символов'),
  /** Значение поля datetime-local; пусто – встреча «сейчас» (scheduled_at = null) */
  scheduled_at: z
    .string()
    .refine((v) => v === '' || !Number.isNaN(Date.parse(v)), 'Проверьте дату и время'),
  analysis_enabled: z.boolean(),
  analysis_fps: z.number().int().min(2).max(5),
});
export type MeetingFormValues = z.infer<typeof meetingFormSchema>;

/** Тело запроса POST /meetings. */
export function toCreateRequest(values: MeetingFormValues) {
  return {
    title: values.title.trim(),
    scheduled_at: values.scheduled_at ? new Date(values.scheduled_at).toISOString() : null,
    analysis_enabled: values.analysis_enabled,
    analysis_fps: values.analysis_fps,
  };
}

/** ISO-время сервера → значение поля datetime-local (локальное время браузера). */
export function toDatetimeLocal(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
