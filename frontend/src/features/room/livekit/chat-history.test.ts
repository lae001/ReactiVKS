import {
  chooseResponder,
  createRequestLimiter,
  encodeHistory,
  encodeRequest,
  loadChat,
  MAX_CHUNK_BYTES,
  MAX_HISTORY_MESSAGES,
  MAX_STORED_MESSAGES,
  MAX_TEXT_LENGTH,
  mergeMessages,
  parseSync,
  REQUEST_INTERVAL_MS,
  saveChat,
  type StoredMessage,
  validateMessage,
} from './chat-history';
import { roomKey } from './room-state';

const NOW = Date.parse('2026-10-29T10:00:00Z');
const msg = (n: number, extra: Partial<StoredMessage> = {}): StoredMessage => ({
  id: `m${n}`,
  from: 'p_a',
  name: 'Анна',
  text: `сообщение ${n}`,
  at: NOW - 1000 * (100 - n),
  ...extra,
});
const bytes = (value: unknown) => new TextEncoder().encode(JSON.stringify(value));

describe('проверка сообщения', () => {
  it('годное сообщение проходит как есть', () => {
    expect(validateMessage(msg(1), NOW)).toEqual(msg(1));
  });

  it.each([
    ['не объект', 'текст'],
    ['пустой id', { ...msg(1), id: '' }],
    ['длинный id', { ...msg(1), id: 'x'.repeat(200) }],
    ['нет отправителя', { ...msg(1), from: '' }],
    ['имя не строка', { ...msg(1), name: 5 }],
    ['слишком длинное имя', { ...msg(1), name: 'я'.repeat(101) }],
    ['пустой текст', { ...msg(1), text: '' }],
    ['текст длиннее 2000', { ...msg(1), text: 'я'.repeat(MAX_TEXT_LENGTH + 1) }],
    ['время не число', { ...msg(1), at: '1' }],
    ['время NaN', { ...msg(1), at: Number.NaN }],
    ['время из далекого будущего', { ...msg(1), at: NOW + 3_600_000 }],
  ])('отбрасывается: %s', (_name, value) => {
    expect(validateMessage(value, NOW)).toBeNull();
  });

  it('текст ровно 2000 символов допустим', () => {
    expect(validateMessage(msg(1, { text: 'я'.repeat(MAX_TEXT_LENGTH) }), NOW)).not.toBeNull();
  });
});

describe('объединение', () => {
  it('дедупликация по id и сортировка по времени', () => {
    const merged = mergeMessages(
      [msg(3), msg(1)],
      [msg(2), msg(3, { text: 'подделка' })],
      [msg(1)],
    );
    expect(merged.map((m) => m.id)).toEqual(['m1', 'm2', 'm3']);
    expect(merged.find((m) => m.id === 'm3')?.text).toBe('сообщение 3'); // первое побеждает
  });

  it(`не больше ${MAX_STORED_MESSAGES} последних`, () => {
    const many = Array.from({ length: 300 }, (_, i) => msg(i, { at: NOW - 400_000 + i * 1000 }));
    const merged = mergeMessages(many);
    expect(merged).toHaveLength(MAX_STORED_MESSAGES);
    expect(merged.at(-1)?.id).toBe('m299');
  });
});

describe('хранилище вкладки', () => {
  beforeEach(() => sessionStorage.clear());

  it('сохраняется и читается после «обновления», битые записи отбрасываются', () => {
    saveChat('m-1', [msg(1), msg(2)]);
    expect(loadChat('m-1').map((m) => m.id)).toEqual(['m1', 'm2']);
    expect(loadChat('m-2')).toEqual([]);

    sessionStorage.setItem(
      roomKey.chat('m-1'),
      JSON.stringify([msg(1), { id: 'плохое' }, 5, null]),
    );
    expect(loadChat('m-1').map((m) => m.id)).toEqual(['m1']);
    sessionStorage.setItem(roomKey.chat('m-1'), 'не json');
    expect(loadChat('m-1')).toEqual([]);
  });
});

