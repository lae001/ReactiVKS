import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meetingsApi } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';

import { organizer } from '@/test/api-mocks';
import { renderApp } from '@/test/render';

describe('карточка встречи', () => {
  it('запланированная: ссылка и кнопка «Начать встречу»', async () => {
    renderApp('/meetings/m-later', { user: organizer });
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Интервью: frontend-разработчик' }),
    ).toBeInTheDocument();
    expect(screen.getByText('https://vks.example.ru/j/demolater2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Начать встречу' })).toBeInTheDocument();
  });

  it('завершенная с анализом: отчет с графиками, отметками и таблицей участников', async () => {
    renderApp('/meetings/m-ended', { user: organizer });
    expect(await screen.findByRole('heading', { name: 'Отчет по эмоциям' })).toBeInTheDocument();
    expect(
      screen.getByRole('img', { name: /График вероятностей эмоций за 47:00/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('list', { name: 'Распределение эмоций за встречу' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Вопрос о сроках')).toBeInTheDocument();

    const table = screen.getByRole('table', { name: /Участники встречи/ });
    expect(within(table).getByText('Анна Смирнова')).toBeInTheDocument();
    // отказавшийся от анализа не получает эмоций, только пометку
    expect(within(table).getByText('Отказался')).toBeInTheDocument();
    expect(screen.getByText(/рекомендательный характер/)).toBeInTheDocument();
  });

  it('цвет эмоции не единственный признак: у легенды есть подписи всех семи классов', async () => {
    renderApp('/meetings/m-ended', { user: organizer });
    const legend = await screen.findByRole('list', { name: /Легенда/ });
    expect(within(legend).getAllByRole('listitem')).toHaveLength(7);
    expect(legend).toHaveTextContent('Радость');
    expect(legend).toHaveTextContent('Нейтральное');
  });

  it('завершенная без анализа: объясняет, почему отчета нет', async () => {
    renderApp('/meetings/m-ended-2', { user: organizer });
    expect(
      await screen.findByText(/Анализ эмоций в этой встрече был выключен/),
    ).toBeInTheDocument();
  });

  it('неизвестная встреча: понятное сообщение и возврат к списку', async () => {
    renderApp('/meetings/42', { user: organizer });
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Встреча не найдена' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'К встречам' })).toHaveAttribute('href', '/meetings');
  });

  describe('управление', () => {
    afterEach(() => vi.restoreAllMocks());

    it('«Начать встречу» активирует запланированную и открывает комнату', async () => {
      const user = userEvent.setup();
      const router = renderApp('/meetings/m-later', { user: organizer });
      await user.click(await screen.findByRole('button', { name: 'Начать встречу' }));
      await waitFor(() => expect(router.state.location.pathname).toBe('/room/m-later'));
      await expect(meetingsApi.getMeeting('m-later')).resolves.toMatchObject({
        status: 'active',
      });
    });

    it('активная: «Войти во встречу» – ссылка в комнату', async () => {
      renderApp('/meetings/m-active', { user: organizer });
      expect(await screen.findByRole('link', { name: 'Войти во встречу' })).toHaveAttribute(
        'href',
        '/room/m-active',
      );
    });

    it('правка названия и параметров запланированной встречи', async () => {
      const user = userEvent.setup();
      renderApp('/meetings/m-later', { user: organizer });
      await user.click(await screen.findByRole('button', { name: 'Изменить' }));
      const title = screen.getByLabelText('Название');
      await user.clear(title);
      await user.type(title, 'Интервью: backend');
      await user.selectOptions(screen.getByLabelText('Кадров в секунду'), '5');
      await user.click(screen.getByRole('button', { name: 'Сохранить' }));

      expect(
        await screen.findByRole('heading', { level: 1, name: 'Интервью: backend' }),
      ).toBeInTheDocument();
      await expect(meetingsApi.getMeeting('m-later')).resolves.toMatchObject({
        title: 'Интервью: backend',
        analysis_fps: 5,
      });
    });

    it('у начатой встречи правится только название', async () => {
      const user = userEvent.setup();
      renderApp('/meetings/m-active', { user: organizer });
      await user.click(await screen.findByRole('button', { name: 'Изменить' }));
      expect(screen.getByLabelText('Название')).toBeInTheDocument();
      expect(screen.queryByLabelText('Кадров в секунду')).not.toBeInTheDocument();
      expect(screen.getByText(/можно изменить только название/)).toBeInTheDocument();
    });

    it('meeting_not_editable от сервера – понятное сообщение', async () => {
      vi.spyOn(meetingsApi, 'updateMeeting').mockRejectedValueOnce(
        new ApiError({ status: 409, code: 'meeting_not_editable', message: 'x' }),
      );
      const user = userEvent.setup();
      renderApp('/meetings/m-later', { user: organizer });
      await user.click(await screen.findByRole('button', { name: 'Изменить' }));
      await user.type(screen.getByLabelText('Название'), '!');
      await user.click(screen.getByRole('button', { name: 'Сохранить' }));
      expect(await screen.findByRole('alert')).toHaveTextContent(/изменить нельзя/);
    });

    it('удаление: только после подтверждения, потом возврат к списку', async () => {
      const user = userEvent.setup();
      const router = renderApp('/meetings/m-later', { user: organizer });
      await user.click(await screen.findByRole('button', { name: 'Удалить' }));

      const dialog = screen.getByRole('alertdialog');
      expect(dialog).toHaveTextContent('Ссылка-приглашение перестанет работать');
      await expect(meetingsApi.getMeeting('m-later')).resolves.toBeDefined();

      await user.click(within(dialog).getByRole('button', { name: 'Отмена' }));
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
      await expect(meetingsApi.getMeeting('m-later')).resolves.toBeDefined();

      await user.click(screen.getByRole('button', { name: 'Удалить' }));
      await user.click(
        within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Удалить' }),
      );
      await waitFor(() => expect(router.state.location.pathname).toBe('/meetings'));
      await expect(meetingsApi.getMeeting('m-later')).rejects.toMatchObject({
        code: 'not_found',
      });
    });

    it('завершение: подтверждение, затем статус «Завершена»', async () => {
      const user = userEvent.setup();
      renderApp('/meetings/m-active', { user: organizer });
      await user.click(await screen.findByRole('button', { name: 'Завершить встречу' }));
      expect(screen.getByRole('alertdialog')).toHaveTextContent(/закончится для всех участников/);
      await expect(meetingsApi.getMeeting('m-active')).resolves.toMatchObject({
        status: 'active',
      });

      await user.click(
        within(screen.getByRole('alertdialog')).getByRole('button', {
          name: 'Завершить встречу',
        }),
      );
      expect(await screen.findByText('Завершена')).toBeInTheDocument();
      await expect(meetingsApi.getMeeting('m-active')).resolves.toMatchObject({
        status: 'ended',
      });
    });

    it('сбой загрузки – сообщение и «Повторить», а не «Встреча не найдена»', async () => {
      vi.spyOn(meetingsApi, 'getMeeting').mockRejectedValueOnce(
        new ApiError({ status: 0, code: 'network_error', message: 'x' }),
      );
      const user = userEvent.setup();
      renderApp('/meetings/m-later', { user: organizer });
      expect(
        await screen.findByRole('heading', { level: 1, name: 'Не удалось загрузить встречу' }),
      ).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: 'Повторить' }));
      expect(
        await screen.findByRole('heading', { level: 1, name: 'Интервью: frontend-разработчик' }),
      ).toBeInTheDocument();
    });
  });
});
