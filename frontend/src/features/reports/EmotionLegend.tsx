import { EMOTION_LABELS, emotionColor } from '@/shared/config/emotions';
import { EmotionTag } from '@/shared/ui/emotion-icon';

/** Легенда графиков: цветной квадрат, значок и подпись – класс опознается без цвета. */
export function EmotionLegend() {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-2 text-sm" aria-label="Легенда: классы эмоций">
      {EMOTION_LABELS.map((e) => (
        <li key={e} className="flex items-center gap-1.5">
          <span
            className="size-3 rounded-sm"
            style={{ background: emotionColor(e, 'fill') }}
            aria-hidden
          />
          <EmotionTag label={e} surface="line" />
        </li>
      ))}
    </ul>
  );
}
