import { z } from 'zod';

/** Политика пароля из docs/api/rest-api.md; сервер проверяет ее всегда, здесь – для быстрой подсказки. */
export const PASSWORD_MIN = 8;
export const PASSWORD_MAX = 128;

export const passwordSchema = z
  .string()
  .min(PASSWORD_MIN, `Минимум ${PASSWORD_MIN} символов`)
  .max(PASSWORD_MAX, `Максимум ${PASSWORD_MAX} символов`)
  .refine((v) => v === v.trim(), 'Уберите пробелы в начале и в конце пароля')
  .refine((v) => /\p{L}/u.test(v), 'Добавьте хотя бы одну букву')
  .refine((v) => /\d/.test(v), 'Добавьте хотя бы одну цифру');

const emailSchema = z
  .string()
  .trim()
  .min(1, 'Укажите электронную почту')
  .max(254, 'Не длиннее 254 символов')
  .pipe(z.email('Проверьте адрес: он должен выглядеть как name@example.ru'));

export const displayNameSchema = z
  .string()
  .trim()
  .min(1, 'Укажите имя')
  .max(100, 'Не длиннее 100 символов');

export const loginSchema = z.object({
  email: emailSchema,
  // политика пароля могла измениться после регистрации – при входе проверяем только наличие
  password: z.string().min(1, 'Введите пароль'),
});
export type LoginValues = z.infer<typeof loginSchema>;

export const registerSchema = z.object({
  display_name: displayNameSchema,
  email: emailSchema,
  password: passwordSchema,
});
export type RegisterValues = z.infer<typeof registerSchema>;

export const profileSchema = z.object({ display_name: displayNameSchema });
export type ProfileValues = z.infer<typeof profileSchema>;

export const changePasswordSchema = z.object({
  current_password: z.string().min(1, 'Введите текущий пароль'),
  new_password: passwordSchema,
});
export type ChangePasswordValues = z.infer<typeof changePasswordSchema>;
