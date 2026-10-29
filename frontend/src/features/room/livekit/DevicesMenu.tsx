import { useMediaDeviceSelect } from '@livekit/components-react';
import { DeviceSelect } from '@/features/lobby/DeviceSelect';
import { saveDevicePrefs } from '@/shared/lib/device-prefs';

type Kind = 'videoinput' | 'audioinput' | 'audiooutput';

const PREF_KEY = { videoinput: 'cameraId', audioinput: 'micId', audiooutput: 'speakerId' } as const;

/** Один список устройств на хуке LiveKit; выбор сразу применяется в комнате и запоминается. */
function KindSelect({ kind, label, emptyText }: { kind: Kind; label: string; emptyText: string }) {
  const { devices, activeDeviceId, setActiveMediaDevice } = useMediaDeviceSelect({ kind });
  const options = devices
    .filter((d) => d.deviceId !== '')
    .map((d, i) => ({ id: d.deviceId, label: d.label || `${label} ${i + 1}` }));
  return (
    <DeviceSelect
      tone="room"
      label={label}
      options={options}
      value={activeDeviceId}
      emptyText={emptyText}
      onChange={(id) => {
        saveDevicePrefs({ [PREF_KEY[kind]]: id });
        void setActiveMediaDevice(id);
      }}
    />
  );
}

/** Выбор динамика возможен только через setSinkId (Chrome, Edge) – в Firefox и Safari его нет. */
function speakerSupported(): boolean {
  return typeof HTMLMediaElement !== 'undefined' && 'setSinkId' in HTMLMediaElement.prototype;
}

/** Содержимое всплывающей панели «Устройства»: микрофон, камера и динамик (кнопка и положение – в `ControlBar`). */
export function DevicesPanel() {
  return (
    <>
      <KindSelect kind="audioinput" label="Микрофон" emptyText="Микрофон не найден" />
      <KindSelect kind="videoinput" label="Камера" emptyText="Камера не найдена" />
      {speakerSupported() ? (
        <KindSelect kind="audiooutput" label="Динамик" emptyText="Динамик по умолчанию" />
      ) : (
        <p className="text-xs text-room-muted">
          Выбрать динамик можно только в Chrome и Edge. В вашем браузере звук идет в динамик,
          выбранный в настройках системы.
        </p>
      )}
    </>
  );
}
