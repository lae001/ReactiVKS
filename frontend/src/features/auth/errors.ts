import { ApiError } from '@/shared/api/problem';

/** «через 45 секунд», «через 5 минут» – время из Retry-After. */
export function formatWait(seconds: number): string {
  if (seconds < 60) return `${seconds} ${plural(seconds, 'секунду', 'секунды', 'секунд')}`;
  const minutes = Math.ceil(seconds / 60);
  return `${minutes} ${plural(minutes, 'минуту', 'минуты', 'минут')}`;
}

function plural(n: number, one: string, few: string, many: string): string {
  const mod100 = n % 100;
  const mod10 = n % 10;
  if (mod100 >= 11 && mod100 <= 14) return many;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
}

function tooManyRequests(error: ApiError, action: string): string {
  const wait = error.retryAfter
    ? ` Повторите через ${formatWait(error.retryAfter)}.`
    : ' Подождите немного.';
  return `Слишком много попыток ${action}.${wait}`;
}

function withRequestId(message: string, error: ApiError): string {
  return error.requestId ? `${message} Код обращения: ${error.requestId}.` : message;
}

const NETWORK = 'Не удалось связаться с сервером. Проверьте соединение и повторите.';

/** Сообщение под формой входа по коду ошибки (docs/api/rest-api.md, реестр кодов). */
export function loginErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Что-то пошло не так. Повторите попытку.';
  switch (error.code) {
    case 'invalid_credentials':
      return 'Неверная почта или пароль. Проверьте данные и попробуйте снова.';
    case 'user_blocked':
      return 'Аккаунт заблокирован. Обратитесь к администратору системы.';
    case 'too_many_requests':
      return tooManyRequests(error, 'войти');
    case 'network_error':
      return NETWORK;
    case 'validation_error':
      return 'Проверьте почту и пароль: данные в неверном формате.';
    default:
      return withRequestId('Не удалось войти. Повторите попытку позже.', error);
  }
}

/** Сообщение под формой регистрации для ошибок, не привязанных к полю. */
export function registerErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Что-то пошло не так. Повторите попытку.';
  switch (error.code) {
    case 'not_found':
      return 'Регистрация сейчас закрыта. Обратитесь к администратору системы.';
    case 'too_many_requests':
      return tooManyRequests(error, 'зарегистрироваться');
    case 'network_error':
      return NETWORK;
    case 'user_blocked':
      return 'Аккаунт создан, но заблокирован. Обратитесь к администратору системы.';
    default:
      return withRequestId('Не удалось создать аккаунт. Повторите попытку позже.', error);
  }
}

export function genericErrorMessage(error: unknown, action: string): string {
  if (error instanceof ApiError) {
    if (error.code === 'network_error') return NETWORK;
    if (error.code === 'too_many_requests') return tooManyRequests(error, action);
    return withRequestId(`Не удалось ${action}. Повторите попытку позже.`, error);
  }
  return `Не удалось ${action}. Повторите попытку.`;
}

const FIELD_MESSAGES: Record<string, string> = {
  email: 'Проверьте адрес: он должен выглядеть как name@example.ru',
  password: 'Проверьте пароль: от 8 символов, с буквой и цифрой, без пробелов по краям',
  display_name: 'Проверьте имя: от 1 до 100 символов',
};

/** Сообщения сервера (422) на английском; пользователю показываем свой текст по имени поля. */
export function serverFieldMessage(field: string): string {
  return FIELD_MESSAGES[field] ?? 'Проверьте значение этого поля';
}
