import { isAgent, restIdOf, roomParticipants, toRoomParticipant } from './participants';

function person(
  identity: string,
  attributes: Record<string, string> = {},
  extra: Record<string, unknown> = {},
) {
  return {
    identity,
    name: identity.toUpperCase(),
    attributes,
    isLocal: false,
    isMicrophoneEnabled: true,
    isCameraEnabled: true,
    ...extra,
  };
}

describe('участники из LiveKit', () => {
  it('имя из токена, роль и согласие из атрибутов vks.*', () => {
    const p = toRoomParticipant(
      person(
        'p_1',
        { 'vks.role': 'organizer', 'vks.consent': 'granted', 'vks.kind': 'human' },
        {
          name: 'Иван Петров',
          isMicrophoneEnabled: false,
        },
      ),
    );
    expect(p).toEqual({
      id: 'p_1',
      name: 'Иван Петров',
      role: 'organizer',
      isSelf: false,
      consent: 'granted',
      micOn: false,
      cameraOn: true,
    });
  });

  it('без атрибутов: гость, согласие не требуется; неизвестное значение согласия – тоже', () => {
    expect(toRoomParticipant(person('p_2'))).toMatchObject({
      role: 'guest',
      consent: 'not_required',
    });
    expect(toRoomParticipant(person('p_3', { 'vks.consent': 'whatever' }))).toMatchObject({
      consent: 'not_required',
    });
  });

  it('участник без имени подписывается «Участник»', () => {
    expect(toRoomParticipant(person('p_4', {}, { name: '' }))?.name).toBe('Участник');
  });

  it('агент (vks.kind = agent) не попадает в участников', () => {
    const agent = person('agent-1', { 'vks.kind': 'agent' });
    expect(isAgent(agent)).toBe(true);
    expect(toRoomParticipant(agent)).toBeNull();
    expect(roomParticipants([person('p_1'), agent]).map((p) => p.id)).toEqual(['p_1']);
  });

  it('вы – первым, остальные в порядке входа', () => {
    const list = roomParticipants([
      person('p_1'),
      person('p_2', {}, { isLocal: true }),
      person('p_3'),
    ]);
    expect(list.map((p) => p.id)).toEqual(['p_2', 'p_1', 'p_3']);
    expect(list[0]?.isSelf).toBe(true);
  });

  it('id для REST – identity без префикса p_', () => {
    expect(restIdOf('p_0192-abc')).toBe('0192-abc');
    expect(restIdOf('other')).toBe('other');
  });
});
