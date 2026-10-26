import { EMOTION_LABELS } from '@/shared/config/emotions';

import type {
  EmotionDistribution,
  Marker,
  Report,
  ReportParticipant,
  Series,
} from '@/shared/api/types';

/**
 * Тестовый отчет завершенной встречи m-ended (47 минут, 5 участников) для экрана отчета,
 * пока нет analytics-service. Форма – как у GET /reports/{id} и /series (docs/api/rest-api.md).
 * Ряд строится детерминированно, чтобы скриншоты и тесты не менялись от запуска к запуску.
 */

const STARTED = Date.parse('2026-09-29T12:01:00Z');
const DURATION_S = 47 * 60;
const STEP_S = 30;

/** Сырые веса по классам (порядок EMOTION_LABELS) для момента t, с. */
function rawWeights(t: number): number[] {
  const x = t / DURATION_S;
  const tension = Math.exp(-(((x - 0.55) / 0.08) ** 2)); // напряженный момент ~26 мин
  const joy =
    0.14 +
    0.16 * Math.sin(Math.PI * Math.min(1, x * 1.15)) ** 2 +
    0.2 * Math.exp(-(((x - 0.9) / 0.07) ** 2));
  return [
    0.03 + 0.2 * tension, // angry
    0.02 + 0.07 * tension, // disgust
    0.025 + 0.1 * tension, // fear
    joy, // happy
    0.05 + 0.16 * tension + 0.02 * Math.sin(x * 9) ** 2, // sad
    0.07 + 0.04 * Math.sin(x * 14) ** 2 + 0.05 * tension, // surprise
    0.5 - 0.1 * Math.sin(Math.PI * x) - 0.15 * tension, // neutral
  ];
}

function normalized(t: number): number[] {
  const w = rawWeights(t);
  const sum = w.reduce((a, b) => a + b, 0);
  return w.map((v) => Math.round((v / sum) * 1000) / 1000);
}

const POINTS = Array.from({ length: DURATION_S / STEP_S + 1 }, (_, i) => i * STEP_S);

export const MOCK_REPORT_SERIES: Series = {
  resolution: '30s',
  points: POINTS.map((t) => ({
    ts: new Date(STARTED + t * 1000).toISOString(),
    p: normalized(t),
    face_ratio: t > 1500 && t < 1560 ? 0.6 : 0.95,
  })),
};

function distribution(p: number[]): EmotionDistribution {
  return Object.fromEntries(EMOTION_LABELS.map((e, i) => [e, p[i] ?? 0])) as EmotionDistribution;
}

const overall = EMOTION_LABELS.map((_, i) => {
  const sum = MOCK_REPORT_SERIES.points.reduce((acc, pt) => acc + (pt.p?.[i] ?? 0), 0);
  return Math.round((sum / MOCK_REPORT_SERIES.points.length) * 1000) / 1000;
});

const negative = overall
  .filter((_, i) => ['angry', 'disgust', 'fear', 'sad'].includes(EMOTION_LABELS[i] ?? ''))
  .reduce((a, b) => a + b, 0);

const participants: ReportParticipant[] = [
  {
    participant_id: 'p-anna',
    display_name: 'Анна Смирнова',
    consent: 'granted',
    distribution: distribution([0.02, 0.01, 0.02, 0.38, 0.04, 0.1, 0.43]),
    dominant: 'neutral',
    face_detected_ratio: 0.96,
    analyzed_seconds: 2760,
  },
  {
    participant_id: 'p-maria',
    display_name: 'Мария Ким',
    consent: 'granted',
    distribution: distribution([0.05, 0.03, 0.04, 0.17, 0.12, 0.07, 0.52]),
    dominant: 'neutral',
    face_detected_ratio: 0.91,
    analyzed_seconds: 2610,
  },
  {
    participant_id: 'p-dmitry',
    display_name: 'Дмитрий Орлов',
    consent: 'granted',
    distribution: distribution([0.14, 0.06, 0.05, 0.12, 0.1, 0.06, 0.47]),
    dominant: 'neutral',
    face_detected_ratio: 0.88,
    analyzed_seconds: 2400,
  },
  {
    participant_id: 'p-ivan',
    display_name: 'Иван Петров (вы)',
    consent: 'granted',
    distribution: distribution([0.03, 0.02, 0.02, 0.46, 0.03, 0.12, 0.32]),
    dominant: 'happy',
    face_detected_ratio: 0.97,
    analyzed_seconds: 2810,
  },
  {
    participant_id: 'p-oleg',
    display_name: 'Олег Иванов',
    consent: 'denied',
    distribution: null,
    dominant: null,
    face_detected_ratio: null,
    analyzed_seconds: 0,
  },
];

const markers: Marker[] = [
  {
    id: 'mk-1',
    ts: new Date(STARTED + 9 * 60 * 1000).toISOString(),
    kind: 'manual',
    participant_id: null,
    label: 'Вопрос о сроках',
    details: {},
  },
  {
    id: 'mk-2',
    ts: new Date(STARTED + 25 * 60 * 1000).toISOString(),
    kind: 'auto_shift',
    participant_id: null,
    label: 'Рост негативных эмоций',
    details: { negative_delta: 0.34 },
  },
  {
    id: 'mk-3',
    ts: new Date(STARTED + 41 * 60 * 1000).toISOString(),
    kind: 'manual',
    participant_id: null,
    label: 'Договорились о пилоте',
    details: {},
  },
];

export const MOCK_REPORT: Report = {
  meeting_id: 'm-ended',
  status: 'ready',
  model_version: 'emotion-effnetb0@1.0.0',
  meeting: {
    title: 'Демонстрация прототипа заказчику',
    started_at: new Date(STARTED).toISOString(),
    ended_at: new Date(STARTED + DURATION_S * 1000).toISOString(),
    duration_s: DURATION_S,
  },
  summary: {
    overall: {
      distribution: distribution(overall),
      face_detected_ratio: 0.93,
      negative_share: Math.round(negative * 1000) / 1000,
    },
    participants,
  },
  markers,
  disclaimer:
    'Результаты отражают внешнее выражение лица и носят рекомендательный характер. Это не оценка личности.',
};

/** Отчет для встречи; undefined – анализа не было или встреча не завершена. */
export function getMockReport(meetingId: string): { report: Report; series: Series } | undefined {
  return meetingId === MOCK_REPORT.meeting_id
    ? { report: MOCK_REPORT, series: MOCK_REPORT_SERIES }
    : undefined;
}