describe('ответ с историей', () => {
  it(`до ${MAX_HISTORY_MESSAGES} последних сообщений, части не больше ${MAX_CHUNK_BYTES} байт`, () => {
    const many = Array.from({ length: 120 }, (_, i) =>
      msg(i, { text: 'ж'.repeat(1900), at: NOW - 500_000 + i * 1000 }),
    );
    const chunks = encodeHistory(many);
    expect(chunks.length).toBeGreaterThan(1);
    const ids: string[] = [];
    chunks.forEach((chunk, index) => {
      expect(chunk.byteLength).toBeLessThanOrEqual(MAX_CHUNK_BYTES);
      const parsed = parseSync(chunk, NOW);
      expect(parsed).toMatchObject({ type: 'history', part: index + 1, parts: chunks.length });
      if (parsed?.type === 'history') ids.push(...parsed.messages.map((m) => m.id));
    });
    expect(ids).toHaveLength(MAX_HISTORY_MESSAGES);
    expect(ids.at(-1)).toBe('m119');
    expect(ids[0]).toBe('m70');
  });

  it('короткая история – одна часть; пустая – ни одной', () => {
    expect(encodeHistory([msg(1), msg(2)])).toHaveLength(1);
    expect(encodeHistory([])).toEqual([]);
  });
});

describe('разбор чужих данных', () => {
  it('запрос истории', () => {
    expect(parseSync(encodeRequest(), NOW)).toEqual({ v: 1, type: 'history_request' });
  });

  it.each([
    ['мусор', new TextEncoder().encode('не json')],
    ['пусто', new Uint8Array()],
    ['чужая версия', bytes({ v: 2, type: 'history_request' })],
    ['неизвестный тип', bytes({ v: 1, type: 'delete_all' })],
    ['история без частей', bytes({ v: 1, type: 'history', messages: [] })],
    [
      'часть больше общего числа',
      bytes({ v: 1, type: 'history', part: 3, parts: 2, messages: [] }),
    ],
    ['слишком много частей', bytes({ v: 1, type: 'history', part: 1, parts: 99, messages: [] })],
    ['messages не массив', bytes({ v: 1, type: 'history', part: 1, parts: 1, messages: 'x' })],
    [
      'больше 50 сообщений',
      bytes({
        v: 1,
        type: 'history',
        part: 1,
        parts: 1,
        messages: Array.from({ length: MAX_HISTORY_MESSAGES + 1 }, (_, i) => msg(i)),
      }),
    ],
    [
      'огромное тело',
      new TextEncoder().encode(`{"v":1,"type":"history_request","x":"${'x'.repeat(20_000)}"}`),
    ],
  ])('отбрасывается: %s', (_name, payload) => {
    expect(parseSync(payload, NOW)).toBeNull();
  });

  it('негодные сообщения внутри истории выбрасываются по одному, остальные принимаются', () => {
    const parsed = parseSync(
      bytes({
        v: 1,
        type: 'history',
        part: 1,
        parts: 1,
        messages: [
          msg(1),
          { ...msg(2), text: 'я'.repeat(5000) },
          { id: 'x' },
          msg(3, { at: NOW + 9e9 }),
        ],
      }),
      NOW,
    );
    expect(parsed).toMatchObject({ type: 'history' });
    expect(parsed?.type === 'history' && parsed.messages.map((m) => m.id)).toEqual(['m1']);
  });
});

describe('кто отвечает и лимит запросов', () => {
  it('отвечает наименьшая identity среди остальных, запросивший не в счет', () => {
    expect(chooseResponder(['p_c', 'p_a', 'p_b'], 'p_c')).toBe('p_a');
    expect(chooseResponder(['p_c', 'p_a', 'p_b'], 'p_a')).toBe('p_b');
    expect(chooseResponder(['p_a'], 'p_a')).toBeNull();
    expect(chooseResponder([], 'p_a')).toBeNull();
  });

  it('запрос – не чаще одного в 5 секунд от одного участника', () => {
    const allow = createRequestLimiter();
    expect(allow('p_a', 0)).toBe(true);
    expect(allow('p_a', REQUEST_INTERVAL_MS - 1)).toBe(false);
    expect(allow('p_b', 10)).toBe(true);
    expect(allow('p_a', REQUEST_INTERVAL_MS)).toBe(true);
  });
});
