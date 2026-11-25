import { act, renderHook, render, screen } from '@testing-library/react';

import {
  type IncomingChatMessage,
  MAX_TOASTS,
  TOAST_LIFETIME_MS,
  TOAST_TEXT_LIMIT,
  unreadBadge,
  useChatNotifications,
  useUnreadTitle,
} from './chat-notifications';
import { ChatToasts } from './ChatToasts';

const other = (id: string, message = `текст ${id}`, name = 'Анна'): IncomingChatMessage => ({
  id,
  message,
  from: { name, isLocal: false },
});
const mine = (id: string): IncomingChatMessage => ({
  id,
  message: 'мое',
  from: { name: 'Иван', isLocal: true },
});

function setup(initial: IncomingChatMessage[] = [], visible = false) {
  return renderHook(({ messages, chatVisible }) => useChatNotifications(messages, chatVisible), {
    initialProps: { messages: initial, chatVisible: visible },
  });
}

describe('непрочитанные сообщения чата', () => {
  it('счетчик растет от чужих сообщений и обнуляется при открытии чата', () => {
    const view = setup();
    view.rerender({ messages: [other('1')], chatVisible: false });
    view.rerender({ messages: [other('1'), other('2'), other('3')], chatVisible: false });
    expect(view.result.current.unread).toBe(3);

    act(() => view.result.current.markRead());
    expect(view.result.current.unread).toBe(0);
    expect(view.result.current.toasts).toEqual([]);
  });

  it('свои сообщения не считаются', () => {
    const view = setup();
    view.rerender({ messages: [mine('1'), mine('2')], chatVisible: false });
    expect(view.result.current.unread).toBe(0);
    expect(view.result.current.toasts).toEqual([]);
    view.rerender({ messages: [mine('1'), mine('2'), other('3')], chatVisible: false });
    expect(view.result.current.unread).toBe(1);
  });

  it('открытый чат ничего не накапливает', () => {
    const view = setup([], true);
    view.rerender({ messages: [other('1'), other('2')], chatVisible: true });
    expect(view.result.current.unread).toBe(0);
    expect(view.result.current.toasts).toEqual([]);
  });

  it('сообщения, пришедшие до появления хука, непрочитанными не считаются', () => {
    const view = setup([other('1'), other('2')]);
    expect(view.result.current.unread).toBe(0);
  });

  it('бейдж: «9+» после девяти', () => {
    expect(unreadBadge(1)).toBe('1');
    expect(unreadBadge(9)).toBe('9');
    expect(unreadBadge(10)).toBe('9+');
  });
});

describe('всплывающие уведомления', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  function renderToasts(initial: IncomingChatMessage[] = []) {
    const onOpen = vi.fn();
    const hook = setup(initial);
    const view = render(<span />);
    const show = () =>
      view.rerender(
        <ChatToasts
          toasts={hook.result.current.toasts}
          onOpen={onOpen}
          onExpire={hook.result.current.dismissToast}
        />,
      );
    return { hook, show, onOpen };
  }

  it('«Имя: текст», role="status"; через 4 с исчезает', () => {
    const { hook, show } = renderToasts();
    hook.rerender({ messages: [other('1', 'Привет всем')], chatVisible: false });
    show();
    expect(screen.getByRole('status')).toHaveTextContent('Анна: Привет всем');

    act(() => void vi.advanceTimersByTime(TOAST_LIFETIME_MS - 1));
    show();
    expect(screen.getByRole('status')).toHaveTextContent('Привет всем');
    act(() => void vi.advanceTimersByTime(1));
    show();
    expect(screen.getByRole('status')).toBeEmptyDOMElement();
  });

  it('текст длиннее 80 символов обрезается', () => {
    const { hook, show } = renderToasts();
    hook.rerender({ messages: [other('1', 'я'.repeat(200))], chatVisible: false });
    show();
    const text = screen.getByRole('button').textContent ?? '';
    expect(text).toContain('я'.repeat(TOAST_TEXT_LIMIT));
    expect(text).not.toContain('я'.repeat(TOAST_TEXT_LIMIT + 1));
    expect(text.endsWith('…')).toBe(true);
  });

  it(`не больше ${MAX_TOASTS} одновременно: старые вытесняются`, () => {
    const { hook, show } = renderToasts();
    const all = ['1', '2', '3', '4', '5'].map((id) => other(id));
    hook.rerender({ messages: all, chatVisible: false });
    show();
    const shown = screen.getAllByRole('button').map((b) => b.textContent);
    expect(shown).toHaveLength(MAX_TOASTS);
    expect(shown[0]).toContain('текст 3');
    expect(shown[2]).toContain('текст 5');
    // счетчик при этом считает все
    expect(hook.result.current.unread).toBe(5);
  });

  it('клик по уведомлению открывает чат', () => {
    const { hook, show, onOpen } = renderToasts();
    hook.rerender({ messages: [other('1')], chatVisible: false });
    show();
    act(() => screen.getByRole('button').click());
    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});

describe('заголовок вкладки', () => {
  beforeEach(() => {
    document.title = 'ReactiVKS';
  });

  it('«(3) ReactiVKS» при непрочитанных, после чтения как было, при размонтировании исходный', () => {
    const view = renderHook(({ unread }) => useUnreadTitle(unread), {
      initialProps: { unread: 0 },
    });
    expect(document.title).toBe('ReactiVKS');
    view.rerender({ unread: 3 });
    expect(document.title).toBe('(3) ReactiVKS');
    view.rerender({ unread: 12 });
    expect(document.title).toBe('(9+) ReactiVKS');
    view.rerender({ unread: 0 });
    expect(document.title).toBe('ReactiVKS');

    view.rerender({ unread: 2 });
    expect(document.title).toBe('(2) ReactiVKS');
    view.unmount();
    expect(document.title).toBe('ReactiVKS');
  });
});
