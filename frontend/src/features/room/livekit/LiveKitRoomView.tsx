import '@livekit/components-styles';

import {
  LiveKitRoom,
  RoomAudioRenderer,
  useLocalParticipant,
  useParticipants,
  useRoomContext,
} from '@livekit/components-react';
import { type DisconnectReason, MediaDeviceFailure, type RoomOptions } from 'livekit-client';
import { X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router';

import { paths } from '@/shared/config/routes';
import { formatDuration } from '@/shared/lib/format';
import { loadDevicePrefs } from '@/shared/lib/device-prefs';
import type { RoomEntry } from '@/shared/lib/room-entry';
import { cn } from '@/shared/lib/utils';
import { Badge } from '@/shared/ui/badge';
import { Button } from '@/shared/ui/button';
import { CopyLinkButton } from '@/shared/ui/copy-link-button';

import { ControlBar } from '../ControlBar';
import { ParticipantsPanel } from '../ParticipantsPanel';
import { RoomMessage } from '../RoomMessage';
import type { SidePanelTab } from '../types';

import { ConnectionBanner } from './ConnectionBanner';
import { DevicesMenu } from './DevicesMenu';
import { describeDisconnect, type RoomEnd, roomEndText } from './disconnect';
import { deviceFailureText } from './notice';
import { isAgent, roomParticipants } from './participants';
import { RoomGallery } from './RoomGallery';

export interface RoomConnection {
  url: string;
  token: string;
}

export interface LiveKitMeeting {
  id: string;
  title: string;
  invite_url?: string;
  invite_code?: string;
}

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

/**
 * Комната на LiveKit (UC-4): подключение по токену и адресу из слоя API, галерея, панель управления
 * на хуках LiveKit, состав участников из самого LiveKit. Обрыв, удаление и конец встречи –
 * отдельные экраны. Токен меняется только при повторном подключении (`onReconnect`).
 */
export function LiveKitRoomView({
  meeting,
  entry,
  connection,
  onReconnect,
}: {
  meeting: LiveKitMeeting;
  entry: RoomEntry;
  connection: RoomConnection;
  /** Запросить новый токен (rejoin или вход организатора) для «Подключиться снова» */
  onReconnect: () => void;
}) {
  const [end, setEnd] = useState<RoomEnd | null>(null);
  const [deviceNotice, setDeviceNotice] = useState<string | null>(null);

  // Выбор из лобби: те же устройства, что гость проверял перед входом
  const options = useMemo<RoomOptions>(() => {
    const prefs = loadDevicePrefs();
    return {
      adaptiveStream: true,
      dynacast: true,
      audioCaptureDefaults: prefs.micId ? { deviceId: prefs.micId } : undefined,
      videoCaptureDefaults: prefs.cameraId ? { deviceId: prefs.cameraId } : undefined,
      audioOutput: prefs.speakerId ? { deviceId: prefs.speakerId } : undefined,
    };
  }, []);

  if (end) {
    const { title, text } = roomEndText(end, meeting.title);
    const back = paths.join(entry.inviteCode ?? meeting.invite_code ?? '');
    return (
      <RoomMessage
        title={title}
        text={text}
        action={
          end.kind === 'lost' || end.kind === 'left' ? (
            <Button
              variant="room"
              onClick={() => {
                setEnd(null);
                onReconnect();
              }}
            >
              {end.kind === 'lost' ? 'Подключиться снова' : 'Вернуться во встречу'}
            </Button>
          ) : end.kind === 'meeting_ended' && entry.role === 'organizer' ? (
            <Button asChild variant="room">
              <Link to={paths.meeting(meeting.id)}>К карточке встречи</Link>
            </Button>
          ) : (
            <Button asChild variant="room">
              <Link to={entry.role === 'organizer' ? paths.meetings : back}>
                {entry.role === 'organizer' ? 'К встречам' : 'К приглашению'}
              </Link>
            </Button>
          )
        }
      />
    );
  }

  return (
    <LiveKitRoom
      key={connection.token}
      serverUrl={connection.url}
      token={connection.token}
      connect
      video={entry.cameraOn}
      audio={entry.micOn}
      options={options}
      onDisconnected={(reason?: DisconnectReason) => setEnd(describeDisconnect(reason))}
      onError={() => setEnd({ kind: 'lost' })}
      onMediaDeviceFailure={(failure, kind) => setDeviceNotice(deviceFailureText(failure, kind))}
      className="flex h-dvh flex-col bg-room text-room-foreground"
      data-lk-theme="default"
    >
      <RoomShell
        meeting={meeting}
        entry={entry}
        deviceNotice={deviceNotice}
        onDismissNotice={() => setDeviceNotice(null)}
        onDeviceNotice={setDeviceNotice}
      />
    </LiveKitRoom>
  );
}

function RoomShell({
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
  const elapsed = useElapsed();
  const live = useParticipants();
  const { localParticipant, isMicrophoneEnabled, isCameraEnabled } = useLocalParticipant();
  const [panel, setPanel] = useState<SidePanelTab | null>(null);
  const isOrganizer = entry.role === 'organizer';

  const people = roomParticipants(live);
  // Индикатор виден всем, пока в комнате есть ML-агент (vks.kind = agent)
  const analysisRunning = live.some(isAgent);

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
      {deviceNotice && (
        <p
          role="alert"
          className="flex items-center justify-between gap-3 bg-destructive/15 px-4 py-2 text-sm"
        >
          {deviceNotice}
          <Button
            variant="room"
            size="icon"
            className="size-7 bg-transparent"
            aria-label="Скрыть сообщение"
            onClick={onDismissNotice}
          >
            <X />
          </Button>
        </p>
      )}

      <div className="relative flex min-h-0 flex-1">
        <RoomGallery />
        {panel && (
          <aside
            aria-label={TAB_TITLE[panel]}
            className="absolute inset-0 z-10 flex flex-col border-room-border bg-room sm:left-auto sm:w-96 sm:border-l lg:static lg:w-96"
          >
            <div className="flex h-12 shrink-0 items-center gap-1 border-b border-room-border px-2">
              <div role="tablist" aria-label="Боковая панель" className="flex flex-1 gap-1">
                <button
                  type="button"
                  role="tab"
                  id="tab-participants"
                  aria-selected
                  aria-controls="side-panel"
                  className={cn('h-8 rounded-md bg-room-surface px-3 text-sm text-room-foreground')}
                >
                  {TAB_TITLE.participants} · {people.length}
                </button>
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
              aria-labelledby="tab-participants"
              className="min-h-0 flex-1 overflow-y-auto p-4"
            >
              <ParticipantsPanel
                participants={people}
                canModerate={false}
                onMute={() => undefined}
                onRemove={() => undefined}
              />
            </div>
          </aside>
        )}
      </div>

      <RoomAudioRenderer />
      <ControlBar
        // кнопки организатора (эмоции, «Завершить встречу») – следующие этапы
        isOrganizer={false}
        analysisEnabled={false}
        micOn={isMicrophoneEnabled}
        cameraOn={isCameraEnabled}
        consent="not_required"
        panel={panel}
        showChat={false}
        devices={<DevicesMenu />}
        onToggleMic={() => void toggle('mic')}
        onToggleCamera={() => void toggle('camera')}
        onToggleConsent={() => undefined}
        onTogglePanel={(tab) => setPanel((current) => (current === tab ? null : tab))}
        onLeave={() => void room.disconnect()}
      />
    </>
  );
}
