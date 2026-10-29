import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { MEETING_ERROR_CODES, meetingsApi } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';
import { getParticipantToken } from '@/shared/lib/participant-session';
import { mockNoSession, organizer } from '@/test/api-mocks';
import { installFakeMediaDevices } from '@/test/fake-media';
import { renderApp } from '@/test/render';

function renderLobby(code: string) {
  mockNoSession();
  return renderApp(`/j/${code}`);
}

describe('лобби участника', () => {
  beforeEach(() => void installFakeMediaDevices());
  afterEach(() => vi.unstubAllGlobals());

  it('без явного выбора согласия войти нельзя', async () => {
    const user = userEvent.setup();
    const router = renderLobby('demoactive');

    await screen.findByRole('heading', { level: 1, name: 'Еженедельная планерка команды' });
    const granted = screen.getByRole('radio', { name: /Разрешаю анализ/ });
    const denied = screen.getByRole('radio', { name: /Участвую без анализа/ });
    expect(granted).not.toBeChecked();
    expect(denied).not.toBeChecked();

    await user.type(screen.getByLabelText('Как вас представить'), 'Анна');
    await user.click(screen.getByRole('button', { name: 'Войти во встречу' }));
    expect(screen.getByText(/Без выбора войти нельзя/)).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/j/demoactive');

    await user.click(granted);
    await user.click(screen.getByRole('button', { name: 'Войти во встречу' }));
    // комната загружается лениво – переход завершается после загрузки модуля
    await waitFor(() => expect(router.state.location.pathname).toBe('/room/m-active'));
    expect(getParticipantToken()).toMatch(/^pt_/);
    expect(router.state.location.state).toMatchObject({
      role: 'guest',
      displayName: 'Анна',
      consent: 'granted',
    });
  });

  it('ни один вариант согласия не выбран по умолчанию; «без анализа» – тоже явный выбор', async () => {
    const user = userEvent.setup();
    const router = renderLobby('demoactive');
    await user.type(await screen.findByLabelText('Как вас представить'), 'Олег');
    expect(screen.queryByRole('radio', { checked: true })).not.toBeInTheDocument();

    // повторная попытка без выбора тоже не пускает
    await user.click(screen.getByRole('button', { name: 'Войти во встречу' }));
    await user.click(screen.getByRole('button', { name: 'Войти во встречу' }));
    expect(screen.getByText(/Без выбора войти нельзя/)).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/j/demoactive');

    await user.click(screen.getByRole('radio', { name: /Участвую без анализа/ }));
    expect(screen.queryByText(/Без выбора войти нельзя/)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Войти во встречу' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/room/m-active'));
    expect(router.state.location.state).toMatchObject({ consent: 'denied' });
  });

  it('без имени войти нельзя', async () => {
    const user = userEvent.setup();
    renderLobby('demoactive');
    await user.click(await screen.findByRole('radio', { name: /Участвую без анализа/ }));
    await user.click(screen.getByRole('button', { name: 'Войти во встречу' }));
    expect(screen.getByText(/Укажите имя/)).toBeInTheDocument();
  });

  it('анализ выключен – блока согласия нет', async () => {
    const user = userEvent.setup();
    const router = renderLobby('demonoanal');
    await user.type(await screen.findByLabelText('Как вас представить'), 'Олег');
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Войти во встречу' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/room/m-noanal'));
    expect(router.state.location.state).toMatchObject({ consent: 'not_required' });
  });

  it('встреча еще не началась – ожидание', async () => {
    const user = userEvent.setup();
    renderLobby('demolater2');
    await user.type(await screen.findByLabelText('Как вас представить'), 'Мария');
    await user.click(screen.getByRole('radio', { name: /Участвую без анализа/ }));
    await user.click(screen.getByRole('button', { name: 'Войти во встречу' }));
    const status = await screen.findByText('Встреча еще не началась');
    expect(status.closest('[role="status"]')).toHaveTextContent(
      'Проверяем каждые 5 секунд и войдем сами',
    );
    expect(screen.queryByText(/Обновите страницу/)).not.toBeInTheDocument();
  });

  it.each([
    ['demoended2', 'Встреча завершена'],
    ['nosuchcode', 'Приглашение не найдено'],
  ])('%s – «%s»', async (code, heading) => {
    renderLobby(code);
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument();
  });

  describe('ошибки POST /join/{invite_code}', () => {
    async function submitAsAnna(code = 'demoactive') {
      const user = userEvent.setup();
      const router = renderLobby(code);
      await user.type(await screen.findByLabelText('Как вас представить'), 'Анна');
      await user.click(screen.getByRole('radio', { name: /Разрешаю анализ/ }));
      await user.click(screen.getByRole('button', { name: 'Войти во встречу' }));
      return { user, router };
    }

    function rejectJoinWith(code: string, status = 409, extra: Partial<ApiError> = {}) {
      vi.spyOn(meetingsApi, 'joinMeeting').mockRejectedValueOnce(
        new ApiError({ status, code, message: code, ...extra }),
      );
    }

    afterEach(() => vi.restoreAllMocks());

    it('в отправку уходит версия уведомления и решение о согласии', async () => {
      const spy = vi.spyOn(meetingsApi, 'joinMeeting');
      await submitAsAnna();
      await waitFor(() => expect(spy).toHaveBeenCalled());
      expect(spy).toHaveBeenCalledWith('demoactive', {
        display_name: 'Анна',
        consent: 'granted',
        notice_version: 'v1-draft',
      });
    });

    it.each([
      ['meeting_ended', 'Встреча завершена'],
      ['meeting_cancelled', 'Встреча отменена'],
    ])('%s – экран «%s», токен не сохраняется', async (code, heading) => {
      rejectJoinWith(code);
      await submitAsAnna();
      expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument();
      expect(getParticipantToken()).toBeNull();
    });

    it.each([
      ['meeting_full', 409, /уже 10 участников/],
      ['consent_required', 409, /Выберите вариант согласия/],
      ['livekit_unavailable', 503, /Видеосервер сейчас недоступен/],
      ['too_many_requests', 429, /Слишком много запросов/],
      ['network_error', 0, /Не удалось связаться с сервером/],
    ])('%s – сообщение под формой, вход остается доступным', async (code, status, text) => {
      rejectJoinWith(code, status);
      const { router } = await submitAsAnna();
      expect(await screen.findByRole('alert')).toHaveTextContent(text);
      expect(screen.getByRole('button', { name: 'Войти во встречу' })).toBeEnabled();
      expect(router.state.location.pathname).toBe('/j/demoactive');
    });

    it('notice_outdated – выбор согласия сбрасывается, нужно выбрать заново', async () => {
      rejectJoinWith('notice_outdated');
      await submitAsAnna();
      expect(await screen.findByRole('alert')).toHaveTextContent(/Уведомление .* обновилось/);
      expect(screen.getByRole('radio', { name: /Разрешаю анализ/ })).not.toBeChecked();
    });

    it('422 по полю display_name – ошибка у поля имени', async () => {
      vi.spyOn(meetingsApi, 'joinMeeting').mockRejectedValueOnce(
        new ApiError({
          status: 422,
          code: 'validation_error',
          message: 'v',
          errors: [{ loc: ['body', 'display_name'], msg: 'Имя слишком длинное', type: 'x' }],
        }),
      );
      await submitAsAnna();
      expect(await screen.findByText('Имя слишком длинное')).toBeInTheDocument();
    });

    it('meeting_full на настоящем mock: комната заполнена', async () => {
      const user = userEvent.setup();
      renderLobby('demofull22');
      await user.type(await screen.findByLabelText('Как вас представить'), 'Анна');
      await user.click(screen.getByRole('button', { name: 'Войти во встречу' }));
      expect(await screen.findByRole('alert')).toHaveTextContent(/уже 10 участников/);
    });

    it('отмененная встреча по ссылке – экран «Встреча отменена»', async () => {
      renderLobby('democancel');
      expect(
        await screen.findByRole('heading', { level: 1, name: 'Встреча отменена' }),
      ).toBeInTheDocument();
    });

    it('сбой загрузки приглашения – сообщение, не «не найдено»', async () => {
      vi.spyOn(meetingsApi, 'getJoinInfo').mockRejectedValueOnce(
        new ApiError({ status: 0, code: 'network_error', message: 'x' }),
      );
      renderLobby('demoactive');
      expect(
        await screen.findByRole('heading', { level: 1, name: 'Не удалось открыть приглашение' }),
      ).toBeInTheDocument();
    });
  });

  describe('ожидание начала встречи', () => {
    const notStarted = () =>
      new ApiError({ status: 409, code: 'meeting_not_started', message: 'not started' });

    async function submitAndWait(code = 'demoactive') {
      const user = userEvent.setup({ delay: null });
      const router = renderLobby(code);
      await user.type(await screen.findByLabelText('Как вас представить'), 'Мария');
      await user.click(screen.getByRole('radio', { name: /Участвую без анализа/ }));
      // таймеры подменяем после загрузки страницы: react-query сам использует setTimeout
      // RTL после каждого user.click ждет setTimeout(0), под подменой таймеров он не сработает
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
      fireEvent.click(screen.getByRole('button', { name: 'Войти во встречу' }));
      await act(() => vi.advanceTimersByTimeAsync(0));
      return { user, router };
    }

    afterEach(() => {
      vi.useRealTimers();
      vi.restoreAllMocks();
    });

    it('повторяет вход раз в 5 секунд и входит сам, когда встреча началась', async () => {
      const spy = vi
        .spyOn(meetingsApi, 'joinMeeting')
        .mockRejectedValueOnce(notStarted())
        .mockRejectedValueOnce(notStarted());
      const { router } = await submitAndWait();
      expect(screen.getByText('Встреча еще не началась')).toBeInTheDocument();
      expect(spy).toHaveBeenCalledTimes(1);

      await act(() => vi.advanceTimersByTimeAsync(4_999));
      expect(spy).toHaveBeenCalledTimes(1);
      await act(() => vi.advanceTimersByTimeAsync(1));
      expect(spy).toHaveBeenCalledTimes(2);
      expect(screen.getByText('Встреча еще не началась')).toBeInTheDocument();

      // третий вызов уходит в настоящий mock: встреча активна
      await act(() => vi.advanceTimersByTimeAsync(5_000));
      expect(spy).toHaveBeenCalledTimes(3);
      await act(() => vi.advanceTimersByTimeAsync(0));
      expect(router.state.location.pathname).toBe('/room/m-active');
      expect(getParticipantToken()).toMatch(/^pt_/);
    });

    it('«Отменить ожидание» останавливает опрос', async () => {
      const spy = vi.spyOn(meetingsApi, 'joinMeeting').mockRejectedValue(notStarted());
      await submitAndWait();
      expect(screen.getByText('Встреча еще не началась')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'Отменить ожидание' }));
      expect(screen.getByRole('button', { name: 'Войти во встречу' })).toBeEnabled();
      await act(() => vi.advanceTimersByTimeAsync(60_000));
      expect(spy).toHaveBeenCalledTimes(1);
    });

    it('ответ запроса, отправленного до отмены, игнорируется', async () => {
      let finish: (() => void) | undefined;
      const real = meetingsApi.joinMeeting.bind(meetingsApi);
      const spy = vi
        .spyOn(meetingsApi, 'joinMeeting')
        .mockRejectedValueOnce(notStarted())
        .mockImplementationOnce(
          (...args) =>
            new Promise((resolve, reject) => {
              finish = () => real(...args).then(resolve, reject);
            }),
        );
      const { router } = await submitAndWait();
      expect(screen.getByText('Встреча еще не началась')).toBeInTheDocument();
      await act(() => vi.advanceTimersByTimeAsync(5_000));
      expect(spy).toHaveBeenCalledTimes(2);

      fireEvent.click(screen.getByRole('button', { name: 'Отменить ожидание' }));
      await act(async () => finish?.());
      await act(() => vi.advanceTimersByTimeAsync(1_000));
      expect(router.state.location.pathname).toBe('/j/demoactive');
      expect(getParticipantToken()).toBeNull();
    });

    it('через 10 минут ожидание прекращается и пользователю сообщают об этом', async () => {
      const spy = vi.spyOn(meetingsApi, 'joinMeeting').mockRejectedValue(notStarted());
      await submitAndWait();
      expect(screen.getByText('Встреча еще не началась')).toBeInTheDocument();

      await act(() => vi.advanceTimersByTimeAsync(10 * 60_000 + 5_000));
      expect(screen.getByRole('alert')).toHaveTextContent(/не началась за 10 минут/);
      expect(screen.queryByText('Встреча еще не началась')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Войти во встречу' })).toBeEnabled();
      const calls = spy.mock.calls.length;
      expect(calls).toBeGreaterThanOrEqual(120);
      expect(calls).toBeLessThanOrEqual(122);
      await act(() => vi.advanceTimersByTimeAsync(60_000));
      expect(spy).toHaveBeenCalledTimes(calls);
    });

    it('временный сбой при ожидании не прерывает опрос', async () => {
      const spy = vi
        .spyOn(meetingsApi, 'joinMeeting')
        .mockRejectedValueOnce(notStarted())
        .mockRejectedValueOnce(new ApiError({ status: 0, code: 'network_error', message: 'x' }));
      const { router } = await submitAndWait();
      expect(screen.getByText('Встреча еще не началась')).toBeInTheDocument();
      await act(() => vi.advanceTimersByTimeAsync(5_000));
      expect(spy).toHaveBeenCalledTimes(2);
      expect(screen.getByText('Встреча еще не началась')).toBeInTheDocument();

      await act(() => vi.advanceTimersByTimeAsync(5_000));
      expect(router.state.location.pathname).toBe('/room/m-active');
    });

    it('429 при опросе: ждем не меньше Retry-After', async () => {
      const spy = vi
        .spyOn(meetingsApi, 'joinMeeting')
        .mockRejectedValueOnce(notStarted())
        .mockRejectedValueOnce(
          new ApiError({ status: 429, code: 'too_many_requests', message: 'slow', retryAfter: 30 }),
        );
      const { router } = await submitAndWait();
      await act(() => vi.advanceTimersByTimeAsync(5_000));
      expect(spy).toHaveBeenCalledTimes(2);

      await act(() => vi.advanceTimersByTimeAsync(29_999));
      expect(spy).toHaveBeenCalledTimes(2);
      expect(screen.getByText('Встреча еще не началась')).toBeInTheDocument();
      await act(() => vi.advanceTimersByTimeAsync(1));
      expect(spy).toHaveBeenCalledTimes(3);
      expect(router.state.location.pathname).toBe('/room/m-active');
    });

    it('429 без Retry-After: обычный интервал 5 секунд', async () => {
      const spy = vi
        .spyOn(meetingsApi, 'joinMeeting')
        .mockRejectedValueOnce(notStarted())
        .mockRejectedValueOnce(
          new ApiError({ status: 429, code: 'too_many_requests', message: 'slow' }),
        );
      await submitAndWait();
      await act(() => vi.advanceTimersByTimeAsync(5_000));
      expect(spy).toHaveBeenCalledTimes(2);
      await act(() => vi.advanceTimersByTimeAsync(4_999));
      expect(spy).toHaveBeenCalledTimes(2);
      await act(() => vi.advanceTimersByTimeAsync(1));
      expect(spy).toHaveBeenCalledTimes(3);
    });

    it('Retry-After короче 5 секунд не ускоряет опрос', async () => {
      const spy = vi
        .spyOn(meetingsApi, 'joinMeeting')
        .mockRejectedValueOnce(notStarted())
        .mockRejectedValueOnce(
          new ApiError({ status: 429, code: 'too_many_requests', message: 's', retryAfter: 1 }),
        );
      await submitAndWait();
      await act(() => vi.advanceTimersByTimeAsync(5_000));
      await act(() => vi.advanceTimersByTimeAsync(4_999));
      expect(spy).toHaveBeenCalledTimes(2);
    });

    it('при ожидании встреча отменена – экран «Встреча отменена»', async () => {
      vi.spyOn(meetingsApi, 'joinMeeting')
        .mockRejectedValueOnce(notStarted())
        .mockRejectedValueOnce(
          new ApiError({ status: 409, code: 'meeting_cancelled', message: 'c' }),
        );
      await submitAndWait();
      expect(screen.getByText('Встреча еще не началась')).toBeInTheDocument();
      await act(() => vi.advanceTimersByTimeAsync(5_000));
      expect(
        screen.getByRole('heading', { level: 1, name: 'Встреча отменена' }),
      ).toBeInTheDocument();
    });

    it('при ожидании комната заполнена – опрос прекращается, сообщение под формой', async () => {
      const spy = vi
        .spyOn(meetingsApi, 'joinMeeting')
        .mockRejectedValueOnce(notStarted())
        .mockRejectedValueOnce(new ApiError({ status: 409, code: 'meeting_full', message: 'f' }));
      await submitAndWait();
      expect(screen.getByText('Встреча еще не началась')).toBeInTheDocument();
      await act(() => vi.advanceTimersByTimeAsync(5_000));
      expect(screen.getByRole('alert')).toHaveTextContent(/уже 10 участников/);
      await act(() => vi.advanceTimersByTimeAsync(30_000));
      expect(spy).toHaveBeenCalledTimes(2);
    });
  });

  describe('каждый код реестра на любом шаге', () => {
    const SCREENS: Record<string, string> = {
      meeting_ended: 'Встреча завершена',
      meeting_cancelled: 'Встреча отменена',
      participant_removed: 'Вас удалили из встречи',
      not_found: 'Приглашение не найдено',
      forbidden: 'Нет доступа',
      user_blocked: 'Доступ закрыт',
    };

    it.each(Object.entries(MEETING_ERROR_CODES))(
      '%s (HTTP %i) – экран или сообщение, страница не ломается',
      async (code, status) => {
        if (code === 'meeting_not_started') return; // отдельная ветка: ожидание
        vi.spyOn(meetingsApi, 'joinMeeting').mockRejectedValueOnce(
          new ApiError({ status, code, message: code }),
        );
        const user = userEvent.setup();
        renderLobby('demoactive');
        await user.type(await screen.findByLabelText('Как вас представить'), 'Анна');
        await user.click(screen.getByRole('radio', { name: /Разрешаю анализ/ }));
        await user.click(screen.getByRole('button', { name: 'Войти во встречу' }));

        const heading = SCREENS[code];
        if (heading) {
          expect(
            await screen.findByRole('heading', { level: 1, name: heading }),
          ).toBeInTheDocument();
        } else {
          const alert = await screen.findByRole('alert');
          expect(alert.textContent?.length).toBeGreaterThan(10);
          expect(screen.getByRole('button', { name: 'Войти во встречу' })).toBeEnabled();
        }
        vi.restoreAllMocks();
      },
    );

    it('401 на POST /join (токена еще нет) – общая ошибка входа, а не «вас удалили»', async () => {
      vi.spyOn(meetingsApi, 'joinMeeting').mockRejectedValueOnce(
        new ApiError({ status: 401, code: 'unauthorized', message: 'u' }),
      );
      const user = userEvent.setup();
      renderLobby('demoactive');
      await user.type(await screen.findByLabelText('Как вас представить'), 'Анна');
      await user.click(screen.getByRole('radio', { name: /Разрешаю анализ/ }));
      await user.click(screen.getByRole('button', { name: 'Войти во встречу' }));
      const alert = await screen.findByRole('alert');
      expect(alert).toHaveTextContent('Не удалось войти, попробуйте ещё раз.');
      expect(alert).not.toHaveTextContent('удалили');
      vi.restoreAllMocks();
    });

    it('экран «Вас удалили» называет встречу и организатора', async () => {
      vi.spyOn(meetingsApi, 'joinMeeting').mockRejectedValueOnce(
        new ApiError({ status: 403, code: 'participant_removed', message: 'p' }),
      );
      const user = userEvent.setup();
      renderLobby('demoactive');
      await user.type(await screen.findByLabelText('Как вас представить'), 'Анна');
      await user.click(screen.getByRole('radio', { name: /Разрешаю анализ/ }));
      await user.click(screen.getByRole('button', { name: 'Войти во встречу' }));
      expect(await screen.findByText(/Еженедельная планерка команды/)).toBeInTheDocument();
      expect(screen.getByText(/свяжитесь с организатором/)).toBeInTheDocument();
      vi.restoreAllMocks();
    });
  });
});

