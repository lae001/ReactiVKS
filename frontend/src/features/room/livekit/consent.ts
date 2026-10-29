import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';

import { guestErrorMessage, meetingErrorMessage } from '@/features/meetings/errors';
import { type ConsentChange, meetingsApi } from '@/shared/api/meetings';
import { ApiError } from '@/shared/api/problem';
import type { ConsentState } from '@/shared/api/types';
import type { RoomEntry } from '@/shared/lib/room-entry';

import type { LiveKitMeeting } from './LiveKitRoomView';

export const CONSENT_UNSUPPORTED = 'Пока недоступно: сервер ещё не поддерживает эту функцию.';

/**
 * Переключатель «Анализ моих эмоций» (PUT /participants/me/consent): организатор – по Bearer с
 * `?meeting_id=`, гость – по Participant-токену. Источник истины – атрибут `vks.consent` в LiveKit:
 * `current` берется из него, а ответ сервера лишь показывается сразу, не дожидаясь атрибута.
 */
export function useConsentToggle({
  meeting,
  entry,
  current,
}: {
  meeting: LiveKitMeeting;
  entry: RoomEntry;
  current: ConsentState;
}) {
  const [shown, setShown] = useState<ConsentState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState('');
  // анализ во встрече выключили (analysis_disabled): переключатель больше не нужен
  const [disabled, setDisabled] = useState(false);
  // новое уведомление (notice_outdated): текст ждет, пока пользователь его прочитает
  const [notice, setNotice] = useState<string | null>(null);
  const [noticeSeen, setNoticeSeen] = useState(false);

  const mutation = useMutation({
    mutationFn: (decision: ConsentChange) =>
      meetingsApi.setConsent(
        decision,
        entry.role === 'organizer' ? { meetingId: meeting.id } : undefined,
      ),
  });

  const consent = shown ?? current;

  async function request(decision: ConsentChange) {
    setError(null);
    try {
      const result = await mutation.mutateAsync(decision);
      setShown(result.consent_state);
      setNotice(null);
      setAnnouncement(
        decision === 'granted'
          ? 'Анализ ваших эмоций включен.'
          : 'Анализ ваших эмоций отключен. Уже накопленные данные остаются в отчете организатора.',
      );
    } catch (e) {
      if (e instanceof ApiError && e.code === 'analysis_disabled') {
        setDisabled(true);
        setError(meetingErrorMessage(e));
      } else if (e instanceof ApiError && (e.status === 404 || e.status === 405)) {
        // Сервер еще не умеет менять согласие (маршрута нет). Переключатель берет состояние из атрибута
        // vks.consent, а он не менялся, поэтому остается в прежнем положении.
        setError(CONSENT_UNSUPPORTED);
      } else if (e instanceof ApiError && e.code === 'notice_outdated') {
        await showNewNotice();
      } else {
        setError(
          entry.role === 'guest'
            ? guestErrorMessage(e, 'изменить согласие')
            : meetingErrorMessage(e, 'изменить согласие'),
        );
      }
    }
  }

  /** Подгружает актуальное уведомление и просит прочитать его перед включением анализа. */
  async function showNewNotice() {
    const code = entry.inviteCode ?? meeting.invite_code;
    if (noticeSeen || !code) {
      setError(
        'Уведомление об анализе эмоций обновилось. Перезагрузите страницу, прочитайте его и повторите.',
      );
      return;
    }
    try {
      const info = await meetingsApi.getJoinInfo(code);
      if (info.consent_notice) {
        setNoticeSeen(true);
        setNotice(info.consent_notice.text_md);
      } else {
        setDisabled(true);
        setError('В этой встрече анализ эмоций выключен, согласие менять не нужно.');
      }
    } catch (e) {
      setError(meetingErrorMessage(e, 'загрузить уведомление'));
    }
  }

  return {
    consent,
    disabled,
    error,
    announcement,
    notice,
    pending: mutation.isPending,
    dismissError: () => setError(null),
    /** Переключить: включить анализ или отозвать согласие */
    toggle: () => request(consent === 'granted' ? 'revoked' : 'granted'),
    /** Пользователь прочитал новое уведомление и разрешает анализ */
    acceptNotice: () => request('granted'),
    dismissNotice: () => setNotice(null),
  };
}
