import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';

import { useSessionStore } from '@/shared/api/session';
import { organizer, problem, validationIssue } from '@/test/api-mocks';
import { renderApp } from '@/test/render';
import { server } from '@/test/server';

async function openSettings() {
  server.use(http.get('/api/v1/users/me', () => HttpResponse.json(organizer)));
  renderApp('/settings', { user: organizer });
  return screen.findByLabelText('Имя');
}

describe('профиль', () => {
  it('показывает данные из GET /users/me, почта только для чтения', async () => {
    const name = await openSettings();
    expect(name).toHaveValue('Иван Петров');
    expect(screen.getByLabelText('Электронная почта')).toHaveAttribute('readonly');
    expect(screen.getByRole('button', { name: 'Сохранить имя' })).toBeDisabled();
  });

  it('PATCH /users/me меняет имя и обновляет шапку', async () => {
    let body: unknown;
    const name = await openSettings();
    server.use(
      http.patch('/api/v1/users/me', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...organizer, display_name: 'Иван Сидоров' });
      }),
    );
    const user = userEvent.setup();
    await user.clear(name);
    await user.type(name, 'Иван Сидоров');
    await user.click(screen.getByRole('button', { name: 'Сохранить имя' }));

    expect(await screen.findByText(/Имя сохранено/)).toBeInTheDocument();
    expect(body).toEqual({ display_name: 'Иван Сидоров' });
    expect(useSessionStore.getState().user?.display_name).toBe('Иван Сидоров');
  });

  it('пустое имя не уходит на сервер', async () => {
    const name = await openSettings();
    const user = userEvent.setup();
    await user.clear(name);
    await user.click(screen.getByRole('button', { name: 'Сохранить имя' }));
    expect(await screen.findByText('Укажите имя')).toBeInTheDocument();
  });

  it('422 от сервера ложится на поле имени', async () => {
    const name = await openSettings();
    server.use(
      http.patch('/api/v1/users/me', () =>
        problem(422, 'validation_error', { errors: [validationIssue('display_name')] }),
      ),
    );
    const user = userEvent.setup();
    await user.type(name, '!');
    await user.click(screen.getByRole('button', { name: 'Сохранить имя' }));
    await waitFor(() => expect(name).toHaveAttribute('aria-invalid', 'true'));
  });

  it('ошибка загрузки профиля – сообщение и повтор', async () => {
    server.use(http.get('/api/v1/users/me', () => problem(500, 'internal_error')));
    renderApp('/settings', { user: organizer });
    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось загрузить профиль');

    server.use(http.get('/api/v1/users/me', () => HttpResponse.json(organizer)));
    await userEvent.setup().click(screen.getByRole('button', { name: 'Повторить' }));
    expect(await screen.findByLabelText('Имя')).toHaveValue('Иван Петров');
  });
});

describe('смена пароля (мок)', () => {
  it('помечена как тестовая, применяет политику пароля', async () => {
    await openSettings();
    expect(screen.getByText('Тестовый режим')).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Текущий пароль'), 'Passw0rd1');
    await user.type(screen.getByLabelText('Новый пароль'), 'короткий');
    await user.click(screen.getByRole('button', { name: 'Сменить пароль' }));
    expect(await screen.findByText('Добавьте хотя бы одну цифру')).toBeInTheDocument();
  });

  it('корректная форма проходит и честно говорит, что пароль не изменен', async () => {
    await openSettings();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Текущий пароль'), 'Passw0rd1');
    await user.type(screen.getByLabelText('Новый пароль'), 'Newpassw0rd');
    await user.click(screen.getByRole('button', { name: 'Сменить пароль' }));
    expect(await screen.findByText(/Пароль не изменен/)).toBeInTheDocument();
  });
});
