import { useEffect, useState } from 'react';

import { apiFetch } from '@/shared/api/client';
import type { ReportSeries } from '@/features/reports/RemoteReport';
import { EMOTION_LABELS } from '@/shared/config/emotions';
import { refreshSession, useSessionStore } from '@/shared/api/session';
import { emptyEmotions, reduceEmotions } from './stream';

/** Отдельный канал организатора; никогда не управляет медиасоединением LiveKit. */
export function useEmotions(meetingId: string, enabled: boolean) {
  const [view, setView] = useState({
    meetingId: '',
    data: emptyEmotions(),
    status: 'Подключение…',
  });
  const userId = useSessionStore((s) => s.user?.id);
  useEffect(() => {
    if (!enabled) return;
    let disposed = false;
    let forbidden = false;
    let socket: WebSocket | undefined;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout>;
    let watchdog: ReturnType<typeof setTimeout>;
    let receivedAt = 0;
    let lastTs: string | undefined;
    const abort = new AbortController();
    let data = emptyEmotions();
    const show = (status: string) => {
      if (!disposed) setView({ meetingId, data, status });
    };
    const send = (body: unknown) => {
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(body));
    };
    const stop = () => {
      forbidden = true;
      receivedAt = 0;
      clearTimeout(timer);
      data = emptyEmotions();
      show('Нет доступа к данным встречи');
      socket?.close();
    };
    function connect() {
      if (disposed || forbidden) return;
      show('Подключение…');
      socket = new WebSocket(
        `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`,
        'vks.v1',
      );
      watchdog = setTimeout(() => socket?.close(), 10000);
      socket.onopen = () => send({ type: 'auth', token: useSessionStore.getState().accessToken });
      socket.onmessage = (event) => {
        if (disposed || forbidden) return;
        let m: Record<string, unknown>;
        try {
          m = JSON.parse(String(event.data));
        } catch {
          return;
        }
        if (!m || typeof m !== 'object') return;
        if (m.type === 'welcome') {
          send({ type: 'subscribe', meeting_id: meetingId });
          return;
        }
        if (m.type === 'error') {
          if (m.code === 'forbidden' || m.code === 'not_found') stop();
          else {
            data = emptyEmotions();
            show('Сервис отклонил запрос');
          }
          return;
        }
        if (m.meeting_id !== meetingId) return;
        if (m.type === 'meeting.ended') {
          stop();
          return;
        }
        data = reduceEmotions(data, m, meetingId);
        if (m.type === 'subscribed') {
          if (lastTs) {
            void apiFetch<ReportSeries>(`/api/v1/reports/${meetingId}/series`, {
              signal: abort.signal,
              query: { since: lastTs, resolution: '1s' },
            })
              .then((series) => {
                if (disposed || forbidden || series.labels.join() !== EMOTION_LABELS.join()) return;
                const history = { ...data.history };
                for (const row of series.series)
                  history[row.participant_id] = [
                    ...row.points
                      .filter((p) => p.p && Date.parse(p.ts) >= Date.now() - 300000)
                      .map((p) => ({ ts: p.ts, confidence: Math.max(...p.p!) })),
                    ...(history[row.participant_id] ?? []),
                  ].slice(-1500);
                data = { ...data, history };
                show('Подключено');
              })
              .catch(() => {
                if (!disposed && !forbidden)
                  show('Подключено; пропущенный участок графика недоступен');
              });
          }
          clearTimeout(watchdog);
          attempt = 0;
        }
        lastTs = data.lastTs ?? lastTs;
        receivedAt = Date.now();
        show('Подключено');
      };
      socket.onclose = async (event) => {
        clearTimeout(watchdog);
        if (disposed || forbidden) return;
        data = emptyEmotions();
        show('Поток эмоций недоступен. Видеосвязь продолжается.');
        if (event.code === 4403 || event.code === 4400) {
          stop();
          return;
        }
        if (event.code === 4401) {
          try {
            if (!(await refreshSession())) {
              stop();
              return;
            }
          } catch {
            /* повтор после задержки */
          }
        }
        if (!disposed && !forbidden)
          timer = setTimeout(
            connect,
            Math.min(10000, 500 * 2 ** attempt++) * (0.8 + Math.random() * 0.2),
          );
      };
    }
    const unsubscribe = useSessionStore.subscribe((next, previous) => {
      if (!next.accessToken) {
        stop();
        return;
      }
      if (next.accessToken !== previous.accessToken)
        send({ type: 'auth.refresh', token: next.accessToken });
    });
    const ping = setInterval(() => send({ type: 'ping' }), 20000);
    const stale = setInterval(() => {
      if (receivedAt && Date.now() - receivedAt > 5000) {
        data = {
          ...data,
          analysis: 'unavailable',
          participants: data.participants.map((p) => ({ ...p, last: null })),
        };
        show('Данные устарели. Ожидаем обновления.');
      }
    }, 1000);
    connect();
    return () => {
      disposed = true;
      abort.abort();
      unsubscribe();
      clearTimeout(timer);
      clearTimeout(watchdog);
      clearInterval(ping);
      clearInterval(stale);
      socket?.close();
    };
  }, [meetingId, enabled, userId]);
  return enabled && view.meetingId === meetingId
    ? view
    : { meetingId, data: emptyEmotions(), status: 'Поток не подключён' };
}
