import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { meetingsApi } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';
import { organizer } from '@/test/api-mocks';
import { renderApp } from '@/test/render';
afterEach(() => vi.restoreAllMocks());
it('сохранённые настройки становятся начальными значениями новой встречи', async () => {
  const router = renderApp('/settings', { user: organizer });
  const user = userEvent.setup();
  const fps = await screen.findByLabelText('Частота анализа по умолчанию');
  await user.clear(fps);
  await user.type(fps, '5');
  await user.click(screen.getByLabelText('Включать анализ в новых встречах'));
  await user.click(screen.getByText('Сохранить настройки встреч'));
  await screen.findByText('Настройки встреч сохранены.');
  await router.navigate('/meetings/new');
  expect(await screen.findByRole('checkbox', { name: /Анализировать эмоции/ })).not.toBeChecked();
  expect(screen.getByRole('radio', { name: '5' })).toBeChecked();
  await router.navigate('/settings');
  expect(await screen.findByLabelText('Частота анализа по умолчанию')).toHaveValue(5);
});
it('дробная частота не отправляется, серверный отказ не показывает успешное сохранение', async () => {
  const save = vi
    .spyOn(meetingsApi, 'putSettings')
    .mockRejectedValue(new ApiError({ status: 422, code: 'validation_error', message: 'invalid' }));
  renderApp('/settings', { user: organizer });
  const user = userEvent.setup();
  const fps = await screen.findByLabelText('Частота анализа по умолчанию');
  await user.clear(fps);
  await user.type(fps, '2.5');
  await user.click(screen.getByText('Сохранить настройки встреч'));
  expect(await screen.findByText('Укажите целое число от 2 до 5.')).toBeVisible();
  expect(save).not.toHaveBeenCalled();
  await user.clear(fps);
  await user.type(fps, '4');
  await user.click(screen.getByText('Сохранить настройки встреч'));
  await screen.findByText(/Сервер отклонил настройки/);
  expect(screen.queryByText('Настройки встреч сохранены.')).toBeNull();
  await waitFor(() =>
    expect(meetingsApi.getSettings()).resolves.toMatchObject({ analysis_fps_default: 3 }),
  );
});
