import { formatWait } from './errors';

describe('formatWait', () => {
  it.each([
    [1, '1 секунду'],
    [2, '2 секунды'],
    [11, '11 секунд'],
    [45, '45 секунд'],
    [60, '1 минуту'],
    [61, '2 минуты'],
    [300, '5 минут'],
    [900, '15 минут'],
  ])('%i с → %s', (seconds, expected) => {
    expect(formatWait(seconds)).toBe(expected);
  });
});
