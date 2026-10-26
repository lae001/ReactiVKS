import {
  Activity,
  type LucideIcon,
  LogOut,
  MessageSquare,
  Mic,
  MicOff,
  PhoneOff,
  ScanFace,
  Users,
  Video,
  VideoOff,
} from 'lucide-react';

import type { ConsentState } from '@/shared/api/types';
import { cn } from '@/shared/lib/utils';

import type { SidePanelTab } from './types';

function ControlButton({
  icon: Icon,
  label,
  caption = label,
  onClick,
  pressed,
  tone = 'default',
}: {
  icon: LucideIcon;
  /** Постоянное доступное имя; состояние передает aria-pressed */
  label: string;
  /** Подпись под иконкой, может отражать состояние */
  caption?: string;
  onClick: () => void;
  pressed?: boolean;
  tone?: 'default' | 'off' | 'active';
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={pressed}
      aria-label={label}
      title={label}
      className={cn(
        'flex h-12 min-w-10 shrink-0 flex-col items-center justify-center gap-0.5 rounded-lg px-2 text-room-foreground transition-colors hover:bg-room-border sm:min-w-16',
        tone === 'off' && 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        tone === 'active' && 'bg-room-border',
      )}
    >
      <Icon className="size-5" aria-hidden />
      <span className="hidden text-[11px] leading-none sm:block" aria-hidden>
        {caption}
      </span>
    </button>
  );
}

/** Нижняя панель управления комнатой: устройства и согласие по центру, панели и выход справа. */
export function ControlBar({
  isOrganizer,
  analysisEnabled,
  micOn,
  cameraOn,
  consent,
  panel,
  onToggleMic,
  onToggleCamera,
  onToggleConsent,
  onTogglePanel,
  onLeave,
}: {
  isOrganizer: boolean;
  analysisEnabled: boolean;
  micOn: boolean;
  cameraOn: boolean;
  consent: ConsentState;
  panel: SidePanelTab | null;
  onToggleMic: () => void;
  onToggleCamera: () => void;
  onToggleConsent: () => void;
  onTogglePanel: (tab: SidePanelTab) => void;
  onLeave: () => void;
}) {
  const analyzed = consent === 'granted';

  return (
    <footer
      aria-label="Управление встречей"
      className="flex shrink-0 items-center justify-center-safe gap-1 overflow-x-auto border-t border-room-border px-2 py-2 sm:gap-2"
    >
      <ControlButton
        icon={micOn ? Mic : MicOff}
        label="Микрофон"
        caption={micOn ? 'Микрофон' : 'Микр. выкл.'}
        onClick={onToggleMic}
        pressed={micOn}
        tone={micOn ? 'default' : 'off'}
      />
      <ControlButton
        icon={cameraOn ? Video : VideoOff}
        label="Камера"
        caption={cameraOn ? 'Камера' : 'Камера выкл.'}
        onClick={onToggleCamera}
        pressed={cameraOn}
        tone={cameraOn ? 'default' : 'off'}
      />
      {analysisEnabled && (
        <ControlButton
          icon={ScanFace}
          label="Анализ моих эмоций"
          caption={analyzed ? 'Анализ вкл.' : 'Анализ выкл.'}
          onClick={onToggleConsent}
          pressed={analyzed}
          tone={analyzed ? 'active' : 'default'}
        />
      )}

      <span className="mx-1 h-8 w-px bg-room-border sm:mx-2" aria-hidden />

      <ControlButton
        icon={Users}
        label="Участники"
        onClick={() => onTogglePanel('participants')}
        pressed={panel === 'participants'}
        tone={panel === 'participants' ? 'active' : 'default'}
      />
      {isOrganizer && analysisEnabled && (
        <ControlButton
          icon={Activity}
          label="Эмоции"
          onClick={() => onTogglePanel('emotions')}
          pressed={panel === 'emotions'}
          tone={panel === 'emotions' ? 'active' : 'default'}
        />
      )}
      <ControlButton
        icon={MessageSquare}
        label="Чат"
        onClick={() => onTogglePanel('chat')}
        pressed={panel === 'chat'}
        tone={panel === 'chat' ? 'active' : 'default'}
      />

      <button
        type="button"
        onClick={onLeave}
        className="ml-1 flex h-12 shrink-0 items-center gap-2 rounded-lg bg-destructive px-3 text-sm font-medium text-destructive-foreground transition-colors hover:bg-destructive/90 sm:ml-2 sm:px-4"
      >
        {isOrganizer ? (
          <PhoneOff className="size-5" aria-hidden />
        ) : (
          <LogOut className="size-5" aria-hidden />
        )}
        <span className="sr-only md:not-sr-only">
          {isOrganizer ? 'Завершить встречу' : 'Выйти'}
        </span>
      </button>
    </footer>
  );
}
