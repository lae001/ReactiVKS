export type ConsentChoice = 'granted' | 'denied';

export interface JoinForm {
  displayName: string;
  consent: ConsentChoice | null;
  /** Во встрече включен анализ – без явного выбора войти нельзя */
  consentRequired: boolean;
}

export type JoinFormErrors = Partial<Record<'displayName' | 'consent', string>>;

/** Проверки формы лобби – те же, что у POST /join/{invite_code} (docs/api/rest-api.md). */
export function validateJoinForm(form: JoinForm): JoinFormErrors {
  const errors: JoinFormErrors = {};
  const name = form.displayName.trim();
  if (!name) errors.displayName = 'Укажите имя – так вас увидят другие участники.';
  else if (name.length > 64) errors.displayName = 'Имя длиннее 64 символов. Сократите его.';
  if (form.consentRequired && !form.consent) {
    errors.consent = 'Выберите, разрешаете ли вы анализ эмоций. Без выбора войти нельзя.';
  }
  return errors;
}
