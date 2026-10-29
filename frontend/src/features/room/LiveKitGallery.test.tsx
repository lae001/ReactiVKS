import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';

import type * as LiveKitReact from '@livekit/components-react';

import { LiveKitGallery, TILES_PER_PAGE } from './LiveKitGallery';

// Подменённые дорожки: браузер, сервер LiveKit и контекст комнаты не нужны.
const fakeTracks = vi.hoisted(() => ({ list: [] as { participant: { identity: string } }[] }));

vi.mock('@livekit/components-react', async (importOriginal) => {
  const actual = await importOriginal<typeof LiveKitReact>();
  return {
    ...actual,
    useConnectionState: () => 'connected',
    useTracks: () => fakeTracks.list,
    GridLayout: ({
      tracks,
      children,
    }: {
      tracks: { participant: { identity: string } }[];
      children: ReactNode;
    }) => (
      <ul>
        {tracks.map((t) => (
          <li key={t.participant.identity} data-testid="tile">
            {t.participant.identity}
            {children}
          </li>
        ))}
      </ul>
    ),
    ParticipantTile: () => null,
    ControlBar: () => null,
    RoomAudioRenderer: () => null,
    ConnectionStateToast: () => null,
  };
});

function setParticipants(count: number) {
  fakeTracks.list = Array.from({ length: count }, (_, i) => ({
    participant: { identity: `user-${i + 1}` },
  }));
}

const tileNames = () => screen.getAllByTestId('tile').map((el) => el.textContent);

describe('LiveKitGallery: пагинация', () => {
  it('до лимита страницы пагинации нет', () => {
    setParticipants(TILES_PER_PAGE);
    render(<LiveKitGallery />);
    expect(screen.getAllByTestId('tile')).toHaveLength(TILES_PER_PAGE);
    expect(screen.queryByRole('navigation', { name: 'Страницы галереи' })).toBeNull();
  });

  it('13 участников делятся на две страницы: 12 и 1', async () => {
    setParticipants(13);
    const user = userEvent.setup();
    render(<LiveKitGallery />);

    expect(screen.getByText('Страница 1 из 2')).toBeInTheDocument();
    expect(screen.getAllByTestId('tile')).toHaveLength(12);
    expect(screen.getByTestId('lk-gallery')).toHaveAttribute('data-tiles', '13');
    expect(screen.getByRole('button', { name: 'Предыдущая страница' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Следующая страница' }));

    expect(screen.getByText('Страница 2 из 2')).toBeInTheDocument();
    expect(tileNames()).toEqual(['user-13']);
    expect(screen.getByRole('button', { name: 'Следующая страница' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Предыдущая страница' }));
    expect(screen.getByText('Страница 1 из 2')).toBeInTheDocument();
    expect(tileNames()[0]).toBe('user-1');
  });

  it('25 участников дают три страницы', () => {
    setParticipants(25);
    render(<LiveKitGallery />);
    expect(screen.getByText('Страница 1 из 3')).toBeInTheDocument();
  });
});
