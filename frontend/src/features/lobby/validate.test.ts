import { validateJoinForm } from './validate';

describe('форма лобби', () => {
  it('анализ включен – нужен явный выбор', () => {
    expect(
      validateJoinForm({ displayName: 'Анна', consent: null, consentRequired: true }),
    ).toHaveProperty('consent');
    expect(
      validateJoinForm({ displayName: 'Анна', consent: 'denied', consentRequired: true }),
    ).toEqual({});
    expect(
      validateJoinForm({ displayName: 'Анна', consent: 'granted', consentRequired: true }),
    ).toEqual({});
  });

  it('анализ выключен – выбор не нужен', () => {
    expect(
      validateJoinForm({ displayName: 'Анна', consent: null, consentRequired: false }),
    ).toEqual({});
  });

  it('имя обязательно и не длиннее 64 символов', () => {
    expect(
      validateJoinForm({ displayName: '   ', consent: null, consentRequired: false }),
    ).toHaveProperty('displayName');
    expect(
      validateJoinForm({ displayName: 'а'.repeat(65), consent: null, consentRequired: false }),
    ).toHaveProperty('displayName');
  });
});
