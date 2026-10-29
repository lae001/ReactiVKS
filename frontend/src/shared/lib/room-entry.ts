import type { ConsentState, JoinedMeeting, ParticipantRole } from '@/shared/api/meetings';

/**
 * С чем пользователь входит в комнату: передается из лобби через state навигации.
 * Сведения о встрече и id участника берутся из ответа POST /join/{invite_code}; токен LiveKit
 * комната получит в ветке с LiveKitRoom.
 */
export interface RoomEntry {
  role: ParticipantRole;
  displayName: string;
  consent: ConsentState;
  cameraOn: boolean;
  micOn: boolean;
  inviteCode?: string;
  /** id участника из JoinResult: по нему комната отличает себя в списке участников */
  participantId?: string;
  /** Встреча из JoinResult: гость не может запросить GET /meetings/{id} (он только для владельца) */
  meeting?: JoinedMeeting;
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
    participantId: s.participantId,
    meeting: s.meeting,
  };
}
