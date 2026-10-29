import { ApiError } from '@/shared/api/problem';

import { MEETING_ERROR_CODES } from '@/shared/api/meetings';

import { meetingErrorMessage } from './errors';

const err = (code: string, extra: Partial<ConstructorParameters<typeof ApiError>[0]> = {}) =>
  new ApiError({ status: 409, code, message: code, ...extra });

describe('meetingErrorMessage', () => {
  it('у каждого кода реестра есть русское сообщение, а не общая заглушка', () => {
    const generic = meetingErrorMessage(err('что-то-новое'), 'сделать');
    for (const code of Object.keys(MEETING_ERROR_CODES)) {
      if (code === 'internal_error') continue; // непредвиденная ошибка – общий текст с кодом обращения
      const text = meetingErrorMessage(err(code, { retryAfter: 30 }), 'сделать');
      expect(text, code).not.toBe(generic);
      expect(text, code).toMatch(/[а-яё]/i);
    }
  });

  it('общий текст называет действие и код обращения', () => {
    expect(
      meetingErrorMessage(err('internal_error', { requestId: 'req-7' }), 'создать встречу'),
    ).toBe('Не удалось создать встречу. Повторите попытку позже. Код обращения: req-7.');
  });

  it('429 с Retry-After называет время ожидания', () => {
    expect(meetingErrorMessage(err('too_many_requests', { retryAfter: 45 }))).toContain(
      '45 секунд',
    );
  });

  it('сбой сети и не-ApiError', () => {
    expect(meetingErrorMessage(err('network_error', { status: 0 }))).toMatch(
      /связаться с сервером/,
    );
    expect(meetingErrorMessage(new Error('x'))).toMatch(/Что-то пошло не так/);
  });
});
