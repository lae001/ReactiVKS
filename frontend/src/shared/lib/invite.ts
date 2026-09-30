/** Формат кода приглашения (docs/api/rest-api.md, схема `Meeting.invite_code`). */
const INVITE_CODE = /^[a-z2-7]{10}$/;

/**
 * Код приглашения из того, что вставил пользователь: полная ссылка
 * `https://…/j/<код>`, путь `/j/<код>` или сам код. null – код не распознан.
 */
export function parseInviteCode(input: string): string | null {
  const value = input.trim();
  const fromPath = /\/j\/([^/?#\s]+)/.exec(value)?.[1];
  const code = (fromPath ?? value).toLowerCase();
  return INVITE_CODE.test(code) ? code : null;
}
