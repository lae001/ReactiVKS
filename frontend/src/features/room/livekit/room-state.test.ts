import { clearRoomState, loadDevices, roomKey, saveDevices } from './room-state';

describe('состояние комнаты во вкладке (sessionStorage)', () => {
  beforeEach(() => sessionStorage.clear());

  it('микрофон и камера: записи нет – null, иначе последнее сохраненное состояние по встрече', () => {
    expect(loadDevices('m-1')).toBeNull();
    saveDevices('m-1', { mic: false, camera: true });
    expect(loadDevices('m-1')).toEqual({ mic: false, camera: true });
    expect(loadDevices('m-2')).toBeNull();
    // ключ вида vks.room.devices.<meetingId>
    expect(sessionStorage.getItem('vks.room.devices.m-1')).toBe('{"mic":false,"camera":true}');
    saveDevices('m-1', { mic: true, camera: true });
    expect(loadDevices('m-1')).toEqual({ mic: true, camera: true });
  });

  it('повреждённая запись игнорируется', () => {
    for (const bad of ['не json', '{"mic":1}', '[]', 'null', '{"mic":true}']) {
      sessionStorage.setItem(roomKey.devices('m-1'), bad);
      expect(loadDevices('m-1')).toBeNull();
    }
  });

  it('очистка убирает всё по этой встрече и не трогает другие', () => {
    saveDevices('m-1', { mic: false, camera: false });
    saveDevices('m-2', { mic: false, camera: false });
    sessionStorage.setItem(roomKey.chat('m-1'), '[]');
    sessionStorage.setItem(roomKey.startedAt('m-1'), '123');
    clearRoomState('m-1');
    expect(sessionStorage.length).toBe(1);
    expect(loadDevices('m-2')).not.toBeNull();
  });

  it('недоступное хранилище не ломает чтение и запись', () => {
    const broken = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(loadDevices('m-1')).toBeNull();
    broken.mockRestore();
    const set = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota');
    });
    expect(() => saveDevices('m-1', { mic: true, camera: true })).not.toThrow();
    set.mockRestore();
  });
});
