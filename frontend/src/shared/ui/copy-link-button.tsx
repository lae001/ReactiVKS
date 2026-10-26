import { Check, Copy } from 'lucide-react';
import { useEffect, useState } from 'react';

import { Button, type buttonVariants } from '@/shared/ui/button';
import type { VariantProps } from 'class-variance-authority';

/** Копирование ссылки-приглашения; подтверждение тем же словом, что и действие. */
export function CopyLinkButton({
  url,
  label = 'Копировать ссылку',
  variant = 'outline',
}: {
  url: string;
  label?: string;
  variant?: VariantProps<typeof buttonVariants>['variant'];
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
    <Button variant={variant} size="sm" onClick={copy} aria-live="polite">
      {state === 'copied' ? <Check aria-hidden /> : <Copy aria-hidden />}
      {state === 'copied'
        ? 'Ссылка скопирована'
        : state === 'failed'
          ? 'Не удалось – скопируйте вручную'
          : label}
    </Button>
  );
}
