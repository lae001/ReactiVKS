import { useState } from 'react';
import { Button } from '@/shared/ui/button';
import { downloadReport, exportError } from './export';
import type { ExportFormat } from './export';

export function ReportExport({
  meetingId,
  ended,
  reportReady,
}: {
  meetingId: string;
  ended: boolean;
  reportReady: boolean;
}) {
  const [pending, setPending] = useState<ExportFormat | null>(null);
  const [error, setError] = useState('');
  async function download(format: ExportFormat) {
    setPending(format);
    setError('');
    try {
      await downloadReport(meetingId, format);
    } catch (cause) {
      setError(exportError(cause));
    } finally {
      setPending(null);
    }
  }
  return (
    <div className="flex flex-col gap-2" aria-label="Экспорт отчёта">
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          disabled={!ended || pending !== null}
          onClick={() => void download('csv')}
        >
          Скачать CSV
        </Button>
        <Button
          variant="outline"
          disabled={!reportReady || pending !== null}
          onClick={() => void download('pdf')}
        >
          Скачать PDF
        </Button>
      </div>
      {!ended && (
        <p className="text-sm text-muted-foreground">CSV доступен после завершения встречи.</p>
      )}
      {!reportReady && (
        <p className="text-sm text-muted-foreground">PDF доступен после подготовки отчёта.</p>
      )}
      {pending && <p role="status">Скачиваем {pending.toUpperCase()}…</p>}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
