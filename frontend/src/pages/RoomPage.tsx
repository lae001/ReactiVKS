import { X } from 'lucide-react';
import { type ReactNode, useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router';

import { EmotionIndicator } from '@/features/emotions/EmotionIndicator';
import { EmotionPanel } from '@/features/emotions/EmotionPanel';
import { type ChatMessage, ChatPanel } from '@/features/room/ChatPanel';
import { ControlBar } from '@/features/room/ControlBar';
import { ParticipantsPanel } from '@/features/room/ParticipantsPanel';
import type { RoomParticipant, SidePanelTab } from '@/features/room/types';
import { VideoTile } from '@/features/room/VideoTile';
import type { ConsentState, Meeting, SnapshotParticipant } from '@/shared/api/types';
import { paths } from '@/shared/config/routes';
import { useLocalMedia } from '@/shared/hooks/use-local-media';
import { formatDuration } from '@/shared/lib/format';
import { readRoomEntry, type RoomEntry } from '@/shared/lib/room-entry';
import { cn } from '@/shared/lib/utils';
import {
  getRoomMeeting,
  MOCK_CHAT,
  MOCK_EMOTION_SNAPSHOT,
  MOCK_ORGANIZER_NAME,
  MOCK_ROOM_PARTICIPANTS,
} from '@/shared/mocks/data';
import { Badge } from '@/shared/ui/badge';
import { Button } from '@/shared/ui/button';
import { CopyLinkButton } from '@/shared/ui/copy-link-button';

const TAB_TITLE: Record<SidePanelTab, string> = {
  participants: 'Участники',
  emotions: 'Эмоции',
  chat: 'Чат',
};

/** Раскладка галереи по числу плиток (до 10 участников). */
function galleryCols(n: number): string {
  if (n <= 1) return 'grid-cols-1';
  if (n === 2) return 'grid-cols-1 sm:grid-cols-2';
  if (n <= 4) return 'grid-cols-2';
  if (n <= 6) return 'grid-cols-2 lg:grid-cols-3';
  return 'grid-cols-2 md:grid-cols-3 xl:grid-cols-4';
}

function isWide(): boolean {
  return (
    typeof window.matchMedia === 'function' && window.matchMedia('(min-width: 1024px)').matches
  );
}

function useElapsed(): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);
  return seconds;
}

function RoomMessage({ title, text, action }: { title: string; text: string; action: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-start justify-center gap-4 bg-room px-6 text-room-foreground md:px-16">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="max-w-md text-room-muted">{text}</p>
      {action}
    </div>
  );
}

/**
 * UC-4. Комната встречи (docs/frontend/site-structure.md, 4.3): галерея, боковая панель
 * «Участники / Эмоции / Чат», нижняя панель управления. Состав зависит от роли.
 * Сейчас – на тестовых данных; видео на LiveKit – EMO-75, панель эмоций по WebSocket – EMO-90, EMO-91.
 */
export default function RoomPage() {
  const { meetingId = '' } = useParams();
  const location = useLocation();
  const meeting = getRoomMeeting(meetingId);
  const [left, setLeft] = useState(false);

  // Без state из лобби считаем, что вошел организатор (с главной или из карточки встречи).
  // Согласие организатора по умолчанию не дано – анализ только после явного включения.
  const entry: RoomEntry = readRoomEntry(location.state) ?? {
    role: 'organizer',
    displayName: MOCK_ORGANIZER_NAME,
    consent: meeting.analysis_enabled ? 'denied' : 'not_required',
    cameraOn: true,
    micOn: true,
  };

  if (meeting.status === 'ended' || meeting.status === 'cancelled') {
    return (
      <RoomMessage
        title="Встреча завершена"
        text={`Встреча «${meeting.title}» уже закончилась.`}
        action={
          <Button asChild variant="room">
            <Link to={paths.meeting(meeting.id)}>К карточке встречи</Link>
          </Button>
        }
      />
    );
  }

  if (left) {
    return (
      <RoomMessage
        title="Вы вышли из встречи"
        text="Камера и микрофон выключены. Если вышли случайно, вернитесь по ссылке-приглашению."
        action={
          <Button asChild variant="room">
            <Link to={paths.join(entry.inviteCode ?? meeting.invite_code)}>
              Вернуться во встречу
            </Link>
          </Button>
        }
      />
    );
  }

  return <Room meeting={meeting} entry={entry} onLeave={() => setLeft(true)} />;
}

