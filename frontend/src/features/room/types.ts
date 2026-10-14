import type { ConsentState, ParticipantRole } from '@/shared/api/types';

/** Участник в комнате с точки зрения интерфейса; с LiveKit (EMO-75) – из useParticipants(). */
export interface RoomParticipant {
  id: string;
  name: string;
  role: ParticipantRole;
  isSelf: boolean;
  consent: ConsentState;
  micOn: boolean;
  cameraOn: boolean;
}

export type SidePanelTab = 'participants' | 'emotions' | 'chat';
