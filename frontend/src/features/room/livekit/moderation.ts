import { useMutation } from '@tanstack/react-query';

import { type MuteKind, meetingsApi } from '@/shared/api/meetings';

import { restIdOf } from './participants';

/** Модерация организатора через REST meeting-service: LiveKit-вызовы делает сам сервер. */
export function useModeration(meetingId: string, { onEnded }: { onEnded?: () => void } = {}) {
  const mute = useMutation({
    mutationFn: ({ identity, kind }: { identity: string; kind: MuteKind }) =>
      meetingsApi.muteParticipant(meetingId, restIdOf(identity), kind),
  });
  const remove = useMutation({
    mutationFn: (identity: string) => meetingsApi.removeParticipant(meetingId, restIdOf(identity)),
  });
  // onEnded – на уровне хука: комната закрывается самим LiveKit раньше, чем придет ответ, и
  // обработчик, переданный в mutate(), к тому времени уже не вызвался бы (компонент размонтирован)
  const end = useMutation({
    mutationFn: () => meetingsApi.endMeeting(meetingId),
    onSuccess: () => onEnded?.(),
  });
  return { mute, remove, end };
}

/** Одно действие модерации, ожидающее подтверждения. */
export type PendingAction =
  | { kind: 'mute_audio'; identity: string; name: string }
  | { kind: 'mute_video'; identity: string; name: string }
  | { kind: 'remove'; identity: string; name: string }
  | { kind: 'end' };

/** Тексты диалога подтверждения; кнопка называет действие так же, как исходная. */
export function confirmText(action: PendingAction): {
  title: string;
  text: string;
  confirmLabel: string;
} {
  switch (action.kind) {
    case 'mute_audio':
      return {
        title: `Выключить микрофон: ${action.name}?`,
        text: 'Участник сможет включить микрофон снова сам.',
        confirmLabel: 'Выключить микрофон',
      };
    case 'mute_video':
      return {
        title: `Выключить камеру: ${action.name}?`,
        text: 'Участник сможет включить камеру снова сам.',
        confirmLabel: 'Выключить камеру',
      };
    case 'remove':
      return {
        title: `Удалить из встречи: ${action.name}?`,
        text: 'Участник будет отключен и не сможет вернуться по этой ссылке.',
        confirmLabel: 'Удалить из встречи',
      };
    case 'end':
      return {
        title: 'Завершить встречу для всех?',
        text: 'Все участники будут отключены. Итоги встречи появятся в ее карточке.',
        confirmLabel: 'Завершить встречу',
      };
  }
}
