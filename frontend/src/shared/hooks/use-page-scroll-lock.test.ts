import { renderHook } from '@testing-library/react';

import { usePageScrollLock } from './use-page-scroll-lock';

describe('блокировка прокрутки страницы в комнате', () => {
  afterEach(() => {
    document.documentElement.style.overflow = '';
    document.body.style.overflow = '';
  });

  it('пока включена – html и body без прокрутки, при размонтировании возвращается прежнее значение', () => {
    document.body.style.overflow = 'scroll';
    const view = renderHook(() => usePageScrollLock());
    expect(document.documentElement.style.overflow).toBe('clip');
    expect(document.body.style.overflow).toBe('clip');

    view.unmount();
    expect(document.documentElement.style.overflow).toBe('');
    expect(document.body.style.overflow).toBe('scroll');
  });

  it('выключенная блокировка ничего не трогает и включается по флагу', () => {
    const view = renderHook(({ on }) => usePageScrollLock(on), { initialProps: { on: false } });
    expect(document.body.style.overflow).toBe('');
    view.rerender({ on: true });
    expect(document.body.style.overflow).toBe('clip');
    view.rerender({ on: false });
    expect(document.body.style.overflow).toBe('');
  });
});
