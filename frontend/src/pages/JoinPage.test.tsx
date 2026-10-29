import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meetingsApi } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';
import { getParticipantToken } from '@/shared/lib/participant-session';
import { mockNoSession } from '@/test/api-mocks';
import { renderApp } from '@/test/render';

/** Браузер с WebRTC и камерой: без этого лобби не дает войти. */
function stubMediaBrowser() {
  const stream = { getTracks: () => [], getVideoTracks: () => [], getAudioTracks: () => [] };
  vi.stubGlobal('RTCPeerConnection', class {});
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
  Object.defineProperty(navigator, 'mediaDevices', {
    value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    configurable: true,
  });
}

function renderLobby(code: string) {
  mockNoSession();
  return renderApp(`/j/${code}`);
}

describe('лобби участника', () => {
  beforeEach(stubMediaBrowser);
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
      'Обновите страницу, когда встреча начнётся.',
    );
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
});
