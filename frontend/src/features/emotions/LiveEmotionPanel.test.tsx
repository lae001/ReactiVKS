import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { apiFetch } from '@/shared/api/client';
import { LiveEmotionPanel } from './LiveEmotionPanel';
import { emptyEmotions } from './stream';
vi.mock('@/shared/api/client', () => ({ apiFetch: vi.fn() }));
afterEach(() => vi.resetAllMocks());
it('пустой поток не создаёт эмоции, отметка подтверждается сервером', async () => {
  vi.mocked(apiFetch).mockResolvedValue({ id: 'marker' });
  render(<LiveEmotionPanel meetingId="m" data={emptyEmotions()} status="Недоступно" />);
  expect(screen.getByText('Данных участников пока нет.')).toBeInTheDocument();
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Название отметки'), 'Обсуждение');
  await user.click(screen.getByRole('button', { name: 'Отметить момент' }));
  expect(apiFetch).toHaveBeenCalledWith('/api/v1/reports/m/markers', {
    method: 'POST',
    body: { label: 'Обсуждение', ts: null },
  });
  expect(await screen.findByText('Отметка сохранена в отчёте')).toBeInTheDocument();
});
it('отказ сервера сохраняет введённый текст для повтора', async () => {
  vi.mocked(apiFetch).mockRejectedValue(new Error('404'));
  render(<LiveEmotionPanel meetingId="m" data={emptyEmotions()} status="Недоступно" />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Название отметки'), 'Вопрос');
  await user.click(screen.getByRole('button', { name: 'Отметить момент' }));
  expect(await screen.findByText(/Не удалось сохранить отметку/)).toBeInTheDocument();
  expect(screen.getByLabelText('Название отметки')).toHaveValue('Вопрос');
});
