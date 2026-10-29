import '@livekit/components-styles';

import { LiveKitRoom } from '@livekit/components-react';
import { type DisconnectReason, type RoomOptions } from 'livekit-client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router';

import { paths } from '@/shared/config/routes';
import { loadDevicePrefs } from '@/shared/lib/device-prefs';
import type { RoomEntry } from '@/shared/lib/room-entry';
import { Button } from '@/shared/ui/button';

import { RoomMessage } from '../RoomMessage';

import {
  describeDisconnect,
  isAbortedBeforeConnect,
  isCancelledConnect,
  type RoomEnd,
  roomEndText,
} from './disconnect';
import { deviceFailureText } from './notice';
import { RoomShell } from './RoomShell';

/** Сколько ждать подключения, прежде чем считать, что оно не состоялось (страховка от «вечного» ожидания) */
const CONNECT_WATCHDOG_MS = 20_000;

export interface RoomConnection {
  url: string;
  token: string;
}

export interface LiveKitMeeting {
  id: string;
  title: string;
  analysis_enabled: boolean;
  invite_url?: string;
  invite_code?: string;
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

  // Подключалась ли комната: отмену попытки (StrictMode, смена токена) нельзя путать с обрывом связи
  const connected = useRef(false);
  useEffect(() => {
    connected.current = false;
    const timer = window.setTimeout(() => {
      if (!connected.current) setEnd({ kind: 'lost' });
    }, CONNECT_WATCHDOG_MS);
    return () => window.clearTimeout(timer);
  }, [connection.token]);

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
      onConnected={() => {
        connected.current = true;
      }}
      onDisconnected={(reason?: DisconnectReason) => {
        const wasConnected = connected.current;
        connected.current = false;
        if (isAbortedBeforeConnect(reason, wasConnected)) return;
        setEnd(describeDisconnect(reason));
      }}
      onError={(error) => {
        if (isCancelledConnect(error)) return;
        setEnd({ kind: 'lost' });
      }}
      onMediaDeviceFailure={(failure, kind) => setDeviceNotice(deviceFailureText(failure, kind))}
      // Размер – инлайном: стили LiveKit (`.lk-room-container`, без слоя) перебивают классы Tailwind
      style={{ display: 'flex', flexDirection: 'column', height: '100dvh' }}
      className="bg-room text-room-foreground"
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
