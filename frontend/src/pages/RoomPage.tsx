import { X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router';

import { meetingErrorMessage } from '@/features/meetings/errors';
import { ApiError } from '@/shared/api/problem';

import { EmotionIndicator } from '@/features/emotions/EmotionIndicator';
import { EmotionPanel } from '@/features/emotions/EmotionPanel';
import { type ChatMessage, ChatPanel } from '@/features/room/ChatPanel';
import { ConfirmDialog } from '@/features/room/ConfirmDialog';
import { exitLink } from '@/features/room/livekit/exit-link';
import { RoomMessage } from '@/features/room/RoomMessage';
import { ControlBar } from '@/features/room/ControlBar';
import { ParticipantsPanel } from '@/features/room/ParticipantsPanel';
import type { RoomParticipant, SidePanelTab } from '@/features/room/types';
import { VideoTile } from '@/features/room/VideoTile';
import { LiveKitRoomPage } from '@/features/room/livekit/LiveKitRoomPage';
import { useMeeting, useParticipants } from '@/features/meetings/queries';
import { API_MODE, type Meeting, type Participant } from '@/shared/api/meetings';
import { useSessionStore } from '@/shared/api/session';
import type { ConsentState, SnapshotParticipant } from '@/shared/api/types';
import { paths } from '@/shared/config/routes';
import { useLocalMedia } from '@/shared/hooks/use-local-media';
import { formatDuration } from '@/shared/lib/format';
import { readRoomEntry, type RoomEntry } from '@/shared/lib/room-entry';
import { cn } from '@/shared/lib/utils';
// Панель эмоций и чат остаются на тестовых данных: realtime-сервис и чат на LiveKit – позже
import { MOCK_CHAT, MOCK_EMOTION_SNAPSHOT } from '@/shared/mocks/data';
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

/** Что комнате нужно знать о встрече: организатору приходит полная карточка, гостю – JoinResult.meeting. */
type RoomMeeting = Pick<Meeting, 'id' | 'title' | 'status' | 'analysis_enabled'> &
  Partial<Pick<Meeting, 'invite_url' | 'invite_code'>>;

/**
 * UC-4. Комната встречи (docs/frontend/site-structure.md, 4.3): галерея, боковая панель
 * «Участники / Эмоции / Чат», нижняя панель управления. Состав зависит от роли.
 * Встреча и участники – через слой API; видео на LiveKit – EMO-75, панель эмоций и чат остаются на
 * тестовых данных (WebSocket – EMO-90, EMO-91).
 */
export default function RoomPage() {
  const { meetingId = '' } = useParams();
  const location = useLocation();
  const [left, setLeft] = useState(false);
  const organizerName = useSessionStore((s) => s.user?.display_name);

  const fromLobby = readRoomEntry(location.state);
  // Гость получил сведения о встрече при входе (GET /meetings/{id} только для владельца);
  // организатор запрашивает карточку сам.
  const meetingQuery = useMeeting(meetingId, { enabled: !fromLobby?.meeting });
  // REST-список участников нужен только mock-комнате: в режиме http состав берется из LiveKit
  const participantsQuery = useParticipants(meetingId, API_MODE === 'mock');

  const meeting: RoomMeeting | undefined = fromLobby?.meeting ?? meetingQuery.data;
  if (!meeting) {
    if (meetingQuery.isError) {
      const notFound =
        meetingQuery.error instanceof ApiError && meetingQuery.error.code === 'not_found';
      return (
        <RoomMessage
          title={notFound ? 'Встреча не найдена' : 'Не удалось открыть комнату'}
          text={
            notFound
              ? 'Встреча не найдена или у вас нет к ней доступа.'
              : meetingErrorMessage(meetingQuery.error, 'открыть комнату')
          }
          action={
            <Button asChild variant="room">
              <Link to={paths.meetings}>К встречам</Link>
            </Button>
          }
        />
      );
    }
    return <RoomMessage title="Входим во встречу…" text="Подготавливаем комнату." action={null} />;
  }
  if (API_MODE === 'mock' && participantsQuery.isPending) {
    return <RoomMessage title="Входим во встречу…" text="Подготавливаем комнату." action={null} />;
  }

  // Без state из лобби считаем, что вошел организатор (с главной или из карточки встречи).
  // Согласие организатора по умолчанию не дано – анализ только после явного включения.
  const entry: RoomEntry = fromLobby ?? {
    role: 'organizer',
    displayName: organizerName ?? 'Организатор',
    consent: meeting.analysis_enabled ? 'denied' : 'not_required',
    cameraOn: true,
    micOn: true,
  };
  // Собеседники: гости, кроме самого вошедшего. Список обновляется вместе с LiveKit в ветке комнаты.
  const others = (participantsQuery.data ?? []).filter(
    (p) => p.role === 'guest' && p.id !== entry.participantId,
  );

  if (meeting.status === 'ended' || meeting.status === 'cancelled') {
    return (
      <RoomMessage
        title="Встреча завершена"
        text={`Встреча «${meeting.title}» уже закончилась.`}
        action={
          entry.role === 'organizer' ? (
            <Button asChild variant="room">
              <Link to={paths.meeting(meeting.id)}>К карточке встречи</Link>
            </Button>
          ) : (
            // карточка встречи только для владельца: гостю – обратно к приглашению
            <Button asChild variant="room">
              <Link to={exitLink(entry, meeting).to}>{exitLink(entry, meeting).label}</Link>
            </Button>
          )
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
            <Link to={paths.join(entry.inviteCode ?? meeting.invite_code ?? '')}>
              Вернуться во встречу
            </Link>
          </Button>
        }
        secondary={
          entry.role === 'organizer' ? (
            <Button asChild variant="room">
              <Link to={paths.meetings}>К встречам</Link>
            </Button>
          ) : undefined
        }
      />
    );
  }

  if (API_MODE === 'http') return <LiveKitRoomPage meeting={meeting} entry={entry} />;
  return <Room meeting={meeting} entry={entry} others={others} onLeave={() => setLeft(true)} />;
}

function Room({
  meeting,
  entry,
  others: initialOthers,
  onLeave,
}: {
  meeting: RoomMeeting;
  entry: RoomEntry;
  others: Participant[];
  onLeave: () => void;
}) {
  const navigate = useNavigate();
  const isOrganizer = entry.role === 'organizer';
  const elapsed = useElapsed();
  const media = useLocalMedia({ initialCamera: entry.cameraOn, initialMic: entry.micOn });

  const [myConsent, setMyConsent] = useState<ConsentState>(entry.consent);
  const [others, setOthers] = useState(() => initialOthers.map((p) => ({ ...p, micOn: true })));
  const [messages, setMessages] = useState<ChatMessage[]>(MOCK_CHAT);
  const [panel, setPanel] = useState<SidePanelTab | null>(() =>
    isOrganizer && meeting.analysis_enabled && isWide() ? 'emotions' : null,
  );
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<RoomParticipant | null>(null);
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
        {isOrganizer && meeting.invite_url && (
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
                      <span className="hidden sm:inline">Ваши эмоции не анализируются</span>
                      <span className="sm:hidden">Вас не анализируют</span>
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
                  onRemove={(id) => setRemoveTarget(participants.find((p) => p.id === id) ?? null)}
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
          <ConfirmDialog
            title="Завершить встречу для всех?"
            text="Все участники будут отключены. Итоги встречи появятся в ее карточке."
            confirmLabel="Завершить встречу"
            onCancel={() => setConfirmEnd(false)}
            // POST /meetings/{id}/end – EMO-75; после завершения – карточка встречи с отчетом
            onConfirm={() => navigate(paths.meeting(meeting.id))}
          />
        )}
        {removeTarget && (
          <ConfirmDialog
            title={`Удалить из встречи: ${removeTarget.name}?`}
            text="Участник будет отключен от встречи."
            confirmLabel="Удалить из встречи"
            onCancel={() => setRemoveTarget(null)}
            // Модерация через REST meeting-service – EMO-75
            onConfirm={() => {
              setOthers((list) => list.filter((p) => p.id !== removeTarget.id));
              setRemoveTarget(null);
            }}
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