function Room({
  meeting,
  entry,
  onLeave,
}: {
  meeting: Meeting;
  entry: RoomEntry;
  onLeave: () => void;
}) {
  const navigate = useNavigate();
  const isOrganizer = entry.role === 'organizer';
  const elapsed = useElapsed();
  const media = useLocalMedia({ initialCamera: entry.cameraOn, initialMic: entry.micOn });

  const [myConsent, setMyConsent] = useState<ConsentState>(entry.consent);
  const [others, setOthers] = useState(() =>
    MOCK_ROOM_PARTICIPANTS.map((p) => ({ ...p, micOn: true })),
  );
  const [messages, setMessages] = useState<ChatMessage[]>(MOCK_CHAT);
  const [panel, setPanel] = useState<SidePanelTab | null>(() =>
    isOrganizer && meeting.analysis_enabled && isWide() ? 'emotions' : null,
  );
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [announcement, setAnnouncement] = useState('');

  const self: RoomParticipant = {
    id: 'self',
    name: entry.displayName,
    role: entry.role,
    isSelf: true,
    consent: myConsent,
    micOn: media.micOn,
    cameraOn: media.cameraOn,
  };
  const participants: RoomParticipant[] = [
    self,
    ...others.map((p) => ({
      id: p.id,
      name: p.display_name,
      role: p.role,
      isSelf: false,
      consent: meeting.analysis_enabled ? p.consent_state : 'not_required',
      micOn: p.micOn,
      cameraOn: true,
    })),
  ];

  // Панель эмоций видит только организатор; участник без согласия – «без анализа»
  const emotions: SnapshotParticipant[] = participants
    .filter((p) => !p.isSelf)
    .map((p): SnapshotParticipant => {
      const snap = MOCK_EMOTION_SNAPSHOT[p.id];
      return snap && p.consent === 'granted'
        ? snap
        : {
            participant_id: p.id,
            display_name: p.name,
            role: p.role,
            state: 'no_consent',
            last: null,
          };
    });
  const emotionsById = new Map(emotions.map((e) => [e.participant_id, e]));

  function toggleConsent() {
    // PUT /participants/me/consent {decision: granted | revoked} – EMO-89
    const next: ConsentState = myConsent === 'granted' ? 'revoked' : 'granted';
    setMyConsent(next);
    setAnnouncement(
      next === 'granted'
        ? 'Анализ ваших эмоций включен.'
        : 'Анализ ваших эмоций отключен. Уже накопленные данные остаются в отчете организатора.',
    );
  }

  function togglePanel(tab: SidePanelTab) {
    setPanel((current) => (current === tab ? null : tab));
  }

  function leave() {
    if (isOrganizer) setConfirmEnd(true);
    else onLeave();
  }

  return (
    <div className="flex h-dvh flex-col bg-room text-room-foreground">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-room-border px-4">
        <div className="flex min-w-0 flex-1 items-baseline gap-3">
          <h1 className="truncate text-sm font-medium">{meeting.title}</h1>
          <span className="text-sm text-room-muted" aria-label="Длительность встречи">
            {formatDuration(elapsed)}
          </span>
        </div>
        {/* Виден всем, пока в комнате есть ML-агент (vks.kind = agent) */}
        {meeting.analysis_enabled && (
          <Badge variant="signal">
            <span className="size-1.5 rounded-full bg-signal-foreground" aria-hidden />
            Идет анализ эмоций
          </Badge>
        )}
        {isOrganizer && (
          <span className="hidden md:block">
            <CopyLinkButton url={meeting.invite_url} variant="room" label="Пригласить" />
          </span>
        )}
      </header>

      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>

      <div className="relative flex min-h-0 flex-1">
        <section
          aria-label="Галерея участников"
          className={cn(
            'grid flex-1 auto-rows-fr gap-2 overflow-y-auto p-2 sm:gap-3 sm:p-4',
            galleryCols(participants.length),
          )}
        >
          {participants.map((p) => {
            const data = emotionsById.get(p.id);
            return (
              <VideoTile
                key={p.id}
                participant={p}
                stream={p.isSelf ? media.stream : null}
                overlay={
                  isOrganizer && meeting.analysis_enabled && data ? (
                    <EmotionIndicator data={data} />
                  ) : p.isSelf && meeting.analysis_enabled && myConsent !== 'granted' ? (
                    <span className="rounded-md bg-room/85 px-2 py-1 text-xs text-room-muted">
                      Ваши эмоции не анализируются
                    </span>
                  ) : null
                }
              />
            );
          })}
        </section>

        {panel && (
          <aside
            aria-label={TAB_TITLE[panel]}
            className="absolute inset-0 z-10 flex flex-col border-room-border bg-room sm:left-auto sm:w-96 sm:border-l lg:static lg:w-96"
          >
            <div className="flex h-12 shrink-0 items-center gap-1 border-b border-room-border px-2">
              <div role="tablist" aria-label="Боковая панель" className="flex flex-1 gap-1">
                {(Object.keys(TAB_TITLE) as SidePanelTab[])
                  .filter((t) => t !== 'emotions' || (isOrganizer && meeting.analysis_enabled))
                  .map((t) => (
                    <button
                      key={t}
                      type="button"
                      role="tab"
                      id={`tab-${t}`}
                      aria-selected={panel === t}
                      aria-controls="side-panel"
                      onClick={() => setPanel(t)}
                      className={cn(
                        'h-8 rounded-md px-3 text-sm text-room-muted transition-colors hover:text-room-foreground',
                        panel === t && 'bg-room-surface text-room-foreground',
                      )}
                    >
                      {TAB_TITLE[t]}
                      {t === 'participants' && ` · ${participants.length}`}
                    </button>
                  ))}
              </div>
              <Button
                variant="room"
                size="icon"
                className="size-8 bg-transparent"
                onClick={() => setPanel(null)}
                aria-label="Закрыть панель"
              >
                <X />
              </Button>
            </div>
            <div
              id="side-panel"
              role="tabpanel"
              aria-labelledby={`tab-${panel}`}
              className="min-h-0 flex-1 overflow-y-auto p-4"
            >
              {panel === 'participants' && (
                <ParticipantsPanel
                  participants={participants}
                  canModerate={isOrganizer}
                  onMute={(id) =>
                    setOthers((list) => list.map((p) => (p.id === id ? { ...p, micOn: false } : p)))
                  }
                  onRemove={(id) => setOthers((list) => list.filter((p) => p.id !== id))}
                />
              )}
              {panel === 'emotions' && <EmotionPanel participants={emotions} elapsed={elapsed} />}
              {panel === 'chat' && (
                <ChatPanel
                  messages={messages}
                  onSend={(text) =>
                    setMessages((list) => [
                      ...list,
                      {
                        id: `m${list.length + 1}`,
                        author: 'Вы',
                        text,
                        at: formatDuration(elapsed),
                      },
                    ])
                  }
                />
              )}
            </div>
          </aside>
        )}

        {confirmEnd && (
          <EndMeetingDialog
            onCancel={() => setConfirmEnd(false)}
            // POST /meetings/{id}/end – EMO-75; после завершения – карточка встречи с отчетом
            onConfirm={() => navigate(paths.meeting(meeting.id))}
          />
        )}
      </div>

      <ControlBar
        isOrganizer={isOrganizer}
        analysisEnabled={meeting.analysis_enabled}
        micOn={media.micOn}
        cameraOn={media.cameraOn}
        consent={myConsent}
        panel={panel}
        onToggleMic={media.toggleMic}
        onToggleCamera={media.toggleCamera}
        onToggleConsent={toggleConsent}
        onTogglePanel={togglePanel}
        onLeave={leave}
      />
    </div>
  );
}

function EndMeetingDialog({
  onCancel,
  onConfirm,
}: {
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const confirmRef = useRef<HTMLButtonElement>(null);
  useEffect(() => confirmRef.current?.focus(), []);

  return (
    <div
      className="absolute inset-0 z-20 flex items-center justify-center bg-room/70 p-4"
      onKeyDown={(e) => e.key === 'Escape' && onCancel()}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="end-title"
        aria-describedby="end-text"
        className="flex w-full max-w-sm flex-col gap-4 rounded-xl border border-room-border bg-room-surface p-5"
      >
        <h2 id="end-title" className="text-lg font-semibold">
          Завершить встречу для всех?
        </h2>
        <p id="end-text" className="text-sm text-room-muted">
          Все участники будут отключены. Итоги встречи появятся в ее карточке.
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="room" onClick={onCancel}>
            Отмена
          </Button>
          <Button ref={confirmRef} variant="destructive" onClick={onConfirm}>
            Завершить встречу
          </Button>
        </div>
      </div>
    </div>
  );
}
