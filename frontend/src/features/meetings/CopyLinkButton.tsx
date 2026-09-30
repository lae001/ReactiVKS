import { Check, Copy } from 'lucide-react';
import { useEffect, useState } from 'react';

import { Button } from '@/shared/ui/button';

/** Копирование ссылки-приглашения; подтверждение тем же словом, что и действие. */
export function CopyLinkButton({
  url,
  label = 'Копировать ссылку',
}: {
  url: string;
  label?: string;
}) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle');

  useEffect(() => {
    if (state === 'idle') return;
    const t = setTimeout(() => setState('idle'), 2000);
    return () => clearTimeout(t);
  }, [state]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setState('copied');
    } catch {
      setState('failed');
    }
  }

  return (
    <Button variant="outline" size="sm" onClick={copy} aria-live="polite">
      {state === 'copied' ? <Check aria-hidden /> : <Copy aria-hidden />}
      {state === 'copied'
        ? 'Ссылка скопирована'
        : state === 'failed'
          ? 'Не удалось – скопируйте вручную'
          : label}
    </Button>
  );
}
