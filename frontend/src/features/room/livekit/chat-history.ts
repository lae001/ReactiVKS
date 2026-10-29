import { readJson, roomKey, writeJson } from './room-state';

/**
 * История чата без сервера (ADR-008, «Обновление»): каждая вкладка хранит сообщения встречи в `sessionStorage`,
 * а вошедшему участнику их отдает один из тех, кто в комнате, по каналу данных LiveKit. Данные не подписаны:
 * участник теоретически может подделать историю другим, поэтому все входящее валидируется.
 */

/** Тема данных LiveKit для синхронизации истории (docs/api/livekit-integration.md). */
export const CHAT_SYNC_TOPIC = 'vks.chat.sync';

export const MAX_STORED_MESSAGES = 200;
export const MAX_HISTORY_MESSAGES = 50;
export const MAX_TEXT_LENGTH = 2000;
const MAX_NAME_LENGTH = 100;
const MAX_ID_LENGTH = 128;
/** Лимит LiveKit для reliable data ≈ 15 КБ: ответ делится на части не больше ~12 КБ. */
export const MAX_CHUNK_BYTES = 12 * 1024;
/** Входящее сообщение больше этого размера отбрасывается без разбора. */
export const MAX_PAYLOAD_BYTES = 16 * 1024;
/** Запрос истории не чаще одного раза в 5 секунд от одного участника. */
export const REQUEST_INTERVAL_MS = 5000;
/** Ответ отправляется с небольшой случайной задержкой, чтобы дублирующий ответчик мог уступить. */
export const MAX_REPLY_DELAY_MS = 300;
/** Пока участник только что запросил историю, своей у него еще нет: от него историю не принимаем. */
export const REQUESTER_QUIET_MS = 10_000;
/** Сообщение «из будущего» больше чем на минуту – подделка или неверные часы: отбрасывается. */
const MAX_FUTURE_MS = 60_000;

export interface StoredMessage {
  id: string;
  /** identity отправителя в LiveKit */
  from: string;
  name: string;
  text: string;
  /** Время отправки, мс */
  at: number;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

/** Сообщение из неизвестного источника (хранилище, чужой ответ) или `null`, если оно не годится. */
export function validateMessage(value: unknown, now = Date.now()): StoredMessage | null {
  if (!isRecord(value)) return null;
  const { id, from, name, text, at } = value;
  if (typeof id !== 'string' || id === '' || id.length > MAX_ID_LENGTH) return null;
  if (typeof from !== 'string' || from === '' || from.length > MAX_ID_LENGTH) return null;
  if (typeof name !== 'string' || name.length > MAX_NAME_LENGTH) return null;
  if (typeof text !== 'string' || text === '' || text.length > MAX_TEXT_LENGTH) return null;
  if (typeof at !== 'number' || !Number.isFinite(at) || at <= 0 || at > now + MAX_FUTURE_MS) {
    return null;
  }
  return { id, from, name, text, at };
}

/** Объединение без повторов (по id), по времени; не больше `MAX_STORED_MESSAGES` последних. */
export function mergeMessages(...lists: StoredMessage[][]): StoredMessage[] {
  const byId = new Map<string, StoredMessage>();
  for (const list of lists)
    for (const message of list) if (!byId.has(message.id)) byId.set(message.id, message);
  return [...byId.values()]
    .sort((a, b) => a.at - b.at || a.id.localeCompare(b.id))
    .slice(-MAX_STORED_MESSAGES);
}

export function loadChat(meetingId: string): StoredMessage[] {
  const data = readJson(roomKey.chat(meetingId));
  if (!Array.isArray(data)) return [];
  const now = Date.now();
  return mergeMessages(
    data.flatMap((item) => {
      const message = validateMessage(item, now);
      return message ? [message] : [];
    }),
  );
}

export function saveChat(meetingId: string, messages: StoredMessage[]) {
  writeJson(roomKey.chat(meetingId), messages.slice(-MAX_STORED_MESSAGES));
}

// ---------- Протокол синхронизации ----------

export type SyncMessage =
  | { v: 1; type: 'history_request' }
  | { v: 1; type: 'history'; part: number; parts: number; messages: StoredMessage[] };

export function encodeRequest(): Uint8Array {
  return new TextEncoder().encode(JSON.stringify({ v: 1, type: 'history_request' }));
}

const byteLength = (text: string) => new TextEncoder().encode(text).length;

/**
 * Ответ с историей: до 50 последних сообщений, разбитых на части не больше ~12 КБ каждая (лимит LiveKit для
 * reliable data ≈ 15 КБ). Каждая часть самостоятельна: получатель объединяет их по id.
 */
export function encodeHistory(messages: StoredMessage[]): Uint8Array[] {
  const recent = messages.slice(-MAX_HISTORY_MESSAGES);
  const groups: StoredMessage[][] = [];
  let current: StoredMessage[] = [];
  let size = 0;
  for (const message of recent) {
    const length = byteLength(JSON.stringify(message)) + 1;
    // запас на обертку {v, type, part, parts, messages:[]}
    if (current.length > 0 && size + length > MAX_CHUNK_BYTES - 200) {
      groups.push(current);
      current = [];
      size = 0;
    }
    current.push(message);
    size += length;
  }
  if (current.length > 0) groups.push(current);
  return groups.map((group, index) =>
    new TextEncoder().encode(
      JSON.stringify({
        v: 1,
        type: 'history',
        part: index + 1,
        parts: groups.length,
        messages: group,
      }),
    ),
  );
}

/** Разбор входящих данных темы синхронизации: схема, размеры, сообщения. Все лишнее – `null`. */
export function parseSync(payload: Uint8Array, now = Date.now()): SyncMessage | null {
  if (payload.byteLength === 0 || payload.byteLength > MAX_PAYLOAD_BYTES) return null;
  let data: unknown;
  try {
    data = JSON.parse(new TextDecoder().decode(payload));
  } catch {
    return null;
  }
  if (!isRecord(data) || data.v !== 1) return null;
  if (data.type === 'history_request') return { v: 1, type: 'history_request' };
  if (data.type !== 'history') return null;
  const { part, parts, messages } = data;
  if (
    typeof part !== 'number' ||
    typeof parts !== 'number' ||
    !Number.isInteger(part) ||
    !Number.isInteger(parts) ||
    part < 1 ||
    parts < part ||
    parts > 20 ||
    !Array.isArray(messages) ||
    messages.length > MAX_HISTORY_MESSAGES
  ) {
    return null;
  }
  const valid = messages.flatMap((item) => {
    const message = validateMessage(item, now);
    return message ? [message] : [];
  });
  return { v: 1, type: 'history', part, parts, messages: valid };
}

/** Кто отвечает на запрос: наименьшая identity среди участников, кроме запросившего (и агентов). */
export function chooseResponder(identities: string[], requester: string): string | null {
  const candidates = identities.filter((identity) => identity !== requester);
  return candidates.length === 0 ? null : candidates.reduce((a, b) => (a < b ? a : b));
}

/** Не чаще одного запроса истории в 5 секунд от одного участника. */
export function createRequestLimiter() {
  const last = new Map<string, number>();
  return (sender: string, now: number): boolean => {
    const previous = last.get(sender);
    if (previous !== undefined && now - previous < REQUEST_INTERVAL_MS) return false;
    last.set(sender, now);
    return true;
  };
}
