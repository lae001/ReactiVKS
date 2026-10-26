import type { ReportParticipant } from '@/shared/api/types';
import { EMOTION_LABELS } from '@/shared/config/emotions';
import { formatDuration, formatPercent } from '@/shared/lib/format';
import { Badge } from '@/shared/ui/badge';
import { EmotionTag } from '@/shared/ui/emotion-icon';
import { ProbabilityBar } from '@/features/emotions/EmotionIndicator';

const CONSENT_LABEL = {
  granted: 'Согласие дано',
  denied: 'Отказался',
  revoked: 'Согласие отозвано',
  not_required: 'Анализ выключен',
} as const;

/** Таблица участников отчета: имя, доминирующая эмоция, распределение, доля кадров с лицом, время анализа. */
export function ParticipantsTable({ participants }: { participants: ReportParticipant[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border bg-card">
      <table className="w-full text-sm">
        <caption className="sr-only">Участники встречи и результаты распознавания</caption>
        <thead className="text-left text-muted-foreground">
          <tr className="border-b">
            <th scope="col" className="p-3 font-medium">
              Участник
            </th>
            <th scope="col" className="hidden p-3 font-medium sm:table-cell">
              Чаще всего
            </th>
            <th scope="col" className="p-3 font-medium">
              Распределение
            </th>
            <th scope="col" className="hidden p-3 text-right font-medium sm:table-cell">
              Лицо в кадре
            </th>
            <th scope="col" className="hidden p-3 text-right font-medium sm:table-cell">
              Анализ
            </th>
          </tr>
        </thead>
        <tbody>
          {participants.map((p) => (
            <tr key={p.participant_id} className="border-b last:border-0">
              <th scope="row" className="p-3 text-left font-medium">
                {p.display_name}
                {p.dominant && (
                  <span className="mt-1 block text-xs font-normal sm:hidden">
                    <EmotionTag label={p.dominant} surface="line" />
                  </span>
                )}
              </th>
              {p.distribution && p.dominant ? (
                <>
                  <td className="hidden p-3 sm:table-cell">
                    <EmotionTag label={p.dominant} surface="line" />
                  </td>
                  <td className="min-w-24 p-3 sm:w-48">
                    <ProbabilityBar
                      p={EMOTION_LABELS.map((e) => p.distribution?.[e] ?? 0)}
                      surface="fill"
                    />
                  </td>
                  <td className="hidden p-3 text-right tabular-nums sm:table-cell">
                    {formatPercent(p.face_detected_ratio ?? 0)}
                  </td>
                  <td className="hidden p-3 text-right tabular-nums sm:table-cell">
                    {formatDuration(p.analyzed_seconds)}
                  </td>
                </>
              ) : (
                <td colSpan={4} className="p-3 text-muted-foreground">
                  <Badge variant="outline">{CONSENT_LABEL[p.consent]}</Badge>{' '}
                  <span className="hidden sm:inline">Эмоции не анализировались</span>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
