import {
  RoomAudioRenderer,
  useChat,
  useDataChannel,
  useLocalParticipant,
  useParticipants,
  useRoomContext,
} from '@livekit/components-react';
import { MediaDeviceFailure } from 'livekit-client';
import { X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router';

import { meetingErrorMessage } from '@/features/meetings/errors';
import { paths } from '@/shared/config/routes';
import { formatDuration } from '@/shared/lib/format';
import type { RoomEntry } from '@/shared/lib/room-entry';
import { cn } from '@/shared/lib/utils';
import { Badge } from '@/shared/ui/badge';
import { Button } from '@/shared/ui/button';
import { CopyLinkButton } from '@/shared/ui/copy-link-button';

import { ChatPanel } from '../ChatPanel';
import { EmotionPanel } from '@/features/emotions/EmotionPanel';

import { ConfirmDialog } from '../ConfirmDialog';
import { ControlBar } from '../ControlBar';
import { ParticipantsPanel } from '../ParticipantsPanel';
import type { SidePanelTab } from '../types';

import { useChatNotifications, useUnreadTitle } from './chat-notifications';
import { ChatToasts } from './ChatToasts';
import { ConnectionBanner } from './ConnectionBanner';
import { useConsentToggle } from './consent';
import { DevicesPanel } from './DevicesMenu';
import { EMOTIONS_MOCK_NOTICE, mockEmotionSnapshot } from './emotions-mock';
import { confirmText, type PendingAction, useModeration } from './moderation';
import { deviceFailureText } from './notice';
import { isAgent, roomParticipants } from './participants';
import { ReactionsOverlay } from './ReactionsOverlay';
import { REACTION_TOPIC, useReactions } from './reactions';
import { RoomGallery } from './RoomGallery';
import type { LiveKitMeeting } from './LiveKitRoomView';

const TAB_TITLE: Record<SidePanelTab, string> = {
  participants: 'Участники',
  emotions: 'Эмоции',
  chat: 'Чат',
};

function useElapsed(): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);
  return seconds;
}

const clock = (timestamp: number) =>
  new Date(timestamp).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });

