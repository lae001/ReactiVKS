import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router';

import { meetingsApi } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';
import type { RoomEntry } from '@/shared/lib/room-entry';

import { RoomShell } from './RoomShell';

const lk = vi.hoisted(() => ({
  participants: [] as unknown[],
  messages: [] as unknown[],
  send: vi.fn(),
  disconnect: vi.fn(),
  setMic: vi.fn(),
  setCamera: vi.fn(),
  publishData: vi.fn().mockResolvedValue(undefined),
  onData: undefined as ((message: unknown) => void) | undefined,
  onSync: undefined as ((message: unknown) => void) | undefined,
}));

vi.mock('@livekit/components-react', () => ({
  useParticipants: () => lk.participants,
  useDataChannel: (topic: string, onMessage: (message: unknown) => void) => {
    if (topic === 'vks.reaction') lk.onData = onMessage;
    else lk.onSync = onMessage;
    return { send: vi.fn(), isSending: false, message: undefined };
  },
  useConnectionState: () => 'connected',
  useChat: () => ({ chatMessages: lk.messages, send: lk.send, isSending: false }),
  useLocalParticipant: () => ({
    localParticipant: {
      identity: 'p_org',
      setMicrophoneEnabled: lk.setMic,
      setCameraEnabled: lk.setCamera,
      publishData: lk.publishData,
    },
    isMicrophoneEnabled: true,
    isCameraEnabled: true,
  }),
  useRoomContext: () => ({ disconnect: lk.disconnect }),
  RoomAudioRenderer: () => null,
}));
vi.mock('./RoomGallery', () => ({
  RoomGallery: () => <section aria-label="Галерея участников" />,
}));
vi.mock('./DevicesMenu', () => ({ DevicesPanel: () => <p>Панель устройств</p> }));
vi.mock('./ConnectionBanner', () => ({ ConnectionBanner: () => null }));

const person = (
  identity: string,
  name: string,
  attributes: Record<string, string> = {},
  extra: Record<string, unknown> = {},
) => ({
  identity,
  name,
  attributes,
  isLocal: false,
  isMicrophoneEnabled: true,
  isCameraEnabled: true,
  ...extra,
});

const meeting = {
  id: 'm-1',
  title: 'Планерка',
  analysis_enabled: true,
  invite_url: 'https://vks.test/j/abc',
  invite_code: 'abc',
};
const organizerEntry: RoomEntry = {
  role: 'organizer',
  displayName: 'Иван',
  consent: 'denied',
  cameraOn: true,
  micOn: true,
};
const guestEntry: RoomEntry = { ...organizerEntry, role: 'guest', displayName: 'Анна' };

function renderShell(entry: RoomEntry, room: typeof meeting = meeting) {
  const router = createMemoryRouter(
    [
      {
        path: '/room/m-1',
        element: (
          <QueryClientProvider client={new QueryClient()}>
            <RoomShell
              meeting={room}
              entry={entry}
              deviceNotice={null}
              onDismissNotice={() => undefined}
              onDeviceNotice={() => undefined}
            />
          </QueryClientProvider>
        ),
      },
      { path: '/meetings/:id', element: <p>карточка встречи</p> },
    ],
    { initialEntries: ['/room/m-1'] },
  );
  render(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  lk.participants = [
    person(
      'p_org',
      'Иван Петров',
      { 'vks.role': 'organizer', 'vks.consent': 'denied' },
      { isLocal: true },
    ),
    person('p_g1', 'Анна Гостева', { 'vks.role': 'guest', 'vks.consent': 'granted' }),
  ];
  lk.messages = [];
  lk.send.mockReset().mockResolvedValue(undefined);
  lk.disconnect.mockReset();
  lk.publishData.mockClear();
});
afterEach(() => vi.restoreAllMocks());

describe('шапка комнаты', () => {
  it('«Идет анализ эмоций» только пока в комнате есть агент', () => {
    renderShell(guestEntry);
    expect(screen.queryByText('Идет анализ эмоций')).not.toBeInTheDocument();
  });

  it('агент в комнате – индикатор виден, а в участниках его нет', async () => {
    lk.participants = [
      ...lk.participants,
      person('agent', 'emotion-agent', { 'vks.kind': 'agent' }),
    ];
    const user = userEvent.setup();
    renderShell(guestEntry);
    expect(screen.getByText('Идет анализ эмоций')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Участники' }));
    const panel = screen.getByRole('tabpanel');
    expect(within(panel).queryByText('emotion-agent')).not.toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Участники · 2/ })).toBeInTheDocument();
  });

  it('организатор видит ссылку «Пригласить», гость – нет', () => {
    renderShell(organizerEntry);
    expect(screen.getByRole('button', { name: /Пригласить/ })).toBeInTheDocument();
  });
});

