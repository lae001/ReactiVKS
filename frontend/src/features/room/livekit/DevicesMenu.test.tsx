import { render, screen } from '@testing-library/react';

import { DevicesPanel } from './DevicesMenu';

vi.mock('@livekit/components-react', () => ({
  useMediaDeviceSelect: ({ kind }: { kind: string }) => ({
    devices: kind === 'videoinput' ? [] : [{ deviceId: 'a', label: 'MacBook Air Microphone' }],
    activeDeviceId: 'a',
    setActiveMediaDevice: vi.fn(),
  }),
}));

describe('панель «Устройства»: тёмная тема комнаты', () => {
  it('списки микрофона, камеры и динамика – светлый текст на тёмном фоне, в том числе пустой и отключённый', () => {
    render(<DevicesPanel />);
    const selects = screen.getAllByRole('combobox');
    expect(selects.length).toBeGreaterThanOrEqual(2);
    for (const select of selects) {
      // светлый #e8eef1 на тёмном #121a20 (≈15:1); отключённый – #93a4b0 (≈6,7:1), оба не ниже 4,5:1
      expect(select).toHaveClass(
        'bg-room',
        'text-room-foreground',
        'border-room-border',
        'scheme-dark',
      );
      expect(select).not.toHaveClass('bg-card');
    }
    const empty = screen.getByRole('combobox', { name: 'Камера' });
    expect(empty).toBeDisabled();
    expect(empty).toHaveClass('disabled:text-room-muted', 'disabled:opacity-100');
    for (const option of screen.getAllByRole('option')) {
      expect(option).toHaveClass('bg-room-surface', 'text-room-foreground');
    }
    expect(screen.getByText('Камера не найдена')).toBeInTheDocument();
    // подписи полей тоже светлые
    expect(screen.getByText('Микрофон')).toHaveClass('text-room-foreground');
  });
});
