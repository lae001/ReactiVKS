import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
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
}));

vi.mock('@livekit/components-react', () => ({
  useParticipants: () => lk.participants,
  useChat: () => ({ chatMessages: lk.messages, send: lk.send, isSending: false }),
  useLocalParticipant: () => ({
    localParticipant: { setMicrophoneEnabled: lk.setMic, setCameraEnabled: lk.setCamera },
    isMicrophoneEnabled: true,
    isCameraEnabled: true,
  }),
  useRoomContext: () => ({ disconnect: lk.disconnect }),
  RoomAudioRenderer: () => null,
}));
vi.mock('./RoomGallery', () => ({
  RoomGallery: () => <section aria-label="Галерея участников" />,
}));
vi.mock('./DevicesMenu', () => ({ DevicesMenu: () => null }));
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

const meeting = { id: 'm-1', title: 'Планерка', invite_url: 'https://vks.test/j/abc' };
const organizerEntry: RoomEntry = {
  role: 'organizer',
  displayName: 'Иван',
  consent: 'denied',
  cameraOn: true,
  micOn: true,
};
const guestEntry: RoomEntry = { ...organizerEntry, role: 'guest', displayName: 'Анна' };

function renderShell(entry: RoomEntry) {
  const router = createMemoryRouter(
    [
      {
        path: '/room/m-1',
        element: (
          <QueryClientProvider client={new QueryClient()}>
            <RoomShell
              meeting={meeting}
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
