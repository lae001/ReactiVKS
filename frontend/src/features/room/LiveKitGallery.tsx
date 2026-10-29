import {
  ConnectionStateToast,
  ControlBar,
  GridLayout,
  ParticipantTile,
  RoomAudioRenderer,
  useConnectionState,
  usePagination,
  useTracks,
} from '@livekit/components-react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Track } from 'livekit-client';

import { Button } from '@/shared/ui/button';

/**
 * Плиток на странице: остальные участники уходят на следующие страницы. Лимит комнаты по уставу – 10 человек,
 * 12 взято с запасом, а пагинация оставлена на случай роста лимита.
 */
export const TILES_PER_PAGE = 12;

/**
 * Галерея участников комнаты LiveKit (EMO-53). Число плиток не задано: сетку строит `GridLayout`
 * по списку дорожек, при превышении `TILES_PER_PAGE` включается пагинация.
 * Должна находиться внутри `<LiveKitRoom>`.
 */
export function LiveKitGallery() {
  const connectionState = useConnectionState();
  // Плитка участника без камеры остается (placeholder): его видно в списке и без видео.
  const tracks = useTracks([
    { source: Track.Source.Camera, withPlaceholder: true },
    { source: Track.Source.ScreenShare, withPlaceholder: false },
  ]);
  const pagination = usePagination(TILES_PER_PAGE, tracks);
  const multiPage = pagination.totalPageCount > 1;

  return (
    <div className="flex h-full flex-col bg-room text-room-foreground" data-lk-theme="default">
      <p className="sr-only" role="status" data-testid="lk-state" data-state={connectionState}>
        Соединение: {connectionState}
      </p>
      <div className="min-h-0 flex-1 p-2" data-testid="lk-gallery" data-tiles={tracks.length}>
        <GridLayout tracks={pagination.tracks} style={{ height: '100%' }}>
          <ParticipantTile />
        </GridLayout>
      </div>
      {multiPage && (
        <nav aria-label="Страницы галереи" className="flex items-center justify-center gap-3 py-2">
          <Button
            type="button"
            variant="outline"
            size="icon"
            aria-label="Предыдущая страница"
            onClick={pagination.prevPage}
            disabled={pagination.currentPage <= 1}
          >
            <ChevronLeft />
          </Button>
          <span className="text-sm tabular-nums" aria-live="polite">
            Страница {pagination.currentPage} из {pagination.totalPageCount}
          </span>
          <Button
            type="button"
            variant="outline"
            size="icon"
            aria-label="Следующая страница"
            onClick={pagination.nextPage}
            disabled={pagination.currentPage >= pagination.totalPageCount}
          >
            <ChevronRight />
          </Button>
        </nav>
      )}
      <ControlBar controls={{ chat: false, screenShare: false }} />
      <RoomAudioRenderer />
      <ConnectionStateToast />
    </div>
  );
}
