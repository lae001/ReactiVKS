import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ControlBar } from './ControlBar';

const noop = () => undefined;

function setWidth(width: number) {
  Object.defineProperty(window, 'innerWidth', { value: width, configurable: true });
}

type Props = Partial<Parameters<typeof ControlBar>[0]>;

function renderBar(props: Props = {}) {
  const onTogglePanel = vi.fn();
  const onToggleConsent = vi.fn();
  const onPick = vi.fn();
  const view = render(
    <ControlBar
      isOrganizer
      analysisEnabled
      micOn
      cameraOn
      consent="granted"
      panel={null}
      onToggleMic={noop}
      onToggleCamera={noop}
      onToggleConsent={onToggleConsent}
      onTogglePanel={onTogglePanel}
      onLeave={noop}
      onEnd={noop}
      devicesPanel={<p>Список устройств</p>}
      reactions={{ onPick, blockedUntil: 0, tooFrequent: false }}
      {...props}
    />,
  );
  return { ...view, onTogglePanel, onToggleConsent, onPick };
}

const MAIN = ['Микрофон', 'Камера', 'Реакции', 'Чат', 'Выйти', 'Завершить встречу'];

afterEach(() => setWidth(1024));

describe('нижняя панель: главные кнопки всегда на виду', () => {
  it.each([360, 768, 960, 1024, 1280, 1920])(
    '%i px: микрофон, камера, реакции, чат, выход и завершение в строке, прокрутки нет',
    (width) => {
      setWidth(width);
      renderBar();
      for (const name of MAIN) expect(screen.getByRole('button', { name })).toBeVisible();
      const footer = screen.getByRole('contentinfo', { name: 'Управление встречей' });
      expect(footer.className).not.toMatch(/overflow-x-auto|overflow-auto|overflow-scroll/);
      expect(footer.querySelector('[class*="overflow-x"]')).toBeNull();
    },
  );

  it('гость: «Выйти» есть, «Завершить встречу» нет', () => {
    renderBar({ isOrganizer: false, onEnd: undefined });
    expect(screen.getByRole('button', { name: 'Выйти' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Завершить встречу' })).not.toBeInTheDocument();
  });

  it('бейдж непрочитанных остается на кнопке «Чат», даже когда остальное в «Ещё»', () => {
    setWidth(360);
    renderBar({ unreadChat: 12 });
    const chat = screen.getByRole('button', { name: 'Чат, непрочитанных: 12' });
    expect(chat).toHaveTextContent('9+');
  });
});

describe('«Ещё»: второстепенные кнопки, когда места не хватает', () => {
  it('1280 px: всё в строке, «Ещё» не нужно', () => {
    setWidth(1280);
    renderBar();
    for (const name of ['Устройства', 'Анализ моих эмоций', 'Участники', 'Эмоции']) {
      expect(screen.getByRole('button', { name })).toBeVisible();
    }
    expect(screen.queryByRole('button', { name: 'Ещё' })).not.toBeInTheDocument();
  });

  it('360 px: «Ещё» с aria-haspopup; пункты работают как исходные кнопки и закрывают меню', async () => {
    setWidth(360);
    const user = userEvent.setup();
    const { onTogglePanel, onToggleConsent } = renderBar();
    expect(screen.queryByRole('button', { name: 'Участники' })).not.toBeInTheDocument();
    const more = screen.getByRole('button', { name: 'Ещё' });
    expect(more).toHaveAttribute('aria-haspopup', 'true');

    await user.click(more);
    const menu = screen.getByRole('menu');
    await user.click(within(menu).getByRole('menuitem', { name: 'Участники' }));
    expect(onTogglePanel).toHaveBeenCalledWith('participants');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();

    await user.click(more);
    await user.click(screen.getByRole('menuitem', { name: /Анализ моих эмоций/ }));
    expect(onToggleConsent).toHaveBeenCalledTimes(1);

    await user.click(more);
    await user.click(screen.getByRole('menuitem', { name: 'Эмоции' }));
    expect(onTogglePanel).toHaveBeenLastCalledWith('emotions');
  });

  it('пункт «Устройства» открывает панель устройств, а «Ещё» закрывается', async () => {
    setWidth(360);
    const user = userEvent.setup();
    renderBar();
    await user.click(screen.getByRole('button', { name: 'Ещё' }));
    await user.click(screen.getByRole('menuitem', { name: 'Устройства' }));
    expect(screen.getByRole('group', { name: 'Выбор устройств' })).toHaveTextContent(
      'Список устройств',
    );
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('Esc и клик вне закрывают меню; Esc возвращает фокус на «Ещё»', async () => {
    setWidth(360);
    const user = userEvent.setup();
    renderBar();
    const more = screen.getByRole('button', { name: 'Ещё' });
    await user.click(more);
    expect(screen.getByRole('menu')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(more).toHaveFocus();

    await user.click(more);
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });
});

describe('всплывающие панели: открыта только одна', () => {
  it('«Реакции», «Устройства» и «Ещё» закрывают друг друга; боковые панели от них не зависят', async () => {
    setWidth(960);
    const user = userEvent.setup();
    const { rerender } = renderBar();
    const popups = () =>
      ['Выбор реакции', 'Выбор устройств', 'Ещё'].filter((name) =>
        screen.queryByRole('group', { name }),
      ).length;

    await user.click(screen.getByRole('button', { name: 'Реакции' }));
    expect(screen.getByRole('group', { name: 'Выбор реакции' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Устройства' }));
    expect(screen.queryByRole('group', { name: 'Выбор реакции' })).not.toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Выбор устройств' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Ещё' }));
    expect(popups()).toBe(1);
    expect(screen.getByRole('group', { name: 'Ещё' })).toBeInTheDocument();

    // боковая панель открыта – всплывающие работают независимо
    rerender(
      <ControlBar
        isOrganizer
        analysisEnabled
        micOn
        cameraOn
        consent="granted"
        panel="chat"
        onToggleMic={noop}
        onToggleCamera={noop}
        onToggleConsent={noop}
        onTogglePanel={noop}
        onLeave={noop}
        onEnd={noop}
        devicesPanel={<p>Список устройств</p>}
        reactions={{ onPick: noop, blockedUntil: 0, tooFrequent: false }}
      />,
    );
    expect(screen.getByRole('button', { name: 'Чат' })).toHaveAttribute('aria-pressed', 'true');
    expect(popups()).toBe(1);
  });

  it('Esc и клик вне закрывают «Реакции» и «Устройства»', async () => {
    setWidth(1280);
    const user = userEvent.setup();
    renderBar();
    await user.click(screen.getByRole('button', { name: 'Устройства' }));
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('group', { name: 'Выбор устройств' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Устройства' })).toHaveFocus();

    await user.click(screen.getByRole('button', { name: 'Реакции' }));
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole('group', { name: 'Выбор реакции' })).not.toBeInTheDocument();
  });

  it('«Реакции» закрывается сразу после выбора реакции', async () => {
    const user = userEvent.setup();
    const { onPick } = renderBar();
    await user.click(screen.getByRole('button', { name: 'Реакции' }));
    await user.click(screen.getByRole('button', { name: 'Реакция: праздник' }));
    expect(onPick).toHaveBeenCalledWith('🎉');
    expect(screen.queryByRole('group', { name: 'Выбор реакции' })).not.toBeInTheDocument();
  });

  it('панели вынесены из потока (fixed): прокрутка и обрезание строки им не мешают', async () => {
    const user = userEvent.setup();
    renderBar();
    await user.click(screen.getByRole('button', { name: 'Устройства' }));
    expect(screen.getByRole('group', { name: 'Выбор устройств' })).toHaveClass(
      'fixed',
      'left-1/2',
      '-translate-x-1/2',
      'bottom-20',
    );
  });
});

describe('ожидание реакций: подпись на кнопке «Реакции»', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date('2026-10-29T10:00:00Z'));
  });
  afterEach(() => vi.useRealTimers());

  it('обычный лимит: «Подождите N с» без слова «часто», кнопка aria-disabled, N убывает', () => {
    const { onPick } = renderBar({
      reactions: { onPick: vi.fn(), blockedUntil: Date.now() + 3000, tooFrequent: false },
    });
    expect(onPick).not.toHaveBeenCalled();
    const button = screen.getByRole('button', { name: 'Реакции. Подождите 3 с' });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(button).toHaveAttribute('title', 'Подождите 3 с');
    expect(button).toHaveTextContent('3 с');
    expect(button.getAttribute('aria-label')).not.toMatch(/часто/);

    act(() => void vi.advanceTimersByTime(1100));
    expect(screen.getByRole('button', { name: 'Реакции. Подождите 2 с' })).toBeInTheDocument();
    act(() => void vi.advanceTimersByTime(2000));
    expect(screen.getByRole('button', { name: 'Реакции' })).not.toHaveAttribute('aria-disabled');
  });

  it('исчерпан лимит 5 за 10 секунд: «Слишком часто. Подождите N с», не больше 10 с', () => {
    renderBar({
      reactions: { onPick: vi.fn(), blockedUntil: Date.now() + 60_000, tooFrequent: true },
    });
    const button = screen.getByRole('button', { name: 'Реакции. Слишком часто. Подождите 10 с' });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    // полный текст озвучивается в области aria-live
    const live = document.querySelector('[aria-live="polite"]');
    expect(live).toHaveTextContent('Слишком часто. Подождите 10 с');
  });

  it('неактивная кнопка не открывает панель', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderBar({
      reactions: { onPick: vi.fn(), blockedUntil: Date.now() + 3000, tooFrequent: false },
    });
    await user.click(screen.getByRole('button', { name: /^Реакции/ }));
    expect(screen.queryByRole('group', { name: 'Выбор реакции' })).not.toBeInTheDocument();
  });
});
