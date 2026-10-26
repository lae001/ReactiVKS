import { EmotionIndicator, ProbabilityBar } from '@/features/emotions/EmotionIndicator';
import type { SnapshotParticipant } from '@/shared/api/types';
import { EMOTION_LABELS, EMOTION_META, emotionVar } from '@/shared/config/emotions';
import { simulateVision, type VisionType } from '@/shared/lib/color';
import { EmotionDistribution } from '@/features/reports/EmotionDistribution';
import { EmotionLegend } from '@/features/reports/EmotionLegend';
import { EmotionTimeline } from '@/features/reports/EmotionTimeline';
import { MOCK_REPORT, MOCK_REPORT_SERIES } from '@/shared/mocks/report';
import { EmotionSpectrum } from '@/shared/ui/brand';
import { EmotionTag } from '@/shared/ui/emotion-icon';

const VISIONS: { type: VisionType; title: string }[] = [
  { type: 'normal', title: 'Норма' },
  { type: 'protan', title: 'Протанопия' },
  { type: 'deutan', title: 'Дейтеранопия' },
  { type: 'tritan', title: 'Тританопия' },
];

/** Цвет токена из styles.css, как его видит браузер. */
function resolved(cssVar: string): string {
  if (typeof document === 'undefined') return '#000000';
  const raw = getComputedStyle(document.documentElement).getPropertyValue(cssVar).trim();
  return /^#[0-9a-f]{6}$/i.test(raw) ? raw : '#000000';
}

const SAMPLE_P = [0.04, 0.02, 0.05, 0.52, 0.06, 0.11, 0.2];

function sample(dominant: SnapshotParticipant['last']): SnapshotParticipant {
  return {
    participant_id: 'demo',
    display_name: 'Анна Смирнова',
    role: 'guest',
    state: 'analyzing',
    last: dominant,
  };
}

/**
 * Образец визуализации эмоций (EMO-55, docs/frontend/emotion-visualization.md): цвета в трех вариантах,
 * значок + подпись, имитация дальтонизма, индикаторы и распределение на темном фоне комнаты.
 */
export function EmotionsSection() {
  return (
    <section className="flex flex-col gap-6" aria-labelledby="emotions-title">
      <div className="flex flex-col gap-2">
        <h2 id="emotions-title" className="text-lg font-semibold">
          Эмоции
        </h2>
        <p className="max-w-prose text-sm text-muted-foreground">
          Цвет всегда сопровождается значком и подписью. На светлом фоне линии и обводки берут
          вариант <code>-line</code>, на темном «Грусть» светлеет (<code>--emotion-sad-dark</code>
          ).
        </p>
        <EmotionSpectrum className="h-2 max-w-md" />
      </div>

      <div className="overflow-x-auto rounded-xl border bg-card">
        <table className="w-full min-w-[40rem] text-sm">
          <caption className="sr-only">
            Цвета классов эмоций и их вид при разных типах цветового зрения
          </caption>
          <thead className="text-left text-muted-foreground">
            <tr className="border-b">
              <th scope="col" className="p-3 font-medium">
                Класс
              </th>
              <th scope="col" className="p-3 font-medium">
                Заливка / линия / темный
              </th>
              {VISIONS.map((v) => (
                <th key={v.type} scope="col" className="p-3 font-medium">
                  {v.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {EMOTION_LABELS.map((e) => {
              const fill = resolved(EMOTION_META[e].cssVar);
              return (
                <tr key={e} className="border-b last:border-0">
                  <th scope="row" className="p-3 text-left font-medium">
                    <EmotionTag label={e} surface="line" />
                    <code className="block pt-1 text-xs font-normal text-muted-foreground">
                      {e}
                    </code>
                  </th>
                  <td className="p-3">
                    <span className="flex gap-1.5">
                      {(['fill', 'line', 'dark'] as const).map((surface) => (
                        <span
                          key={surface}
                          title={`${surface}: ${resolved(emotionVar(e, surface))}`}
                          className="size-7 rounded-md border"
                          style={{ background: `var(${emotionVar(e, surface)})` }}
                        />
                      ))}
                    </span>
                  </td>
                  {VISIONS.map((v) => (
                    <td key={v.type} className="p-3">
                      <span
                        className="block size-7 rounded-md border"
                        style={{ background: simulateVision(fill, v.type) }}
                      />
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-col gap-4 rounded-xl bg-room p-5 text-room-foreground">
        <p className="text-sm font-medium">Индикаторы в комнате (тёмный фон)</p>
        <div className="flex flex-wrap gap-2">
          {EMOTION_LABELS.map((e, i) => (
            <EmotionIndicator
              key={e}
              data={sample({
                ts: '2026-10-01T07:12:03Z',
                dominant: e,
                confidence: 0.5 + i / 20,
                p: SAMPLE_P,
              })}
              className="border border-room-border"
            />
          ))}
        </div>
        <ProbabilityBar p={SAMPLE_P} className="h-3" />
        <p className="text-xs text-room-muted">
          Распределение вероятностей одной полосой; текстовая расшифровка — для скринридеров.
        </p>
      </div>

      <div className="flex flex-col gap-6 rounded-xl border bg-card p-5">
        <div className="flex flex-col gap-1">
          <p className="text-sm font-medium">Графики отчета (светлый фон)</p>
          <p className="text-xs text-muted-foreground">
            Стековая площадь вероятностей для динамики, столбцы для распределения; серии различаются
            заливкой, а не цветом линий.
          </p>
        </div>
        <EmotionTimeline
          series={MOCK_REPORT_SERIES}
          markers={MOCK_REPORT.markers}
          startedAt={MOCK_REPORT.meeting.started_at}
          durationS={MOCK_REPORT.meeting.duration_s}
        />
        <EmotionLegend />
        <EmotionDistribution distribution={MOCK_REPORT.summary.overall.distribution} />
      </div>
    </section>
  );
}
