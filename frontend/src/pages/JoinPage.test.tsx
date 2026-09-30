import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router';

import { routes } from '@/app/routes';

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
  const router = createMemoryRouter(routes, { initialEntries: [`/j/${code}`] });
  render(<RouterProvider router={router} />);
  return router;
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
    expect(screen.getByRole('status')).toHaveTextContent('Встреча еще не началась');
  });

  it.each([
    ['demoended2', 'Встреча завершена'],
    ['nosuchcode', 'Приглашение не найдено'],
  ])('%s – «%s»', async (code, heading) => {
    renderLobby(code);
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument();
  });
});
