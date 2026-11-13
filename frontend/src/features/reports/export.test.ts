import { http, HttpResponse } from 'msw';
import { server } from '@/test/server';
import { organizer, problem, tokenResponse } from '@/test/api-mocks';
import { setSession } from '@/shared/api/session';
import { exportFilename, fetchReportExport } from './export';

const endpoint = '/api/v1/reports/meeting/export.csv';
const bytes = new Uint8Array([
  0xef,
  0xbb,
  0xbf,
  ...new TextEncoder().encode('ts,display_name\n2026-11-12,Участник\n'),
]);
it('CSV использует Bearer, обновляет токен и сохраняет серверные байты, BOM, тип и имя UTF-8', async () => {
  setSession(tokenResponse(organizer, 'old'));
  const seen: string[] = [];
  server.use(
    http.post('/api/v1/auth/refresh', () => HttpResponse.json(tokenResponse(organizer, 'new'))),
    http.get(endpoint, ({ request }) => {
      seen.push(request.headers.get('Authorization') ?? '');
      return seen.length === 1
        ? problem(401, 'unauthorized')
        : new HttpResponse(bytes, {
            headers: {
              'Content-Type': 'text/csv; charset=utf-8',
              'Content-Disposition':
                "attachment; filename*=UTF-8''%D0%9E%D1%82%D1%87%D1%91%D1%82.csv",
            },
          });
    }),
  );
  const result = await fetchReportExport('meeting', 'csv');
  expect(seen).toEqual(['Bearer old', 'Bearer new']);
  expect(result.filename).toBe('Отчёт.csv');
  expect(result.blob.type).toBe('text/csv; charset=utf-8');
  expect(result.blob.size).toBe(bytes.length);
});
it.each([
  [404, 'not_found'],
  [409, 'meeting_in_progress'],
  [409, 'report_not_ready'],
])('передает ошибку %i %s без скачивания', async (status, code) => {
  server.use(http.get(endpoint, () => problem(status as number, code as string)));
  await expect(fetchReportExport('meeting', 'csv')).rejects.toMatchObject({ status, code });
});
it.each([
  ['csv', 'text/csv', 'without BOM'],
  ['pdf', 'application/pdf', '<html>Bad gateway</html>'],
  ['pdf', 'text/html', '%PDF-1.4'],
] as const)('отклоняет некорректный %s (%s)', async (format, type, body) => {
  server.use(
    http.get(
      `/api/v1/reports/meeting/export.${format}`,
      () => new HttpResponse(body, { headers: { 'Content-Type': type } }),
    ),
  );
  await expect(fetchReportExport('meeting', format)).rejects.toMatchObject({
    code: 'invalid_export',
  });
});
it('имя файла не становится путём, некорректный filename* имеет запасное имя', () => {
  expect(exportFilename('attachment; filename="../report.csv"', 'fallback.csv')).toBe(
    '.._report.csv',
  );
  expect(exportFilename("attachment; filename*=UTF-8''%ZZ", 'fallback.csv')).toBe('fallback.csv');
});
