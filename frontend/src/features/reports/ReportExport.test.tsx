import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiError } from '@/shared/api/problem';
import { ReportExport } from './ReportExport';
import { downloadReport } from './export';
import type * as ExportModule from './export';
vi.mock('./export', async (original) => ({
  ...(await original<typeof ExportModule>()),
  downloadReport: vi.fn(),
}));
afterEach(() => vi.resetAllMocks());
it('CSV доступен после завершения, PDF только после готовности', () => {
  const view = render(<ReportExport meetingId="meeting" ended={false} reportReady={false} />);
  expect(screen.getByText('Скачать CSV')).toBeDisabled();
  view.rerender(<ReportExport meetingId="meeting" ended reportReady={false} />);
  expect(screen.getByText('Скачать CSV')).toBeEnabled();
  expect(screen.getByText('Скачать PDF')).toBeDisabled();
});
it.each([
  ['meeting_in_progress', 'CSV будет доступен'],
  ['report_not_ready', 'PDF ещё не готов'],
  ['not_found', 'Экспорт недоступен'],
])('объясняет отказ %s и позволяет повторить', async (code, message) => {
  vi.mocked(downloadReport)
    .mockRejectedValueOnce(
      new ApiError({ status: code === 'not_found' ? 404 : 409, code, message: code }),
    )
    .mockResolvedValue(undefined);
  render(<ReportExport meetingId="meeting" ended reportReady />);
  const user = userEvent.setup();
  await user.click(screen.getByText('Скачать PDF'));
  expect(await screen.findByRole('alert')).toHaveTextContent(message);
  await user.click(screen.getByText('Скачать PDF'));
  expect(screen.queryByRole('alert')).toBeNull();
  expect(downloadReport).toHaveBeenLastCalledWith('meeting', 'pdf');
});
