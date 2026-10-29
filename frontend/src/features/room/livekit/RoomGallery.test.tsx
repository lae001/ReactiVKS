import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';

import type * as LiveKitReact from '@livekit/components-react';

import { RoomGallery } from './RoomGallery';

type FakeTrack = { participant: { identity: string; attributes: Record<string, string> } };
const fake = vi.hoisted(() => ({ list: [] as unknown[] }));

vi.mock('@livekit/components-react', async (importOriginal) => {
  const actual = await importOriginal<typeof LiveKitReact>();
  return {
    ...actual,
    useTracks: () => fake.list,
    GridLayout: ({ tracks, children }: { tracks: FakeTrack[]; children: ReactNode }) => (
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
  };
});

const track = (identity: string, attributes: Record<string, string> = {}): FakeTrack => ({
  participant: { identity, attributes },
});

describe('галерея комнаты', () => {
  it('агент (vks.kind = agent) исключен из плиток и из счетчика', () => {
    fake.list = [
      track('p_1', { 'vks.kind': 'human' }),
      track('emotion-agent', { 'vks.kind': 'agent' }),
      track('p_2'),
    ];
    render(<RoomGallery />);
    expect(screen.getAllByTestId('tile').map((el) => el.textContent)).toEqual(['p_1', 'p_2']);
    expect(screen.getByTestId('lk-gallery')).toHaveAttribute('data-tiles', '2');
  });

  it('10 участников – одна страница без навигации', () => {
    fake.list = Array.from({ length: 10 }, (_, i) => track(`p_${i}`));
    render(<RoomGallery />);
    expect(screen.getAllByTestId('tile')).toHaveLength(10);
    expect(screen.queryByRole('navigation', { name: 'Страницы галереи' })).toBeNull();
  });

  it('больше 12 плиток – пагинация (на случай роста лимита комнаты)', () => {
    fake.list = Array.from({ length: 13 }, (_, i) => track(`p_${i}`));
    render(<RoomGallery />);
    expect(screen.getByText('Страница 1 из 2')).toBeInTheDocument();
  });
});