describe('панель управления', () => {
  it('русские подписи: микрофон, камера, участники, чат, выход', () => {
    renderShell(guestEntry);
    const bar = screen.getByRole('contentinfo', { name: 'Управление встречей' });
    for (const name of ['Микрофон', 'Камера', 'Участники', 'Чат', 'Выйти']) {
      expect(within(bar).getByRole('button', { name })).toBeInTheDocument();
    }
    expect(
      within(bar).queryByRole('button', { name: 'Завершить встречу' }),
    ).not.toBeInTheDocument();
  });

  it('микрофон и камера переключаются через localParticipant', async () => {
    const user = userEvent.setup();
    renderShell(guestEntry);
    await user.click(screen.getByRole('button', { name: 'Микрофон' }));
    await user.click(screen.getByRole('button', { name: 'Камера' }));
    expect(lk.setMic).toHaveBeenCalledWith(false);
    expect(lk.setCamera).toHaveBeenCalledWith(false);
  });

  it('«Выйти» отключает от комнаты', async () => {
    const user = userEvent.setup();
    renderShell(guestEntry);
    await user.click(screen.getByRole('button', { name: 'Выйти' }));
    expect(lk.disconnect).toHaveBeenCalled();
  });
});

describe('чат (lk.chat)', () => {
  it('показывает сообщения: свои как «Вы», чужие по имени из токена', async () => {
    lk.messages = [
      {
        id: '1',
        timestamp: Date.UTC(2026, 9, 28, 10, 5),
        message: 'Привет',
        from: person('p_g1', 'Анна Гостева'),
      },
      {
        id: '2',
        timestamp: Date.UTC(2026, 9, 28, 10, 6),
        message: 'Здравствуйте',
        from: person('p_org', 'Иван Петров', {}, { isLocal: true }),
      },
    ];
    const user = userEvent.setup();
    renderShell(guestEntry);
    await user.click(screen.getByRole('button', { name: 'Чат' }));
    const list = screen.getByRole('list');
    expect(within(list).getByText('Привет')).toBeInTheDocument();
    expect(within(list).getByText(/^Анна Гостева ·/)).toBeInTheDocument();
    expect(within(list).getByText(/^Вы ·/)).toBeInTheDocument();
  });

  it('отправка идет через useChat; сбой отправки – сообщение', async () => {
    const user = userEvent.setup();
    renderShell(guestEntry);
    await user.click(screen.getByRole('button', { name: 'Чат' }));
    await user.type(screen.getByLabelText('Сообщение'), 'Всем привет');
    await user.click(screen.getByRole('button', { name: 'Отправить' }));
    expect(lk.send).toHaveBeenCalledWith('Всем привет');

    lk.send.mockRejectedValueOnce(new Error('offline'));
    await user.type(screen.getByLabelText('Сообщение'), 'ещё');
    await user.click(screen.getByRole('button', { name: 'Отправить' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/Не удалось отправить сообщение/);
  });

  it('сообщения не сохраняются: в хранилищах браузера их нет', async () => {
    lk.messages = [{ id: '1', timestamp: Date.now(), message: 'секрет', from: undefined }];
    const user = userEvent.setup();
    renderShell(guestEntry);
    await user.click(screen.getByRole('button', { name: 'Чат' }));
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain('секрет');
  });
});

describe('модерация организатора (REST, с подтверждением)', () => {
  async function openParticipants() {
    const user = userEvent.setup();
    const router = renderShell(organizerEntry);
    await user.click(screen.getByRole('button', { name: 'Участники' }));
    return { user, router };
  }

  it('у гостя кнопок модерации нет', async () => {
    const user = userEvent.setup();
    renderShell(guestEntry);
    await user.click(screen.getByRole('button', { name: 'Участники' }));
    expect(screen.queryByRole('button', { name: /Выключить микрофон:/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Удалить из встречи:/ })).not.toBeInTheDocument();
  });

  it.each([
    ['Выключить микрофон: Анна Гостева', 'Выключить микрофон', 'audio'],
    ['Выключить камеру: Анна Гостева', 'Выключить камеру', 'video'],
  ] as const)(
    '%s – только после подтверждения, id без префикса p_',
    async (button, confirmLabel, kind) => {
      const mute = vi.spyOn(meetingsApi, 'muteParticipant').mockResolvedValue();
      const { user } = await openParticipants();

      await user.click(screen.getByRole('button', { name: button }));
      const dialog = screen.getByRole('alertdialog');
      expect(mute).not.toHaveBeenCalled();
      await user.click(within(dialog).getByRole('button', { name: 'Отмена' }));
      expect(mute).not.toHaveBeenCalled();

      await user.click(screen.getByRole('button', { name: button }));
      await user.click(
        within(screen.getByRole('alertdialog')).getByRole('button', { name: confirmLabel }),
      );
      await waitFor(() => expect(mute).toHaveBeenCalledWith('m-1', 'g1', kind));
      await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    },
  );

  it('удаление участника – подтверждение и REST remove', async () => {
    const remove = vi.spyOn(meetingsApi, 'removeParticipant').mockResolvedValue();
    const { user } = await openParticipants();
    await user.click(screen.getByRole('button', { name: 'Удалить из встречи: Анна Гостева' }));
    expect(
      screen.getByRole('alertdialog', { name: 'Удалить из встречи: Анна Гостева?' }),
    ).toBeVisible();
    expect(remove).not.toHaveBeenCalled();
    await user.click(
      within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Удалить из встречи' }),
    );
    await waitFor(() => expect(remove).toHaveBeenCalledWith('m-1', 'g1'));
  });

  it('сбой REST: сообщение в диалоге, диалог остается для повтора', async () => {
    vi.spyOn(meetingsApi, 'removeParticipant').mockRejectedValue(
      new ApiError({ status: 503, code: 'livekit_unavailable', message: 'x' }),
    );
    const { user } = await openParticipants();
    await user.click(screen.getByRole('button', { name: 'Удалить из встречи: Анна Гостева' }));
    await user.click(
      within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Удалить из встречи' }),
    );
    expect(await screen.findByText(/Видеосервер сейчас недоступен/)).toBeVisible();
    expect(screen.getByRole('alertdialog')).toBeVisible();
  });

  it('«Завершить встречу» – подтверждение, POST end, переход в карточку', async () => {
    const end = vi.spyOn(meetingsApi, 'endMeeting').mockResolvedValue({} as never);
    const user = userEvent.setup();
    const router = renderShell(organizerEntry);

    await user.click(screen.getByRole('button', { name: 'Завершить встречу' }));
    const dialog = screen.getByRole('alertdialog', { name: 'Завершить встречу для всех?' });
    expect(end).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole('button', { name: 'Завершить встречу' }));
    await waitFor(() => expect(end).toHaveBeenCalledWith('m-1'));
    await waitFor(() => expect(router.state.location.pathname).toBe('/meetings/m-1'));
  });

  it('«Выйти» у организатора не завершает встречу', async () => {
    const end = vi.spyOn(meetingsApi, 'endMeeting');
    const user = userEvent.setup();
    renderShell(organizerEntry);
    await user.click(screen.getByRole('button', { name: 'Выйти' }));
    expect(lk.disconnect).toHaveBeenCalled();
    expect(end).not.toHaveBeenCalled();
  });
});

describe('согласие на анализ (PUT /participants/me/consent)', () => {
  const toggle = () => screen.getByRole('button', { name: 'Анализ моих эмоций' });

  it('состояние кнопки – из атрибута vks.consent в LiveKit', () => {
    lk.participants = [
      person('p_g1', 'Анна', { 'vks.role': 'guest', 'vks.consent': 'granted' }, { isLocal: true }),
    ];
    renderShell(guestEntry);
    expect(toggle()).toHaveAttribute('aria-pressed', 'true');
    expect(toggle()).toHaveTextContent('Анализ вкл.');
  });

  it('гость: отзыв идет с Participant-токеном (без meeting_id) и сразу виден', async () => {
    lk.participants = [
      person('p_g1', 'Анна', { 'vks.role': 'guest', 'vks.consent': 'granted' }, { isLocal: true }),
    ];
    const set = vi
      .spyOn(meetingsApi, 'setConsent')
      .mockResolvedValue({ consent_state: 'revoked', synced: true });
    const user = userEvent.setup();
    renderShell(guestEntry);
    await user.click(toggle());
    expect(set).toHaveBeenCalledWith('revoked', undefined);
    await waitFor(() => expect(toggle()).toHaveAttribute('aria-pressed', 'false'));
    expect(screen.getByText(/Анализ ваших эмоций отключен/)).toBeInTheDocument();
  });

  it('организатор: Bearer и meeting_id; включение анализа', async () => {
    const set = vi
      .spyOn(meetingsApi, 'setConsent')
      .mockResolvedValue({ consent_state: 'granted', synced: false });
    const user = userEvent.setup();
    renderShell(organizerEntry);
    await user.click(toggle());
    expect(set).toHaveBeenCalledWith('granted', { meetingId: 'm-1' });
    await waitFor(() => expect(toggle()).toHaveAttribute('aria-pressed', 'true'));
  });

  it('во встрече анализ выключен – переключателя и вкладки «Эмоции» нет', () => {
    renderShell(organizerEntry, { ...meeting, analysis_enabled: false });
    expect(screen.queryByRole('button', { name: 'Анализ моих эмоций' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Эмоции' })).not.toBeInTheDocument();
  });

  it('analysis_disabled: сообщение, переключатель пропадает', async () => {
    vi.spyOn(meetingsApi, 'setConsent').mockRejectedValue(
      new ApiError({ status: 409, code: 'analysis_disabled', message: 'x' }),
    );
    const user = userEvent.setup();
    renderShell(guestEntry);
    await user.click(toggle());
    expect(await screen.findByRole('alert')).toHaveTextContent(/анализ эмоций выключен/);
    expect(screen.queryByRole('button', { name: 'Анализ моих эмоций' })).not.toBeInTheDocument();
  });

  it.each([404, 405])(
    '%i (сервер не поддерживает согласие): переключатель остается, сообщение «Пока недоступно»',
    async (status) => {
      lk.participants = [
        person(
          'p_g1',
          'Анна',
          { 'vks.role': 'guest', 'vks.consent': 'granted' },
          { isLocal: true },
        ),
      ];
      vi.spyOn(meetingsApi, 'setConsent').mockRejectedValue(
        new ApiError({
          status,
          code: status === 404 ? 'not_found' : 'unknown_error',
          message: 'x',
        }),
      );
      const user = userEvent.setup();
      renderShell(guestEntry);
      await user.click(toggle());
      expect(await screen.findByRole('alert')).toHaveTextContent(
        'Пока недоступно: сервер ещё не поддерживает эту функцию.',
      );
      expect(toggle()).toHaveAttribute('aria-pressed', 'true');
      expect(toggle()).toHaveTextContent('Анализ вкл.');
    },
  );

  it('notice_outdated: показывается новое уведомление, согласие – после «Разрешаю анализ»', async () => {
    const set = vi
      .spyOn(meetingsApi, 'setConsent')
      .mockRejectedValueOnce(new ApiError({ status: 409, code: 'notice_outdated', message: 'x' }))
      .mockResolvedValueOnce({ consent_state: 'granted', synced: true });
    const info = vi.spyOn(meetingsApi, 'getJoinInfo').mockResolvedValue({
      title: 'Планерка',
      organizer_name: 'Иван',
      status: 'active',
      scheduled_at: null,
      analysis_enabled: true,
      consent_notice: { version: 'v2', text_md: 'Новый текст уведомления' },
    });
    const user = userEvent.setup();
    renderShell(guestEntry);
    await user.click(toggle());

    const dialog = await screen.findByRole('alertdialog', {
      name: 'Обновилось уведомление об анализе эмоций',
    });
    expect(info).toHaveBeenCalledWith('abc');
    expect(within(dialog).getByText('Новый текст уведомления')).toBeVisible();
    expect(set).toHaveBeenCalledTimes(1);

    await user.click(within(dialog).getByRole('button', { name: 'Разрешаю анализ' }));
    await waitFor(() => expect(set).toHaveBeenCalledTimes(2));
    expect(set).toHaveBeenLastCalledWith('granted', undefined);
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  });

  it('notice_outdated второй раз подряд – просим перезагрузить страницу, без цикла', async () => {
    vi.spyOn(meetingsApi, 'setConsent').mockRejectedValue(
      new ApiError({ status: 409, code: 'notice_outdated', message: 'x' }),
    );
    vi.spyOn(meetingsApi, 'getJoinInfo').mockResolvedValue({
      title: 'Планерка',
      organizer_name: 'Иван',
      status: 'active',
      scheduled_at: null,
      analysis_enabled: true,
      consent_notice: { version: 'v2', text_md: 'Текст' },
    });
    const user = userEvent.setup();
    renderShell(guestEntry);
    await user.click(toggle());
    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: 'Разрешаю анализ' }));
    expect(await within(screen.getByRole('alertdialog')).findByRole('alert')).toHaveTextContent(
      /Перезагрузите страницу/,
    );
  });

  it('401 гостя – «Вас удалили из встречи или сессия недействительна»', async () => {
    vi.spyOn(meetingsApi, 'setConsent').mockRejectedValue(
      new ApiError({ status: 401, code: 'unauthorized', message: 'x' }),
    );
    const user = userEvent.setup();
    renderShell(guestEntry);
    await user.click(toggle());
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Вас удалили из встречи или сессия недействительна.',
    );
  });
});

