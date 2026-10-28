import type { Participant } from 'livekit-client';

import type { ConsentState, ParticipantRole } from '@/shared/api/types';

import type { RoomParticipant } from '../types';

/**
 * Состав участников берется из LiveKit, а не из REST: имя – `name` в токене, остальное – атрибуты
 * `vks.role`, `vks.consent`, `vks.kind` (docs/api/livekit-integration.md). REST-список участников
 * доступен только организатору и нужен ему для модерации.
 */
export const ATTR = {
  role: 'vks.role',
  consent: 'vks.consent',
  kind: 'vks.kind',
} as const;

const CONSENTS: ConsentState[] = ['granted', 'denied', 'revoked', 'not_required'];

/** ML-агент (`vks.kind = agent`): в галерее и списке участников не показывается. */
export function isAgent(p: Pick<Participant, 'attributes'>): boolean {
  return p.attributes?.[ATTR.kind] === 'agent';
}

export function roleOf(p: Pick<Participant, 'attributes'>): ParticipantRole {
  return p.attributes?.[ATTR.role] === 'organizer' ? 'organizer' : 'guest';
}

export function consentOf(p: Pick<Participant, 'attributes'>): ConsentState {
  const value = p.attributes?.[ATTR.consent];
  return CONSENTS.find((c) => c === value) ?? 'not_required';
}

/** id участника в REST (`/participants/{id}/…`) из identity LiveKit `p_<id>`. */
export function restIdOf(identity: string): string {
  return identity.startsWith('p_') ? identity.slice(2) : identity;
}

type LiveParticipant = Pick<
  Participant,
  'identity' | 'name' | 'attributes' | 'isLocal' | 'isMicrophoneEnabled' | 'isCameraEnabled'
>;

/** Участник LiveKit для интерфейса; агент не показывается (null). */
export function toRoomParticipant(p: LiveParticipant): RoomParticipant | null {
  if (isAgent(p)) return null;
  return {
    id: p.identity,
    name: p.name || 'Участник',
    role: roleOf(p),
    isSelf: p.isLocal,
    consent: consentOf(p),
    micOn: p.isMicrophoneEnabled,
    cameraOn: p.isCameraEnabled,
  };
}

/** Все люди в комнате: сначала вы, затем остальные в порядке входа. */
export function roomParticipants(list: LiveParticipant[]): RoomParticipant[] {
  const people = list.map(toRoomParticipant).filter((p): p is RoomParticipant => p !== null);
  return [...people.filter((p) => p.isSelf), ...people.filter((p) => !p.isSelf)];
}
