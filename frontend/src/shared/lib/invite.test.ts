import { parseInviteCode } from './invite';

describe('код приглашения', () => {
  it.each([
    ['demoactive', 'demoactive'],
    ['  DEMOACTIVE ', 'demoactive'],
    ['https://vks.example.ru/j/demoactive', 'demoactive'],
    ['https://vks.example.ru/j/demoactive?utm=1', 'demoactive'],
    ['/j/demolater2', 'demolater2'],
  ])('%s → %s', (input, code) => {
    expect(parseInviteCode(input)).toBe(code);
  });

  it.each(['', 'short', 'demoactive1', 'https://vks.example.ru/meetings', 'demo-activ'])(
    '%s не распознается',
    (input) => {
      expect(parseInviteCode(input)).toBeNull();
    },
  );
});
