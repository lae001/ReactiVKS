/// <reference types="node" />
import { readFileSync } from 'node:fs';

import { contrastRatio, deltaE2000, simulateVision, type VisionType } from '@/shared/lib/color';

import { EMOTION_LABELS, emotionVar } from './emotions';

const css = readFileSync('src/app/styles.css', 'utf8');
// Значения берем прямо из styles.css: тест ловит правку токена, которая ломает правила палитры
function token(name: string): string {
  const match = new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`).exec(css);
  if (!match?.[1]) throw new Error(`Нет токена ${name} в styles.css`);
  return match[1];
}
const fill = (e: (typeof EMOTION_LABELS)[number]) => token(emotionVar(e, 'fill'));
const line = (e: (typeof EMOTION_LABELS)[number]) => token(emotionVar(e, 'line'));
const dark = (e: (typeof EMOTION_LABELS)[number]) => token(emotionVar(e, 'dark'));

const PAIRS = EMOTION_LABELS.flatMap((a, i) =>
  EMOTION_LABELS.slice(i + 1).map((b) => [a, b] as const),
);

describe('палитра эмоций (docs/frontend/emotion-visualization.md)', () => {
  it.each<[VisionType, number]>([
    ['normal', 15],
    ['protan', 9],
    ['deutan', 9],
    ['tritan', 9],
  ])('все пары цветов различимы (%s, ΔE2000 ≥ %i)', (vision, min) => {
    for (const [a, b] of PAIRS) {
      const d = deltaE2000(simulateVision(fill(a), vision), simulateVision(fill(b), vision));
      expect(d, `${a} и ${b}`).toBeGreaterThanOrEqual(min);
    }
  });

  it('линии и обводки на светлом фоне – не ниже 3:1', () => {
    for (const e of EMOTION_LABELS) {
      expect(contrastRatio(line(e), '#FFFFFF'), e).toBeGreaterThanOrEqual(3);
      expect(contrastRatio(line(e), token('--background')), e).toBeGreaterThanOrEqual(3);
    }
  });

  it('метки на темном фоне комнаты – не ниже 3:1', () => {
    for (const e of EMOTION_LABELS) {
      expect(contrastRatio(dark(e), token('--room-surface')), e).toBeGreaterThanOrEqual(3);
      expect(contrastRatio(dark(e), token('--room')), e).toBeGreaterThanOrEqual(3);
    }
  });

  it('вариант -line не светлее заливки', () => {
    for (const e of EMOTION_LABELS) {
      expect(contrastRatio(line(e), '#FFFFFF')).toBeGreaterThanOrEqual(
        contrastRatio(fill(e), '#FFFFFF') - 0.01,
      );
    }
  });
});

describe('цветовые расчеты', () => {
  it('контраст белого и черного – 21:1', () => {
    expect(contrastRatio('#FFFFFF', '#000000')).toBeCloseTo(21, 5);
  });
  it('белый при дальтонизме остается белым, одинаковые цвета не различаются', () => {
    expect(simulateVision('#FFFFFF', 'deutan')).toBe('#FFFFFF');
    expect(deltaE2000('#E69F00', '#E69F00')).toBe(0);
  });
});
