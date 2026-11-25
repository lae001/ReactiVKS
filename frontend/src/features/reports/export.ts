import { apiResponse } from '@/shared/api/client';
import { ApiError } from '@/shared/api/problem';

export type ExportFormat = 'csv' | 'pdf';

/** Имя от сервера: поддерживает UTF-8 filename*, исключает пути и управляющие символы. */
export function exportFilename(header: string | null, fallback: string): string {
  const encoded = header?.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = header?.match(/filename="([^"]+)"|filename=([^;]+)/i);
  let name = plain?.[1] ?? plain?.[2] ?? fallback;
  if (encoded) {
    try {
      name = decodeURIComponent(encoded);
    } catch {
      /* Неверное кодирование: обычное имя. */
    }
  }
  return (
    name
      .trim()
      .replace(/[\\/]/g, '_')
      .split('')
      .filter((char) => char.charCodeAt(0) >= 32 && char.charCodeAt(0) !== 127)
      .join('') || fallback
  );
}

/** Сохраняются именно серверные байты; HTML страницы ошибки не превращается в «PDF». */
export async function fetchReportExport(meetingId: string, format: ExportFormat) {
  const mime = format === 'csv' ? 'text/csv' : 'application/pdf';
  const response = await apiResponse(
    `/api/v1/reports/${encodeURIComponent(meetingId)}/export.${format}`,
    {
      headers: { Accept: `${mime}, application/problem+json` },
    },
  );
  const bytes = new Uint8Array(await response.arrayBuffer());
  const validHeader =
    format === 'csv'
      ? bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf
      : new TextDecoder().decode(bytes.slice(0, 5)) === '%PDF-';
  if (
    response.headers.get('Content-Type')?.split(';')[0]?.trim().toLowerCase() !== mime ||
    !validHeader
  ) {
    throw new ApiError({
      status: 502,
      code: 'invalid_export',
      message: 'Неверный формат экспорта',
    });
  }
  return {
    blob: new Blob([bytes], { type: response.headers.get('Content-Type') ?? mime }),
    filename: exportFilename(
      response.headers.get('Content-Disposition'),
      `report-${meetingId}.${format}`,
    ),
  };
}

export async function downloadReport(meetingId: string, format: ExportFormat) {
  const { blob, filename } = await fetchReportExport(meetingId, format);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  // Дать браузеру начать скачивание до освобождения URL (в том числе Firefox/Safari).
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

export function exportError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'meeting_in_progress') return 'CSV будет доступен после завершения встречи.';
    if (error.code === 'report_not_ready')
      return 'PDF ещё не готов. Дождитесь подготовки отчёта и повторите.';
    if (error.code === 'invalid_export')
      return 'Сервис вернул файл неверного формата. Повторите позже.';
    if (error.status === 404)
      return 'Экспорт недоступен: файл не найден, нет доступа или сервис ещё не поддерживает экспорт.';
    if (error.status === 401 || error.status === 403)
      return 'Нет доступа к экспорту. Войдите как владелец встречи.';
  }
  return 'Не удалось скачать файл. Проверьте соединение и повторите позже.';
}
