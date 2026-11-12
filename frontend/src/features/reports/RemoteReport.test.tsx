import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { apiFetch } from '@/shared/api/client';
import { getMockReport } from '@/shared/mocks/report';
import { EMOTION_LABELS } from '@/shared/config/emotions';
import { RemoteReport } from './RemoteReport';

vi.mock('@/shared/api/client', () => ({ apiFetch: vi.fn() }));
function show() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <RemoteReport meetingId="tested-meeting" />
    </QueryClientProvider>,
  );
}
afterEach(() => vi.resetAllMocks());
it('ошибка сервиса не подменяется демонстрационным отчётом', async () => {
  vi.mocked(apiFetch).mockRejectedValue(new Error('503'));
  show();
  expect(await screen.findByRole('alert')).toHaveTextContent('Отчёт недоступен');
  expect(screen.queryByText('Отчет по эмоциям')).toBeNull();
  expect(apiFetch).toHaveBeenCalledWith(
    '/api/v1/reports/tested-meeting',
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
});
it('pending показывает подготовку, failed — ошибку', async () => {
  vi.mocked(apiFetch).mockResolvedValue({ status: 'failed' });
  show();
  expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось сформировать');
});
it('готовый отчёт без анализируемых участников показывает отсутствие данных', async () => {
  vi.mocked(apiFetch).mockResolvedValue({ status: 'ready', summary: { participants: [] } });
  show();
  expect(await screen.findByText('Нет данных анализа для отчёта.')).toBeInTheDocument();
});

it('готовый контракт отображает реальные поля ответа, графики и отметки', async () => {
  const fixture = getMockReport('m-ended')!;
  vi.mocked(apiFetch).mockImplementation(async (path) =>
    path.endsWith('/series')
      ? {
          resolution: '5s',
          labels: EMOTION_LABELS,
          series: [
            {
              participant_id: fixture.report.summary.participants[0]!.participant_id,
              points: fixture.series.points,
            },
          ],
        }
      : { ...fixture.report, meeting_id: 'tested-meeting' },
  );
  show();
  expect(await screen.findByRole('heading', { name: 'Отчет по эмоциям' })).toBeInTheDocument();
  expect(screen.getByRole('img', { name: /График вероятностей/ })).toBeInTheDocument();
  expect(screen.getByText('Вопрос о сроках')).toBeInTheDocument();
});
