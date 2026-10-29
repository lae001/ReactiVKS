import '@livekit/components-styles';

import { LiveKitRoom } from '@livekit/components-react';
import { type DisconnectReason, type RoomOptions } from 'livekit-client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router';

import { usePageScrollLock } from '@/shared/hooks/use-page-scroll-lock';
import { paths } from '@/shared/config/routes';
import { loadDevicePrefs } from '@/shared/lib/device-prefs';
import type { RoomEntry } from '@/shared/lib/room-entry';
import { Button } from '@/shared/ui/button';

import { RoomMessage } from '../RoomMessage';

import {
  describeDisconnect,
  isAbortedBeforeConnect,
  isConnectionLost,
  type RoomEnd,
  roomEndText,
} from './disconnect';
import { exitLink } from './exit-link';
import { deviceFailureText } from './notice';
import { clearRoomState, loadDevices } from './room-state';
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
  /** Начало встречи (есть у организатора; у гостя по контракту его нет – см. meeting-timer.ts) */
  started_at?: string | null;
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
  // Комната на весь экран: страница под ней не прокручивается (на экранах выхода прокрутка возвращается)
  usePageScrollLock(end === null);
  const [deviceNotice, setDeviceNotice] = useState<string | null>(null);

  // Последнее состояние микрофона и камеры этой вкладки: после обновления страницы выключенное остается выключенным.
  // Первый вход берет значения из лобби (entry); запись обновляет RoomShell при каждом переключении.
  const devices = useMemo(
    () => loadDevices(meeting.id) ?? { mic: entry.micOn, camera: entry.cameraOn },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- читаем при входе и при новом подключении (токене)
    [meeting.id, connection.token],
  );

  // Подключалась ли комната: отмену попытки (StrictMode, смена токена) нельзя путать с обрывом связи
  const connected = useRef(false);
  useEffect(() => {
    connected.current = false;
    const timer = window.setTimeout(() => {
      if (!connected.current) setEnd({ kind: 'lost', detail: 'CONNECT_TIMEOUT' });
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
    const { title, text, detail } = roomEndText(end, meeting.title);
    const exit = exitLink(entry);
    // главная кнопка уже ведет наружу (удален, завершена, вошли с другого устройства) – вторую не дублируем
    const primaryLeaves =
      end.kind === 'removed' || end.kind === 'duplicate' || end.kind === 'meeting_ended';
    const exitButton = (
      <Button asChild variant="room">
        <Link to={exit.to}>{exit.label}</Link>
      </Button>
    );
    return (
      <RoomMessage
        title={title}
        text={text}
        detail={detail}
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
            exitButton
          )
        }
        secondary={primaryLeaves ? undefined : exitButton}
      />
    );
  }

  return (
    <LiveKitRoom
      key={connection.token}
      serverUrl={connection.url}
      token={connection.token}
      connect
      video={devices.camera}
      audio={devices.mic}
      options={options}
      onConnected={() => {
        connected.current = true;
      }}
      onDisconnected={(reason?: DisconnectReason) => {
        const wasConnected = connected.current;
        connected.current = false;
        if (isAbortedBeforeConnect(reason, wasConnected)) return;
        const next = describeDisconnect(reason);
        // Завершение встречи и удаление участника: сохраненное состояние вкладки больше не нужно. Явный выход
        // очищает RoomShell по кнопке «Выйти»: `CLIENT_INITIATED` приходит и при обновлении страницы (LiveKit
        // отключается по beforeunload), а тогда состояние как раз должно сохраниться.
        if (next.kind === 'meeting_ended' || next.kind === 'removed') clearRoomState(meeting.id);
        setEnd(next);
      }}
      onError={(error) => {
        // отказ камеры или микрофона – не обрыв: встреча идет, причину показывает onMediaDeviceFailure
        if (isConnectionLost(error)) setEnd({ kind: 'lost', detail: error.message });
      }}
      onMediaDeviceFailure={(failure, kind) => setDeviceNotice(deviceFailureText(failure, kind))}
      // Размер – инлайном: стили LiveKit (`.lk-room-container`, без слоя) перебивают классы Tailwind.
      // Корень закреплен на всё окно (fixed + inset 0, а не 100dvh): что бы ни лежало внутри, страница
      // не прокручивается и не сдвигается программно (`clip`, а не `hidden`: у `hidden` scrollLeft можно изменить
      // фокусом); ширина и высота `auto` отменяют `100%` из стилей LiveKit.
      style={{
        position: 'fixed',
        inset: 0,
        width: 'auto',
        height: 'auto',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'clip',
      }}
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