describe('лобби: выход без тупика', () => {
  beforeEach(() => void installFakeMediaDevices());
  afterEach(() => vi.unstubAllGlobals());

  it('вошедший организатор: «К встречам» на форме и на экранах-заглушках', async () => {
    const user = userEvent.setup();
    const router = renderApp('/j/demoactive', { user: organizer });
    await screen.findByRole('heading', { level: 1, name: 'Еженедельная планерка команды' });
    expect(screen.getByRole('link', { name: 'К встречам' })).toHaveAttribute('href', '/meetings');

    // завершенная встреча (экран-заглушка), отмененная и несуществующее приглашение
    for (const [code, title] of [
      ['demoended2', 'Встреча завершена'],
      ['democancel', 'Встреча отменена'],
      ['zzzzzzzzzz', 'Приглашение не найдено'],
    ] as const) {
      await act(() => router.navigate(`/j/${code}`));
      await screen.findByRole('heading', { level: 1, name: title });
      expect(screen.getByRole('link', { name: 'К встречам' })).toHaveAttribute('href', '/meetings');
    }
    await user.click(screen.getByRole('link', { name: 'К встречам' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/meetings'));
  });

  it('гость, пришедший по прямой ссылке: кнопки «Назад» нет', async () => {
    renderLobby('demoactive');
    await screen.findByRole('heading', { level: 1, name: 'Еженедельная планерка команды' });
    expect(screen.queryByRole('button', { name: /Назад/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'К встречам' })).not.toBeInTheDocument();
  });

  it('гость с историей приложения: «Назад» возвращает на предыдущую страницу, в том числе с заглушки', async () => {
    const user = userEvent.setup();
    const router = renderLobby('demoactive');
    await screen.findByRole('heading', { level: 1, name: 'Еженедельная планерка команды' });
    await act(() => router.navigate('/j/demoended2'));
    await screen.findByRole('heading', { level: 1, name: 'Встреча завершена' });

    await user.click(screen.getByRole('button', { name: /Назад/ }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/j/demoactive'));
    // вернулись на первую запись истории – дальше возвращаться некуда
    await screen.findByRole('heading', { level: 1, name: 'Еженедельная планерка команды' });
    expect(screen.queryByRole('button', { name: /Назад/ })).not.toBeInTheDocument();
  });
});
