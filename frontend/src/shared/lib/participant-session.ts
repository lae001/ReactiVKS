/**
 * Токен гостя (participant_token) на время встречи. По контракту (docs/api/rest-api.md) его выдает
 * POST /join/{invite_code}; REST-вызовы гостя идут с `Authorization: Participant <токен>`,
 * а livekit_token нужен только для медиа. Хранится в sessionStorage вкладки: переживает
 * перезагрузку (повторный вход, отзыв согласия) и не уходит в другие вкладки.
 */
const KEY = 'vks_participant_token';
const SESSION_KEY = 'vks_participant_session';

/** Кто и в какую встречу вошел в этой вкладке: по этому лобби узнает «своего» участника и не заводит второго. */
export interface ParticipantSession {
  token: string;
  inviteCode: string;
  meetingId: string;
  displayName: string;
  consent: 'granted' | 'denied' | 'revoked' | 'not_required';
}

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

/** Токен и сведения о входе: токен кладется в тот же ключ, что и раньше, остальное – отдельной записью. */
export function setParticipantSession(session: ParticipantSession) {
  setParticipantToken(session.token);
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } catch {
    // хранилище недоступно: повторный вход создаст нового участника
  }
}

/** Вход этой вкладки в встречу по `inviteCode`, если он есть и токен еще тот же; иначе `null`. */
export function getParticipantSession(inviteCode: string): ParticipantSession | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (raw === null) return null;
    const data = JSON.parse(raw) as Partial<ParticipantSession> | null;
    if (
      typeof data?.token === 'string' &&
      typeof data.inviteCode === 'string' &&
      typeof data.meetingId === 'string' &&
      typeof data.displayName === 'string' &&
      typeof data.consent === 'string' &&
      data.inviteCode === inviteCode &&
      data.token === getParticipantToken()
    ) {
      return data as ParticipantSession;
    }
    return null;
  } catch {
    return null;
  }
}

export function clearParticipantToken() {
  try {
    sessionStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(KEY);
  } catch {
    // нечего очищать
  }
}
