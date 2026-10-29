import { Link } from 'react-router';

import { Button } from '@/shared/ui/button';

import { exitLink } from './livekit/exit-link';

/** «Отмена» на загрузочных экранах комнаты: организатору к списку встреч, гостю и неизвестной роли – на «/». */
export function CancelLink({ role }: { role?: 'organizer' | 'guest' }) {
  return (
    <Button asChild variant="room">
      <Link to={exitLink({ role: role ?? 'guest' }).to}>Отмена</Link>
    </Button>
  );
}
