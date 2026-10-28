import { formatWait } from '@/features/auth/errors';
import { ApiError } from '@/shared/api/problem';

const NETWORK = 'Не удалось связаться с сервером. Проверьте соединение и повторите.';

/**
 * Сообщение пользователю по коду ошибки meeting-service (docs/api/rest-api.md, реестр кодов).
 * `action` – что пользователь пытался сделать, в форме «не удалось …».
 */
export function meetingErrorMessage(error: unknown, action = 'выполнить действие'): string {
  if (!(error instanceof ApiError)) return 'Что-то пошло не так. Повторите попытку.';
  switch (error.code) {
    case 'network_error':
      return NETWORK;
    case 'unauthorized':
      return 'Сессия закончилась. Войдите снова.';
    case 'forbidden':
      return 'Недостаточно прав для этого действия.';
    case 'user_blocked':
      return 'Ваша учетная запись заблокирована. Обратитесь к администратору системы.';
    case 'not_found':
      return 'Встреча не найдена: возможно, ее удалили.';
    case 'too_many_requests':
      return error.retryAfter
        ? `Слишком много запросов. Повторите через ${formatWait(error.retryAfter)}.`
        : 'Слишком много запросов. Подождите немного.';
    case 'validation_error':
      return 'Проверьте введенные данные.';
    case 'meeting_not_started':
      return 'Встреча еще не началась.';
    case 'meeting_ended':
      return 'Встреча уже завершена.';
    case 'meeting_cancelled':
      return 'Встреча отменена.';
    case 'meeting_full':
      return 'В комнате уже 10 участников – больше войти нельзя.';
    case 'meeting_not_editable':
      return 'Параметры начатой встречи изменить нельзя – только название.';
    case 'consent_required':
      return 'Выберите вариант согласия на анализ эмоций, чтобы войти.';
    case 'notice_outdated':
      return 'Уведомление об анализе эмоций обновилось. Прочитайте его и выберите вариант заново.';
    case 'analysis_disabled':
      return 'В этой встрече анализ эмоций выключен, согласие менять не нужно.';
    case 'participant_removed':
      return 'Организатор удалил вас из встречи, вернуться по этой ссылке нельзя.';
    case 'idempotency_key_reused':
      return 'Этот запрос уже отправлялся с другими данными. Обновите страницу и повторите.';
    case 'livekit_unavailable':
      return 'Видеосервер сейчас недоступен. Повторите через минуту.';
    default:
      return `Не удалось ${action}. Повторите попытку позже.${error.requestId ? ` Код обращения: ${error.requestId}.` : ''}`;
  }
}