describe('панель эмоций (на моке)', () => {
  it('организатор: вкладка «Эмоции» с явной пометкой «Демонстрационные данные» и настоящими участниками', async () => {
    const user = userEvent.setup();
    renderShell(organizerEntry);
    await user.click(screen.getByRole('button', { name: 'Эмоции' }));
    const panel = screen.getByRole('tabpanel');
    expect(within(panel).getByRole('note')).toHaveTextContent(/Демонстрационные данные/);
    expect(within(panel).getByText('Сводка встречи')).toBeInTheDocument();
    expect(within(panel).getAllByText('Анна Гостева').length).toBeGreaterThan(0);
  });

  it('гость панели эмоций не видит', () => {
    renderShell(guestEntry);
    expect(screen.queryByRole('button', { name: 'Эмоции' })).not.toBeInTheDocument();
  });
});

describe('уведомления о новых сообщениях чата', () => {
  const incoming = (id: string, message: string) => ({
    id,
    timestamp: Date.now(),
    message,
    from: person('p_g1', 'Анна Гостева'),
  });

  beforeEach(() => {
    document.title = 'ReactiVKS';
  });
  afterEach(() => {
    document.title = 'ReactiVKS';
  });

  it('бейдж на «Чат», уведомление и заголовок; открытие чата обнуляет всё', async () => {
    const user = userEvent.setup();
    renderShell(guestEntry);
    // открыта другая вкладка – чат не виден
    await user.click(screen.getByRole('button', { name: 'Участники' }));
    lk.messages = [incoming('1', 'Привет'), incoming('2', 'Вы тут?')];
    await user.click(screen.getByRole('button', { name: 'Участники' }));
    await user.click(screen.getByRole('button', { name: 'Участники' }));

    const chatButton = screen.getByRole('button', { name: 'Чат, непрочитанных: 2' });
    expect(chatButton).toHaveTextContent('2');
    expect(screen.getByRole('status')).toHaveTextContent('Анна Гостева: Вы тут?');
    expect(document.title).toBe('(2) ReactiVKS');

    await user.click(chatButton);
    expect(screen.getByRole('button', { name: 'Чат' })).not.toHaveTextContent('2');
    expect(screen.getByRole('status')).toBeEmptyDOMElement();
    expect(document.title).toBe('ReactiVKS');
  });

  it('клик по уведомлению открывает чат', async () => {
    const user = userEvent.setup();
    renderShell(guestEntry);
    lk.messages = [incoming('1', 'Привет')];
    await user.click(screen.getByRole('button', { name: 'Участники' }));
    await user.click(screen.getByRole('button', { name: 'Анна Гостева: Привет' }));
    expect(screen.getByRole('tab', { name: 'Чат', selected: true })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Чат' })).toBeInTheDocument();
  });

  it('сообщения при открытом чате не накапливаются', async () => {
    const user = userEvent.setup();
    renderShell(guestEntry);
    await user.click(screen.getByRole('button', { name: 'Чат' }));
    lk.messages = [incoming('1', 'Привет')];
    await user.type(screen.getByLabelText('Сообщение'), 'а');
    expect(screen.getByRole('button', { name: 'Чат' })).toBeInTheDocument();
    expect(document.title).toBe('ReactiVKS');
  });
});

describe('реакции в комнате', () => {
  const REACTION_TOPIC = 'vks.reaction';
  const sent = (emoji: string) => new TextEncoder().encode(JSON.stringify({ v: 1, emoji }));

  it('кнопка «Реакции» → шесть реакций с подписями; выбор публикует данные, показывает эмодзи у отправителя и закрывает панель', async () => {
    const user = userEvent.setup();
    renderShell(guestEntry);
    await user.click(screen.getByRole('button', { name: 'Реакции' }));
    const group = screen.getByRole('group', { name: 'Выбор реакции' });
    expect(within(group).getAllByRole('button')).toHaveLength(6);

    await user.click(within(group).getByRole('button', { name: 'Реакция: аплодисменты' }));
    // запрос истории чата при входе уходит отдельно (тема vks.chat.sync); реакция – одна
    const reactionCalls = lk.publishData.mock.calls.filter(
      ([, opts]) => (opts as { topic: string }).topic === REACTION_TOPIC,
    );
    expect(reactionCalls).toHaveLength(1);
    const [data, options] = reactionCalls[0] as [Uint8Array, unknown];
    expect(new TextDecoder().decode(data)).toBe('{"v":1,"emoji":"👏"}');
    expect(options).toEqual({ reliable: false, topic: REACTION_TOPIC });
    expect(screen.getByTestId('reaction')).toHaveTextContent('👏');
    expect(screen.getByTestId('reaction')).toHaveTextContent('Вы');
    // панель закрылась, а на кнопке «Реакции» – ожидание лимита 1 в секунду без слова «часто»
    expect(screen.queryByRole('group', { name: 'Выбор реакции' })).not.toBeInTheDocument();
    const button = screen.getByRole('button', { name: /^Реакции\. Подождите \d+ с$/ });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(button.getAttribute('aria-label')).not.toMatch(/часто/);
  });

  it('чужая реакция: эмодзи с ником; в чат и в непрочитанные она не попадает', async () => {
    const user = userEvent.setup();
    renderShell(guestEntry);
    act(() =>
      lk.onData?.({
        topic: REACTION_TOPIC,
        payload: sent('👍'),
        from: person('p_g1', 'Анна Гостева'),
      }),
    );
    expect(screen.getByTestId('reaction')).toHaveTextContent('Анна Гостева');
    expect(screen.getByRole('button', { name: 'Чат' })).toBeInTheDocument(); // без счетчика
    expect(document.title).not.toMatch(/^\(/);

    await user.click(screen.getByRole('button', { name: 'Чат' }));
    expect(screen.getByRole('list')).not.toHaveTextContent('👍');
    expect(screen.getByRole('list')).not.toHaveTextContent('Анна Гостева');
  });

  it('оверлей не принимает клики и скрыт от скринридеров', () => {
    renderShell(guestEntry);
    act(() =>
      lk.onData?.({ topic: REACTION_TOPIC, payload: sent('🎉'), from: person('p_g1', 'Анна') }),
    );
    const overlay = screen.getByTestId('reaction').closest('[aria-hidden]');
    expect(overlay).toHaveAttribute('aria-hidden', 'true');
    expect(overlay).toHaveClass('pointer-events-none');
  });
});

describe('история чата и состояние вкладки', () => {
  beforeEach(() => {
    sessionStorage.clear();
    document.title = 'ReactiVKS';
  });
  afterEach(() => {
    sessionStorage.clear();
    document.title = 'ReactiVKS';
  });

  it('полученная при входе история видна в чате, но не считается непрочитанной и не вызывает уведомлений', async () => {
    const user = userEvent.setup();
    renderShell(guestEntry);
    const now = Date.now();
    const past = [1, 2, 3].map((n) => ({
      id: `h${n}`,
      from: 'p_g1',
      name: 'Анна Гостева',
      text: `раньше ${n}`,
      at: now - 60_000 + n * 1000,
    }));
    const payload = new TextEncoder().encode(
      JSON.stringify({ v: 1, type: 'history', part: 1, parts: 1, messages: past }),
    );
    act(() =>
      lk.onSync?.({ topic: 'vks.chat.sync', payload, from: person('p_g1', 'Анна Гостева') }),
    );
    // бейджа и уведомления нет
    expect(screen.getByRole('button', { name: 'Чат' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toBeEmptyDOMElement();
    expect(document.title).toBe('ReactiVKS');

    await user.click(screen.getByRole('button', { name: 'Чат' }));
    const list = screen.getByRole('list');
    expect(list).toHaveTextContent('раньше 1');
    expect(list).toHaveTextContent('раньше 3');
  });

  it('при входе в комнату уходит запрос истории; своя история из вкладки видна сразу', async () => {
    sessionStorage.setItem(
      'vks.room.chat.m-1',
      JSON.stringify([
        {
          id: 's1',
          from: 'p_org',
          name: 'Иван',
          text: 'я писал до обновления',
          at: Date.now() - 5000,
        },
      ]),
    );
    const user = userEvent.setup();
    renderShell(guestEntry);
    const requests = lk.publishData.mock.calls.filter(
      ([, opts]) => (opts as { topic: string }).topic === 'vks.chat.sync',
    );
    expect(requests).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'Чат' }));
    expect(screen.getByRole('list')).toHaveTextContent('Вы · ');
    expect(screen.getByRole('list')).toHaveTextContent('я писал до обновления');
  });

  it('микрофон и камера: каждое переключение запоминается во вкладке', async () => {
    const user = userEvent.setup();
    renderShell(guestEntry);
    await user.click(screen.getByRole('button', { name: 'Микрофон' }));
    expect(JSON.parse(sessionStorage.getItem('vks.room.devices.m-1')!)).toEqual({
      mic: false,
      camera: true,
    });
    // (в подмене useLocalParticipant состояние устройств не меняется само, поэтому микрофон здесь снова «включен»)
    await user.click(screen.getByRole('button', { name: 'Камера' }));
    expect(JSON.parse(sessionStorage.getItem('vks.room.devices.m-1')!)).toEqual({
      mic: true,
      camera: false,
    });
  });

  it('явный выход («Выйти») очищает сохраненное состояние и отключает от комнаты', async () => {
    sessionStorage.setItem('vks.room.devices.m-1', '{"mic":false,"camera":true}');
    sessionStorage.setItem('vks.room.chat.m-1', '[]');
    sessionStorage.setItem('vks.room.startedAt.m-1', '123');
    await userEvent
      .setup()
      .click((renderShell(guestEntry), screen.getByRole('button', { name: 'Выйти' })));
    expect(lk.disconnect).toHaveBeenCalled();
    expect(sessionStorage.getItem('vks.room.devices.m-1')).toBeNull();
    expect(sessionStorage.getItem('vks.room.chat.m-1')).toBeNull();
    expect(sessionStorage.getItem('vks.room.startedAt.m-1')).toBeNull();
  });

  it('завершение встречи организатором очищает сохраненное состояние', async () => {
    sessionStorage.setItem('vks.room.devices.m-1', '{"mic":false,"camera":true}');
    sessionStorage.setItem('vks.room.chat.m-1', '[]');
    vi.spyOn(meetingsApi, 'endMeeting').mockResolvedValue({} as never);
    const user = userEvent.setup();
    renderShell(organizerEntry);
    await user.click(screen.getByRole('button', { name: 'Завершить встречу' }));
    await user.click(
      within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Завершить встречу' }),
    );
    await waitFor(() => expect(sessionStorage.getItem('vks.room.devices.m-1')).toBeNull());
    expect(sessionStorage.getItem('vks.room.chat.m-1')).toBeNull();
  });
});

describe('счетчик «Участники · N»: только люди', () => {
  it('служебные участники (агент, egress) и их плитки не считаются; одинаковые имена – отдельные люди', async () => {
    lk.participants = [
      person('p_org', 'Иван', { 'vks.role': 'organizer' }, { isLocal: true }),
      person('p_a', 'Анна', { 'vks.role': 'guest' }),
      person('p_b', 'Анна', { 'vks.role': 'guest' }),
      person('agent-1', 'emotion-agent', { 'vks.kind': 'agent' }),
      person('egress-1', 'recorder', {}, { kind: 2 }), // ParticipantKind.EGRESS
    ];
    const user = userEvent.setup();
    renderShell(organizerEntry);
    await user.click(screen.getByRole('button', { name: 'Участники' }));
    expect(screen.getByRole('tab', { name: 'Участники · 3' })).toBeInTheDocument();
    expect(within(screen.getByRole('tabpanel')).queryByText('recorder')).not.toBeInTheDocument();
    expect(within(screen.getByRole('tabpanel')).getAllByText('Анна')).toHaveLength(2);
  });
});
