/**
 * Классы эмоций. Порядок совпадает с массивом `labels` в сообщении `welcome`
 * протокола WebSocket (docs/api/websocket-protocol.md) и с выходом модели.
 * Цвета – черновик до утверждения гайда визуализации (EMO-56).
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
