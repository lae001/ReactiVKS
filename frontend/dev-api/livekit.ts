import { AccessToken, RoomServiceClient, TrackSource, TrackType } from 'livekit-server-sdk';

import type { LiveKitGateway } from './app.ts';
import { LiveKitUnavailableError } from './app.ts';

/**
 * Настоящий LiveKit (`livekit-server --dev`): токены подписываются dev-ключами devkey/secret,
 * серверные вызовы идут через RoomServiceClient. Роль LiveKitGateway из docs/api/livekit-integration.md.
 */
const API_KEY = 'devkey';
const API_SECRET = 'secret';
const SOURCES = [
  TrackSource.CAMERA,
  TrackSource.MICROPHONE,
  TrackSource.SCREEN_SHARE,
  TrackSource.SCREEN_SHARE_AUDIO,
];

/** Ошибка «такого нет» (комнаты или участника) для Twirp-ответов LiveKit. */
function isNotFound(e: unknown): boolean {
  return typeof e === 'object' && e !== null && (e as { status?: number }).status === 404;
}

/** Любая другая ошибка вызова – LiveKit недоступен или ответил сбоем. */
function unavailable(e: unknown): never {
  throw new LiveKitUnavailableError(e instanceof Error ? e.message : 'LiveKit недоступен');
}

export function createLiveKitGateway(
  wsUrl = process.env.LIVEKIT_URL ?? 'ws://127.0.0.1:7880',
): LiveKitGateway {
  const rooms = new RoomServiceClient(wsUrl.replace(/^ws/, 'http'), API_KEY, API_SECRET);

  return {
    url: wsUrl,

    async createToken({ room, identity, name, attributes }) {
      const token = new AccessToken(API_KEY, API_SECRET, {
        identity,
        name,
        ttl: '6h',
        attributes,
      });
      token.addGrant({
        room,
        roomJoin: true,
        canPublish: true,
        canSubscribe: true,
        canPublishData: true,
        canUpdateOwnMetadata: false,
        canPublishSources: SOURCES,
      });
      return token.toJwt();
    },

    async ensureRoom(room) {
      try {
        await rooms.createRoom({
          name: room,
          emptyTimeout: 300,
          departureTimeout: 20,
          maxParticipants: 11,
        });
      } catch (e) {
        unavailable(e);
      }
    },

    async listOnline(room) {
      try {
        const list = await rooms.listParticipants(room);
        return list.map((p) => p.identity);
      } catch (e) {
        return isNotFound(e) ? [] : null;
      }
    },

    async updateAttributes(room, identity, attributes) {
      try {
        await rooms.updateParticipant(room, identity, { attributes });
        return true;
      } catch {
        // участник еще не подключен к комнате или LiveKit недоступен: атрибут возьмется из токена при входе
        return false;
      }
    },

    async mute(room, identity, kind) {
      try {
        const participant = await rooms.getParticipant(room, identity);
        const wanted = kind === 'audio' ? TrackType.AUDIO : TrackType.VIDEO;
        for (const track of participant.tracks) {
          if (track.type === wanted && !track.muted) {
            await rooms.mutePublishedTrack(room, identity, track.sid, true);
          }
        }
      } catch (e) {
        if (!isNotFound(e)) unavailable(e);
      }
    },

    async removeParticipant(room, identity) {
      try {
        await rooms.removeParticipant(room, identity);
      } catch (e) {
        if (!isNotFound(e)) unavailable(e);
      }
    },

    async deleteRoom(room) {
      try {
        await rooms.deleteRoom(room);
      } catch {
        // встреча уже завершена на нашей стороне, остатки комнаты LiveKit уберет сам по таймауту
      }
    },
  };
}
