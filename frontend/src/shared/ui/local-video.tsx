import { useEffect, useRef } from 'react';

import { cn } from '@/shared/lib/utils';

/** Видео своей камеры: зеркально и без звука (свой голос не воспроизводится). */
export function LocalVideo({ stream, className }: { stream: MediaStream; className?: string }) {
  const ref = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.srcObject = stream;
  }, [stream]);

  return (
    <video
      ref={ref}
      autoPlay
      playsInline
      muted
      className={cn('size-full -scale-x-100 object-cover', className)}
    />
  );
}
