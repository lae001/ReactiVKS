import '@livekit/components-styles';

import { LiveKitRoom, VideoConference } from '@livekit/components-react';
import { type FormEvent, useState } from 'react';

import { checkWebRtcSupport, describeWebRtcProblem } from '@/shared/lib/webrtc-support';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { Label } from '@/shared/ui/label';

interface Connection {
  serverUrl: string;
  token: string;
}

/**
 * Песочница LiveKit (EMO-17): подключение к комнате по адресу сервера и токену.
 * Токен выпускается вручную (`lk token create …`), в рабочем сценарии его выдает meeting-service.
 * Инструкция – docs/frontend/webrtc-livekit-notes.md. Доступна только в dev-сборке.
 */
export default function LivekitSandboxPage() {
  const [conn, setConn] = useState<Connection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const problem = describeWebRtcProblem(checkWebRtcSupport());

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    setError(null);
    setConn({
      serverUrl: String(data.get('serverUrl') ?? '').trim(),
      token: String(data.get('token') ?? '').trim(),
    });
  }

  if (conn) {
    return (
      <div className="h-dvh" data-lk-theme="default">
        <LiveKitRoom
          serverUrl={conn.serverUrl}
          token={conn.token}
          connect
          video
          audio
          options={{ adaptiveStream: true, dynacast: true }}
          onDisconnected={() => setConn(null)}
          onError={(err) => {
            setError(err.message);
            setConn(null);
          }}
          style={{ height: '100%' }}
        >
          <VideoConference />
        </LiveKitRoom>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-lg flex-col gap-6 px-6 py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Песочница LiveKit</h1>
        <p className="text-sm text-muted-foreground">
          Откройте страницу в двух вкладках с разными токенами (разный identity), чтобы увидеть друг
          друга.
        </p>
      </header>
      {problem && (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm"
        >
          {problem}
        </p>
      )}
      {error && (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm"
        >
          Не удалось подключиться: {error}
        </p>
      )}
      <form className="flex flex-col gap-4" onSubmit={onSubmit}>
        <div className="flex flex-col gap-2">
          <Label htmlFor="serverUrl">Адрес сервера</Label>
          <Input
            id="serverUrl"
            name="serverUrl"
            required
            defaultValue={import.meta.env.VITE_LIVEKIT_URL ?? 'ws://localhost:7880'}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="token">Токен доступа</Label>
          <Input id="token" name="token" required placeholder="eyJhbGciOi…" />
        </div>
        <Button type="submit">Подключиться</Button>
      </form>
    </div>
  );
}
