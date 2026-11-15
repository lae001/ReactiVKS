import { createContext, useContext } from 'react';
import type { SnapshotParticipant } from '@/shared/api/types';
import { EmotionIndicator } from '@/features/emotions/EmotionIndicator';
import {
  GridLayout,
  ParticipantTile,
  useTracks,
  usePagination,
  useTrackRefContext,
} from '@livekit/components-react';
import { Track } from 'livekit-client';

import { PagerNav } from '../PagerNav';
import { TILES_PER_PAGE } from '../LiveKitGallery';

import { isService } from './participants';

/**
 * Галерея комнаты: `GridLayout` по дорожкам камер и демонстрации экрана, пагинация сверх
 * `TILES_PER_PAGE`. Плитка человека без камеры остается (заглушка с инициалами). ML-агент
 * (`vks.kind = agent`) в плитки не попадает. Должна находиться внутри `<LiveKitRoom>`.
 */
const EmotionsContext = createContext<SnapshotParticipant[]>([]);
export function RoomGallery({ emotions = [] }: { emotions?: SnapshotParticipant[] }) {
  const all = useTracks([
    { source: Track.Source.Camera, withPlaceholder: true },
    { source: Track.Source.ScreenShare, withPlaceholder: false },
  ]);
  const tracks = all.filter((t) => !isService(t.participant));
  const pagination = usePagination(TILES_PER_PAGE, tracks);

  return (
    <section
      aria-label="Галерея участников"
      className="flex min-h-0 flex-1 flex-col"
      data-lk-theme="default"
    >
      {/* Размер области задает только раскладка страницы: GridLayout лежит внутри абсолютно, и
          высота видео не влияет на высоту галереи (иначе панель управления «плывет» при двух видео) */}
      <div className="relative min-h-0 flex-1" data-testid="lk-gallery" data-tiles={tracks.length}>
        <div className="absolute inset-2">
          <EmotionsContext.Provider value={emotions}>
            <GridLayout tracks={pagination.tracks} style={{ height: '100%' }}>
              <IdentifiedTile />
            </GridLayout>
          </EmotionsContext.Provider>
        </div>
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

function IdentifiedTile() {
  const track = useTrackRefContext();
  const emotions = useContext(EmotionsContext);
  const emotion = emotions.find((p) => `p_${p.participant_id}` === track.participant.identity);
  return (
    <div className="relative min-h-0 min-w-0 overflow-hidden">
      <ParticipantTile
        style={{ height: '100%', width: '100%' }}
        data-participant-identity={track.participant.identity}
      />
      {emotion && (
        <div className="absolute top-2 left-2">
          <EmotionIndicator data={emotion} />
        </div>
      )}
    </div>
  );
}
