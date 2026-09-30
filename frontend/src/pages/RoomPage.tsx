import { MessageSquare, Mic, PhoneOff, Video } from 'lucide-react';
import { useParams } from 'react-router';

import { EMOTION_LABELS, EMOTION_META } from '@/shared/config/emotions';
import { Badge } from '@/shared/ui/badge';
import { Button } from '@/shared/ui/button';

const PLACEHOLDER_TILES = ['Вы', 'Участник 2', 'Участник 3', 'Участник 4'];

/**
 * UC-4. Комната организатора: галерея видео, панель эмоций, управление.
 * Сейчас – макет раскладки. Видео на @livekit/components-react – EMO-57 (прототип), спринт 4;
 * панель эмоций – спринт 5.
 */
export default function RoomPage() {
  const { meetingId = '' } = useParams();

  return (
    <div className="flex h-dvh flex-col bg-room text-room-foreground">
      <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-room-border px-4">
        <p className="truncate text-sm font-medium">Встреча {meetingId}</p>
        {/* Виден всем, пока в комнате есть ML-агент (vks.kind = agent) */}
        <Badge variant="signal">
          <span className="size-1.5 rounded-full bg-signal-foreground" aria-hidden />
          Идет анализ эмоций
        </Badge>
      </header>

      <div className="flex min-h-0 flex-1">
        <section
          aria-label="Участники"
          className="grid flex-1 auto-rows-fr gap-3 p-4 sm:grid-cols-2"
        >
          {PLACEHOLDER_TILES.map((name) => (
            <div
              key={name}
              className="relative flex items-center justify-center rounded-lg border border-room-border bg-room-surface"
            >
              <span className="size-16 rounded-full bg-room-border" aria-hidden />
              <span className="absolute bottom-2 left-2 rounded bg-room/80 px-2 py-0.5 text-xs">
                {name}
              </span>
            </div>
          ))}
        </section>

        <aside
          aria-label="Панель эмоций"
          className="hidden w-80 shrink-0 flex-col gap-4 overflow-y-auto border-l border-room-border p-4 lg:flex"
        >
          <h2 className="text-sm font-semibold">Панель эмоций</h2>
          <ul className="flex flex-col gap-2 text-sm">
            {EMOTION_LABELS.map((e) => (
              <li key={e} className="flex items-center gap-2">
                <span
                  className="size-3 rounded-sm"
                  style={{ background: `var(${EMOTION_META[e].cssVar})` }}
                  aria-hidden
                />
                {EMOTION_META[e].title}
              </li>
            ))}
          </ul>
          <p className="mt-auto text-xs leading-relaxed text-room-muted">
            Результаты носят вероятностный характер и не являются оценкой личности.
          </p>
        </aside>
      </div>

      <footer className="flex h-16 shrink-0 items-center justify-center gap-2 border-t border-room-border">
        <Button variant="room" size="icon" aria-label="Микрофон">
          <Mic />
        </Button>
        <Button variant="room" size="icon" aria-label="Камера">
          <Video />
        </Button>
        <Button variant="room" size="icon" aria-label="Чат">
          <MessageSquare />
        </Button>
        <Button variant="destructive" className="ml-4">
          <PhoneOff aria-hidden />
          Завершить
        </Button>
      </footer>
    </div>
  );
}
