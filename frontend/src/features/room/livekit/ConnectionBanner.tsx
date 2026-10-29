import { useConnectionState } from '@livekit/components-react';

import { connectionNotice } from './notice';

/** Полоса над галереей: подключение и переподключение. Обрыв без восстановления – отдельный экран. */
export function ConnectionBanner() {
  const state = useConnectionState();
  const text = connectionNotice(state);
  return (
    <div data-testid="lk-state" data-state={state}>
      {text && (
        <p role="status" className="bg-room-surface px-4 py-2 text-center text-sm text-signal">
          {text}
        </p>
      )}
    </div>
  );
}
