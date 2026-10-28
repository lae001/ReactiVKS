import { resolveApiMode } from './index';

describe('VITE_API_MODE', () => {
  it('по умолчанию и при неизвестном значении – mock; http включается явно', () => {
    expect(resolveApiMode(undefined)).toBe('mock');
    expect(resolveApiMode('')).toBe('mock');
    expect(resolveApiMode('prod')).toBe('mock');
    expect(resolveApiMode('mock')).toBe('mock');
    expect(resolveApiMode('http')).toBe('http');
  });
});
