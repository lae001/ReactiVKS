/**
 * Токен гостя (participant_token) на время встречи. По контракту (docs/api/rest-api.md) его выдает
 * POST /join/{invite_code}; REST-вызовы гостя идут с `Authorization: Participant <токен>`,
 * а livekit_token нужен только для медиа. Хранится в sessionStorage вкладки: переживает
 * перезагрузку (повторный вход, отзыв согласия) и не уходит в другие вкладки.
 */
const KEY = 'vks_participant_token';

export function getParticipantToken(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setParticipantToken(token: string) {
  try {
    sessionStorage.setItem(KEY, token);
  } catch {
    // хранилище недоступно (приватный режим): гость не сможет перезайти после перезагрузки
  }
}

export function clearParticipantToken() {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // нечего очищать
  }
}
