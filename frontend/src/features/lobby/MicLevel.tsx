import { useMicLevel } from '@/shared/hooks/use-mic-level';

/** Индикатор уровня микрофона: полоса растет, когда пользователь говорит. */
export function MicLevel({ stream }: { stream: MediaStream | null }) {
  const level = useMicLevel(stream);
  const percent = Math.round(level * 100);
  return (
    <div
      role="meter"
      aria-label="Уровень микрофона"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      className="h-2 overflow-hidden rounded-full bg-muted"
    >
      <div
        className="h-full rounded-full bg-primary transition-[width] duration-75"
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}
