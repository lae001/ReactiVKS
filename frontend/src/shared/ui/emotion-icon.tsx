import {
  Angry,
  Annoyed,
  CircleAlert,
  Frown,
  Ghost,
  type LucideIcon,
  Meh,
  Smile,
} from 'lucide-react';

import {
  EMOTION_META,
  type EmotionLabel,
  type EmotionSurface,
  emotionColor,
} from '@/shared/config/emotions';
import { cn } from '@/shared/lib/utils';

/** Значок класса эмоции: форма различима и без цвета (docs/frontend/emotion-visualization.md). */
export const EMOTION_ICONS: Record<EmotionLabel, LucideIcon> = {
  angry: Angry,
  disgust: Annoyed,
  fear: Ghost,
  happy: Smile,
  sad: Frown,
  surprise: CircleAlert,
  neutral: Meh,
};

/** Цветной значок эмоции; подпись рядом обязательна, сам значок скрыт от скринридеров. */
export function EmotionIcon({
  label,
  surface = 'dark',
  className,
}: {
  label: EmotionLabel;
  surface?: EmotionSurface;
  className?: string;
}) {
  const Icon = EMOTION_ICONS[label];
  return (
    <Icon
      className={cn('size-4 shrink-0', className)}
      style={{ color: emotionColor(label, surface === 'fill' ? 'line' : surface) }}
      aria-hidden
    />
  );
}

/** Значок + название: основной способ показать класс эмоции в интерфейсе. */
export function EmotionTag({
  label,
  surface = 'dark',
  className,
}: {
  label: EmotionLabel;
  surface?: EmotionSurface;
  className?: string;
}) {
  return (
    <span className={cn('inline-flex items-center gap-1.5', className)}>
      <EmotionIcon label={label} surface={surface} />
      {EMOTION_META[label].title}
    </span>
  );
}
