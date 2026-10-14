/**
 * Классы эмоций. Порядок совпадает с массивом `labels` в сообщении `welcome`
 * протокола WebSocket (docs/api/websocket-protocol.md) и с выходом модели.
 * Цвета и правила их применения – docs/frontend/emotion-visualization.md (EMO-55).
 */
export const EMOTION_LABELS = [
  'angry',
  'disgust',
  'fear',
  'happy',
  'sad',
  'surprise',
  'neutral',
] as const;

export type EmotionLabel = (typeof EMOTION_LABELS)[number];

export const EMOTION_META: Record<EmotionLabel, { title: string; cssVar: string }> = {
  angry: { title: 'Гнев', cssVar: '--emotion-angry' },
  disgust: { title: 'Отвращение', cssVar: '--emotion-disgust' },
  fear: { title: 'Страх', cssVar: '--emotion-fear' },
  happy: { title: 'Радость', cssVar: '--emotion-happy' },
  sad: { title: 'Грусть', cssVar: '--emotion-sad' },
  surprise: { title: 'Удивление', cssVar: '--emotion-surprise' },
  neutral: { title: 'Нейтральное', cssVar: '--emotion-neutral' },
};

/** Порядок в фирменной полосе: от позитивных через нейтральное к негативным. */
export const EMOTION_SPECTRUM: readonly EmotionLabel[] = [
  'happy',
  'surprise',
  'disgust',
  'neutral',
  'sad',
  'angry',
  'fear',
];

/** Где рисуется цвет: заливка на светлом фоне, линия/обводка на светлом фоне, любая метка на темном (комната). */
export type EmotionSurface = 'fill' | 'line' | 'dark';

/**
 * Имя CSS-переменной цвета эмоции для поверхности. Заливки на светлом фоне бывают ниже 3:1,
 * поэтому линии и обводки берут более темный вариант `-line`; синий «Грусть» на темном фоне
 * светлеет (`--emotion-sad-dark`). Остальные цвета на темном фоне подходят без изменений.
 */
export function emotionVar(label: EmotionLabel, surface: EmotionSurface = 'fill'): string {
  if (surface === 'line') return `${EMOTION_META[label].cssVar}-line`;
  if (surface === 'dark' && label === 'sad') return '--emotion-sad-dark';
  return EMOTION_META[label].cssVar;
}

/** Цвет эмоции как значение для style/SVG. */
export function emotionColor(label: EmotionLabel, surface: EmotionSurface = 'fill'): string {
  return `var(${emotionVar(label, surface)})`;
}
