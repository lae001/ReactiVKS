import { useState } from 'react'
import { LiveKitRoom, RoomAudioRenderer, VideoConference } from '@livekit/components-react'
import '@livekit/components-styles'

interface Props {
  /** Токен из meeting-service (в спринте 1 — выданный вручную через `lk token create`). */
  token: string
  serverUrl?: string
}

/**
 * Спайк EMO-17: минимальное подключение к комнате LiveKit.
 * Не привязан к маршрутам; в спринте 3 на его основе будет собрана страница комнаты.
 * Проверка: `livekit-server --dev`, токен через `lk token create --join --room test --identity u1`.
 */
export function LiveKitConnectExample({
  token,
  serverUrl = import.meta.env.VITE_LIVEKIT_URL,
}: Props) {
  const [connected, setConnected] = useState(false)
  return (
    <div data-lk-theme="default" style={{ height: '70vh' }}>
      <LiveKitRoom
        token={token}
        serverUrl={serverUrl}
        connect
        audio
        video
        onConnected={() => setConnected(true)}
        onDisconnected={() => setConnected(false)}
      >
        <VideoConference />
        <RoomAudioRenderer />
        <span className="sr-only">{connected ? 'Подключено' : 'Подключение…'}</span>
      </LiveKitRoom>
    </div>
  )
}
