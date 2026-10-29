import { ApiError } from '@/shared/api/problem';

import { guestErrorMessage, joinErrorMessage } from './errors';

const unauthorized = new ApiError({ status: 401, code: 'unauthorized', message: 'u' });
const full = new ApiError({ status: 409, code: 'meeting_full', message: 'f' });

describe('401 у гостя', () => {
  it('запросы с Participant-токеном (согласие, повторный вход): удален или сессия недействительна', () => {
    expect(guestErrorMessage(unauthorized)).toBe(
      'Вас удалили из встречи или сессия недействительна.',
    );
  });

  it('POST /join без токена: общая ошибка входа', () => {
    expect(joinErrorMessage(unauthorized)).toBe('Не удалось войти, попробуйте ещё раз.');
  });

  it('остальные коды у обоих – обычные сообщения', () => {
    expect(guestErrorMessage(full)).toMatch(/уже 10 участников/);
    expect(joinErrorMessage(full)).toMatch(/уже 10 участников/);
  });
});
