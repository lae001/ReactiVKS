import { GridLayout, ParticipantTile, useTracks, usePagination } from '@livekit/components-react';
import { Track } from 'livekit-client';

import { PagerNav } from '../PagerNav';
import { TILES_PER_PAGE } from '../LiveKitGallery';

import { isAgent } from './participants';

/**
 * Галерея комнаты: `GridLayout` по дорожкам камер и демонстрации экрана, пагинация сверх
 * `TILES_PER_PAGE`. Плитка человека без камеры остается (заглушка с инициалами). ML-агент
 * (`vks.kind = agent`) в плитки не попадает. Должна находиться внутри `<LiveKitRoom>`.
 */
export function RoomGallery() {
  const all = useTracks([
    { source: Track.Source.Camera, withPlaceholder: true },
    { source: Track.Source.ScreenShare, withPlaceholder: false },
  ]);
  const tracks = all.filter((t) => !isAgent(t.participant));
  const pagination = usePagination(TILES_PER_PAGE, tracks);

  return (
    <section
      aria-label="Галерея участников"
      className="flex min-h-0 flex-1 flex-col"
      data-lk-theme="default"
    >
      <div className="min-h-0 flex-1 p-2" data-testid="lk-gallery" data-tiles={tracks.length}>
        <GridLayout tracks={pagination.tracks} style={{ height: '100%' }}>
          <ParticipantTile />
        </GridLayout>
      </div>
      <PagerNav
        currentPage={pagination.currentPage}
        totalPageCount={pagination.totalPageCount}
        onPrev={pagination.prevPage}
        onNext={pagination.nextPage}
      />
    </section>
  );
}
