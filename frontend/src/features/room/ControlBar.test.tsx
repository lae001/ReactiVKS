import { render, screen, within } from '@testing-library/react';

import { ControlBar } from './ControlBar';

const noop = () => undefined;

function renderBar(props: Partial<Parameters<typeof ControlBar>[0]> = {}) {
  return render(
    <ControlBar
      isOrganizer
      analysisEnabled
      micOn
      cameraOn
      consent="granted"
      panel={null}
      onToggleMic={noop}
      onToggleCamera={noop}
      onToggleConsent={noop}
      onTogglePanel={noop}
      onLeave={noop}
      onEnd={noop}
      {...props}
    />,
  );
}

describe('нижняя панель: «Завершить встречу» и «Выйти» на любой ширине', () => {
  it('организатор: обе кнопки вне прокручиваемой группы – при узком окне прокрутка их не скрывает', () => {
    renderBar();
    const scroll = screen.getByTestId('controls-scroll');
    for (const name of ['Выйти', 'Завершить встречу']) {
      const button = screen.getByRole('button', { name });
      expect(button).toBeVisible();
      expect(scroll).not.toContainElement(button);
      // на 360 px подпись скрыта, но доступное имя остается
      expect(button.querySelector('span')).toHaveClass('sr-only');
    }
    // остальное (микрофон, панели) прокручивается внутри группы
    expect(within(scroll).getByRole('button', { name: 'Микрофон' })).toBeVisible();
    expect(within(scroll).getByRole('button', { name: 'Чат' })).toBeVisible();
  });

  it('кнопки не сжимаются и не растягиваются: shrink-0 и фиксированная высота', () => {
    renderBar();
    for (const name of ['Выйти', 'Завершить встречу']) {
      expect(screen.getByRole('button', { name })).toHaveClass('shrink-0', 'h-12');
    }
  });

  it('гость: только «Выйти»', () => {
    renderBar({ isOrganizer: false, onEnd: undefined });
    expect(screen.getByRole('button', { name: 'Выйти' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Завершить встречу' })).not.toBeInTheDocument();
  });
});
