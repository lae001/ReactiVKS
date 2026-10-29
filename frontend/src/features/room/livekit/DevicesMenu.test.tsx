import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { DevicesMenu } from './DevicesMenu';

vi.mock('@livekit/components-react', () => ({
  useMediaDeviceSelect: () => ({
    devices: [{ deviceId: 'a', label: 'Камера 1' }],
    activeDeviceId: 'a',
    setActiveMediaDevice: vi.fn(),
  }),
}));

describe('меню «Устройства»', () => {
  it('панель выведена из потока (fixed) и по центру окна: прокручиваемая нижняя панель ее не обрезает', async () => {
    render(
      // как в нижней панели: родитель прокручивается по горизонтали
      <div style={{ overflowX: 'auto' }}>
        <DevicesMenu />
      </div>,
    );
    await userEvent.setup().click(screen.getByRole('button', { name: 'Устройства' }));
    const panel = screen.getByRole('group', { name: 'Выбор устройств' });
    expect(panel).toHaveClass('fixed', 'left-1/2', '-translate-x-1/2', 'bottom-20');
    // не шире окна даже на самом узком экране
    expect(panel.className).toContain('max-w-[calc(100vw-1rem)]');
    expect(panel).not.toHaveClass('absolute');
  });
});
