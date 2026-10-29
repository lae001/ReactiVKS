import { useEffect } from 'react';

/**
 * Пока включено, страница не прокручивается ни по одной оси: комната занимает окно целиком, а прокручиваются
 * только ее внутренние панели. При выключении и размонтировании возвращается прежнее значение `overflow`.
 */
export function usePageScrollLock(enabled = true) {
  useEffect(() => {
    if (!enabled) return;
    const html = document.documentElement;
    const body = document.body;
    const previous = { html: html.style.overflow, body: body.style.overflow };
    html.style.overflow = 'hidden';
    body.style.overflow = 'hidden';
    return () => {
      html.style.overflow = previous.html;
      body.style.overflow = previous.body;
    };
  }, [enabled]);
}