/** Содержимое комнаты внутри `<LiveKitRoom>`: шапка, галерея, боковая панель, управление. */
export function RoomShell({
  meeting,
  entry,
  deviceNotice,
  onDismissNotice,
  onDeviceNotice,
}: {
  meeting: LiveKitMeeting;
  entry: RoomEntry;
  deviceNotice: string | null;
  onDismissNotice: () => void;
  onDeviceNotice: (text: string) => void;
}) {
  const room = useRoomContext();
  const navigate = useNavigate();
  const elapsed = useElapsed();
  const live = useParticipants();
  const { localParticipant, isMicrophoneEnabled, isCameraEnabled } = useLocalParticipant();
  // Чат на LiveKit (тема lk.chat): история живет, пока открыта вкладка, и нигде не сохраняется
  const chat = useChat();
  // Реакции (эмодзи) идут по каналу данных, без гарантии доставки; в чат они не попадают
  const reactions = useReactions(
    useCallback(
      (data, options) => localParticipant.publishData(data as Uint8Array<ArrayBuffer>, options),
      [localParticipant],
    ),
  );
  useDataChannel(REACTION_TOPIC, reactions.receive);
  const moderation = useModeration(meeting.id, {
    onEnded: () => navigate(paths.meeting(meeting.id)),
  });
  const [panel, setPanelState] = useState<SidePanelTab | null>(null);
  const notifications = useChatNotifications(chat.chatMessages, panel === 'chat');
  useUnreadTitle(notifications.unread);
  // Открытие чата обнуляет счетчик и убирает уведомления
  function setPanel(
    next: SidePanelTab | null | ((current: SidePanelTab | null) => SidePanelTab | null),
  ) {
    const value = typeof next === 'function' ? next(panel) : next;
    if (value === 'chat') notifications.markRead();
    setPanelState(value);
  }
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [chatError, setChatError] = useState(false);
  const isOrganizer = entry.role === 'organizer';

  const people = roomParticipants(live);
  // Индикатор виден всем, пока в комнате есть ML-агент (vks.kind = agent)
  const analysisRunning = live.some(isAgent);
  const self = people.find((p) => p.isSelf);
  const consent = useConsentToggle({ meeting, entry, current: self?.consent ?? 'not_required' });
  const analysisOn = meeting.analysis_enabled && !consent.disabled;
  // Панель эмоций – только организатору и только если во встрече включен анализ
  const showEmotions = isOrganizer && analysisOn;
  const tabs: SidePanelTab[] = showEmotions
    ? ['participants', 'emotions', 'chat']
    : ['participants', 'chat'];

  async function toggle(kind: 'mic' | 'camera') {
    try {
      if (kind === 'mic') await localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled);
      else await localParticipant.setCameraEnabled(!isCameraEnabled);
    } catch (e) {
      const name = e instanceof Error ? e.name : '';
      const failure =
        name === 'NotAllowedError'
          ? MediaDeviceFailure.PermissionDenied
          : name === 'NotFoundError'
            ? MediaDeviceFailure.NotFound
            : name === 'NotReadableError'
              ? MediaDeviceFailure.DeviceInUse
              : undefined;
      onDeviceNotice(deviceFailureText(failure, kind === 'mic' ? 'audioinput' : 'videoinput'));
    }
  }

  const mutation =
    pending?.kind === 'end'
      ? moderation.end
      : pending?.kind === 'remove'
        ? moderation.remove
        : moderation.mute;

  function confirm() {
    if (!pending) return;
    const done = { onSuccess: () => setPending(null) };
    switch (pending.kind) {
      case 'mute_audio':
        return moderation.mute.mutate({ identity: pending.identity, kind: 'audio' }, done);
      case 'mute_video':
        return moderation.mute.mutate({ identity: pending.identity, kind: 'video' }, done);
      case 'remove':
        return moderation.remove.mutate(pending.identity, done);
      case 'end':
        return moderation.end.mutate();
    }
  }

  function cancel() {
    moderation.mute.reset();
    moderation.remove.reset();
    moderation.end.reset();
    setPending(null);
  }

  function ask(action: PendingAction) {
    cancel();
    setPending(action);
  }

  return (
    <>
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-room-border px-4">
        <div className="flex min-w-0 flex-1 items-baseline gap-3">
          <h1 className="truncate text-sm font-medium">{meeting.title}</h1>
          <span className="text-sm text-room-muted" aria-label="Длительность встречи">
            {formatDuration(elapsed)}
          </span>
        </div>
        {analysisRunning && (
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

      <ConnectionBanner />
      <p className="sr-only" aria-live="polite">
        {consent.announcement}
      </p>
      {(deviceNotice || chatError || consent.error) && (
        <p
          role="alert"
          className="flex items-center justify-between gap-3 bg-destructive/15 px-4 py-2 text-sm"
        >
          {deviceNotice ??
            consent.error ??
            'Не удалось отправить сообщение. Проверьте соединение и повторите.'}
          <Button
            variant="room"
            size="icon"
            className="size-7 bg-transparent"
            aria-label="Скрыть сообщение"
            onClick={() => {
              onDismissNotice();
              setChatError(false);
              consent.dismissError();
            }}
          >
            <X />
          </Button>
        </p>
      )}

      <div className="relative flex min-h-0 flex-1">
        <RoomGallery />
        <ReactionsOverlay items={reactions.floating} onExpire={reactions.expire} />
        <ChatToasts
          toasts={notifications.toasts}
          onOpen={() => setPanel('chat')}
          onExpire={notifications.dismissToast}
        />
        {panel && (
          <aside
            aria-label={TAB_TITLE[panel]}
            className="absolute inset-0 z-10 flex flex-col border-room-border bg-room sm:left-auto sm:w-96 sm:border-l lg:static lg:w-96"
          >
            <div className="flex h-12 shrink-0 items-center gap-1 border-b border-room-border px-2">
              <div role="tablist" aria-label="Боковая панель" className="flex flex-1 gap-1">
                {tabs.map((t) => (
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
                    {t === 'participants' && ` · ${people.length}`}
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
                  participants={people}
                  canModerate={isOrganizer}
                  onMute={(id) =>
                    ask({
                      kind: 'mute_audio',
                      identity: id,
                      name: people.find((p) => p.id === id)?.name ?? 'участник',
                    })
                  }
                  onMuteCamera={(id) =>
                    ask({
                      kind: 'mute_video',
                      identity: id,
                      name: people.find((p) => p.id === id)?.name ?? 'участник',
                    })
                  }
                  onRemove={(id) =>
                    ask({
                      kind: 'remove',
                      identity: id,
                      name: people.find((p) => p.id === id)?.name ?? 'участник',
                    })
                  }
                />
              )}
              {panel === 'emotions' && (
                <div className="flex flex-col gap-4">
                  <p
                    role="note"
                    className="rounded-md border border-signal/50 bg-signal/10 px-3 py-2 text-xs"
                  >
                    {EMOTIONS_MOCK_NOTICE}
                  </p>
                  <EmotionPanel participants={mockEmotionSnapshot(people)} elapsed={elapsed} />
                </div>
              )}
              {panel === 'chat' && (
                <ChatPanel
                  messages={chat.chatMessages.map((m) => ({
                    id: m.id,
                    author: m.from?.isLocal ? 'Вы' : (m.from?.name ?? 'Участник'),
                    text: m.message,
                    at: clock(m.timestamp),
                  }))}
                  onSend={(text) => {
                    setChatError(false);
                    chat.send(text).catch(() => setChatError(true));
                  }}
                />
              )}
            </div>
          </aside>
        )}

        {consent.notice && (
          <ConfirmDialog
            title="Обновилось уведомление об анализе эмоций"
            text={consent.notice}
            confirmLabel="Разрешаю анализ"
            confirmVariant="default"
            busy={consent.pending}
            error={consent.error}
            onCancel={consent.dismissNotice}
            onConfirm={() => void consent.acceptNotice()}
          />
        )}
        {pending && (
          <ConfirmDialog
            {...confirmText(pending)}
            busy={mutation.isPending}
            error={
              mutation.isError ? meetingErrorMessage(mutation.error, 'выполнить действие') : null
            }
            onCancel={cancel}
            onConfirm={confirm}
          />
        )}
      </div>

      <RoomAudioRenderer />
      <ControlBar
        isOrganizer={isOrganizer}
        analysisEnabled={analysisOn}
        micOn={isMicrophoneEnabled}
        cameraOn={isCameraEnabled}
        consent={consent.consent}
        panel={panel}
        devicesPanel={<DevicesPanel />}
        reactions={{
          onPick: (emoji) => void reactions.send(emoji),
          blockedUntil: reactions.blockedUntil,
          tooFrequent: reactions.tooFrequent,
        }}
        onToggleMic={() => void toggle('mic')}
        onToggleCamera={() => void toggle('camera')}
        onToggleConsent={() => void consent.toggle()}
        unreadChat={notifications.unread}
        onTogglePanel={(tab) => setPanel((current) => (current === tab ? null : tab))}
        onLeave={() => void room.disconnect()}
        onEnd={isOrganizer ? () => ask({ kind: 'end' }) : undefined}
      />
    </>
  );
}
