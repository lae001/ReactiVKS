import { useMediaDeviceSelect } from '@livekit/components-react';
import { Settings } from 'lucide-react';
import { useState } from 'react';

import { DeviceSelect } from '@/features/lobby/DeviceSelect';
import { saveDevicePrefs } from '@/shared/lib/device-prefs';

import { ControlButton } from '../ControlBar';

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

/** Кнопка «Устройства» на панели управления: микрофон, камера и динамик. */
export function DevicesMenu() {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative">
      <ControlButton
        icon={Settings}
        label="Устройства"
        onClick={() => setOpen((v) => !v)}
        pressed={open}
        tone={open ? 'active' : 'default'}
      />
      {open && (
        <div
          role="group"
          aria-label="Выбор устройств"
          className="absolute bottom-14 left-1/2 z-30 flex w-72 -translate-x-1/2 flex-col gap-3 rounded-xl border border-room-border bg-room-surface p-4 text-room-foreground"
        >
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
        </div>
      )}
    </span>
  );
}
