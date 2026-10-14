import type { components } from './schema';

/** Тело ошибки application/problem+json (RFC 9457), как его отдает сервер. */
export type Problem = components['schemas']['Problem'];
export type ValidationIssue = components['schemas']['ValidationIssue'];

/**
 * Ошибка обращения к API. `code` – код из реестра docs/api/rest-api.md; для сбоя сети
 * и неожиданного ответа это `network_error` и `unknown_error`.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly errors: ValidationIssue[];
  /** Заголовок Retry-After в секундах (429), если сервер его прислал. */
  readonly retryAfter: number | null;

  constructor(init: {
    status: number;
    code: string;
    message: string;
    requestId?: string | null;
    errors?: ValidationIssue[] | null;
    retryAfter?: number | null;
  }) {
    super(init.message);
    this.name = 'ApiError';
    this.status = init.status;
    this.code = init.code;
    this.requestId = init.requestId ?? null;
    this.errors = init.errors ?? [];
    this.retryAfter = init.retryAfter ?? null;
  }
}

/** Retry-After бывает числом секунд или датой HTTP; нужное нам – секунды. */
export function parseRetryAfter(value: string | null, now = Date.now()): number | null {
  if (!value) return null;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return Math.ceil(seconds);
  const date = Date.parse(value);
  return Number.isNaN(date) ? null : Math.max(0, Math.ceil((date - now) / 1000));
}

/** Разбирает неуспешный ответ в ApiError; не-JSON тело (например, ответ прокси) не ломает разбор. */
export async function toApiError(response: Response): Promise<ApiError> {
  const retryAfter = parseRetryAfter(response.headers.get('Retry-After'));
  let problem: Partial<Problem> = {};
  try {
    problem = (await response.json()) as Partial<Problem>;
  } catch {
    // тело не JSON – остаемся с кодом по статусу
  }
  return new ApiError({
    status: response.status,
    code: problem.code ?? 'unknown_error',
    message: problem.detail ?? problem.title ?? `HTTP ${response.status}`,
    requestId: problem.request_id ?? response.headers.get('X-Request-ID'),
    errors: problem.errors,
    retryAfter,
  });
}

/**
 * Имя поля формы по `loc` ошибки валидации: ["body", "display_name"] → "display_name".
 * Ошибки вне тела запроса (query, path) к полям формы не относятся.
 */
export function fieldOf(issue: ValidationIssue): string | null {
  const [where, field] = issue.loc;
  return where === 'body' && typeof field === 'string' ? field : null;
}
