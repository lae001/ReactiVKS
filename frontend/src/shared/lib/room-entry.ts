import type { ConsentState, ParticipantRole } from '@/shared/api/types';

/**
 * С чем пользователь входит в комнату: передается из лобби через state навигации.
 * На тестовых данных заменяет JoinResult и participant_token (EMO-74, EMO-89).
 */
export interface RoomEntry {
  role: ParticipantRole;
  displayName: string;
  consent: ConsentState;
  cameraOn: boolean;
  micOn: boolean;
  inviteCode?: string;
}

export function readRoomEntry(state: unknown): RoomEntry | null {
  if (typeof state !== 'object' || state === null) return null;
  const s = state as Partial<RoomEntry>;
  if ((s.role !== 'guest' && s.role !== 'organizer') || typeof s.displayName !== 'string') {
    return null;
  }
  return {
    role: s.role,
    displayName: s.displayName,
    consent: s.consent ?? 'not_required',
    cameraOn: s.cameraOn ?? true,
    micOn: s.micOn ?? true,
    inviteCode: s.inviteCode,
  };
}
