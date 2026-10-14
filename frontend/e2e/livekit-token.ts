import { AccessToken } from 'livekit-server-sdk';

// Вспомогательный код только для e2e (EMO-53): пока нет meeting-service, токены подписываются
// ключами dev-режима LiveKit (`livekit-server --dev`). В код приложения это не попадает.
export const LIVEKIT_URL = process.env.LIVEKIT_URL ?? 'ws://localhost:7880';
const API_KEY = process.env.LIVEKIT_API_KEY ?? 'devkey';
const API_SECRET = process.env.LIVEKIT_API_SECRET ?? 'secret';

export async function createToken(
  room: string,
  identity: string,
  name = identity,
): Promise<string> {
  const token = new AccessToken(API_KEY, API_SECRET, { identity, name, ttl: '10m' });
  token.addGrant({ roomJoin: true, room, canPublish: true, canSubscribe: true });
  return token.toJwt();
}
