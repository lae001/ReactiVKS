import {
  Activity,
  Ellipsis,
  type LucideIcon,
  LogOut,
  MessageSquare,
  Mic,
  MicOff,
  PhoneOff,
  ScanFace,
  Settings,
  Smile,
  Users,
  Video,
  VideoOff,
} from 'lucide-react';
import { type ReactNode, useEffect, useRef, useState } from 'react';

import type { ConsentState } from '@/shared/api/types';
import { cn } from '@/shared/lib/utils';

import { layoutControls, type SecondaryControl } from './controls-layout';
import { unreadBadge } from './livekit/chat-notifications';
import { ReactionsPanel } from './livekit/ReactionsMenu';
import { secondsLeft, useNow } from './use-countdown';
import type { SidePanelTab } from './types';

type Popup = 'devices' | 'reactions' | 'more';

export function ControlButton({
  icon: Icon,
  label,
  caption = label,
  onClick,
  pressed,
  tone = 'default',
  badge,
  popup,
  disabled,
  title,
  trigger,
}: {
  icon: LucideIcon;
  /** Постоянное доступное имя; состояние передает aria-pressed */
  label: string;
  /** Подпись под иконкой, может отражать состояние */
  caption?: string;
  onClick: () => void;
  pressed?: boolean;
  tone?: 'default' | 'off' | 'active';
  /** Счетчик на кнопке (непрочитанные сообщения), например «3» или «9+» */
  badge?: string;
  /** Кнопка открывает всплывающую панель: aria-haspopup */
  popup?: boolean;
  /** Неактивна, но остается в порядке обхода (aria-disabled) */
  disabled?: boolean;
  title?: string;
  /** Какую всплывающую панель открывает кнопка: по этому имени фокус возвращается после Esc */
  trigger?: Popup;
}) {
  return (
    <button
      type="button"
      onClick={disabled ? undefined : onClick}
      aria-pressed={pressed}
      aria-haspopup={popup ? 'true' : undefined}
      aria-disabled={disabled || undefined}
      aria-label={label}
      title={title ?? label}
      data-popup={popup ? '' : undefined}
      data-trigger={trigger}
      // фиксированная ширина: по ней `controls-layout.ts` считает, что помещается в строку
      className={cn(
        'relative flex h-12 w-11 shrink-0 flex-col items-center justify-center gap-0.5 rounded-lg px-1 text-room-foreground transition-colors hover:bg-room-border sm:w-[76px]',
        tone === 'off' && 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        tone === 'active' && 'bg-room-border',
        disabled && 'opacity-60 hover:bg-transparent',
      )}
    >
      <Icon className="size-5" aria-hidden />
      {badge && (
        <span
          aria-hidden
          className="absolute -top-1 -right-1 grid min-w-5 place-items-center rounded-full bg-primary px-1 text-[11px] leading-5 font-semibold text-primary-foreground"
        >
          {badge}
        </span>
      )}
      <span className="hidden max-w-full truncate text-[11px] leading-none sm:block" aria-hidden>
        {caption}
      </span>
    </button>
  );
}

/** Всплывающая панель над панелью управления: fixed по центру окна, чтобы ее ничто не обрезало. */
function PopupPanel({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div
      role="group"
      aria-label={label}
      data-popup=""
      className="fixed bottom-20 left-1/2 z-30 flex w-max max-w-[calc(100vw-1rem)] -translate-x-1/2 flex-col gap-3 rounded-xl border border-room-border bg-room-surface p-3 text-room-foreground"
    >
      {children}
    </div>
  );
}

/**
 * Ширина окна в CSS-пикселях. Панель управления занимает окно целиком, а подписи кнопок включаются media-запросами
 * по ширине окна, поэтому и раскладка считается по ней (а не по размеру самого элемента).
 */
function useViewportWidth(): number {
  const [width, setWidth] = useState(() =>
    typeof window === 'undefined' ? 1280 : window.innerWidth,
  );
  useEffect(() => {
    const update = () => setWidth(window.innerWidth);
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);
  return width;
}

/** Нижняя панель управления: главные кнопки всегда в строке, второстепенные – если хватает места, иначе в «Ещё». */
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
  devicesPanel,
  reactions,
  onEnd,
  showChat = true,
  unreadChat = 0,
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
  /** Содержимое панели «Устройства» (комната на LiveKit); без него кнопки «Устройства» нет */
  devicesPanel?: ReactNode;
  /** Реакции (комната на LiveKit); без них кнопки «Реакции» нет */
  reactions?: {
    onPick: (emoji: string) => void;
    /** Когда снова можно отправить реакцию (`Date.now()`); 0 – можно сейчас */
    blockedUntil: number;
    /** Исчерпан лимит «пять за 10 секунд»: «Слишком часто. Подождите N с» */
    tooFrequent: boolean;
  };
  /** Если задано, «Выйти» и «Завершить встречу» – две разные кнопки (организатор в комнате на LiveKit) */
  onEnd?: () => void;
  showChat?: boolean;
  /** Непрочитанные сообщения чата: бейдж на кнопке «Чат» */
  unreadChat?: number;
}) {
  const analyzed = consent === 'granted';
  const footer = useRef<HTMLElement>(null);
  const width = useViewportWidth();
  const [popup, setPopup] = useState<Popup | null>(null);

  // Одновременно открыта одна панель: Esc и клик вне ее закрывают, фокус возвращается на кнопку-открывалку
  useEffect(() => {
    if (!popup) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.stopPropagation();
      setPopup(null);
      footer.current?.querySelector<HTMLElement>(`[data-trigger="${popup}"]`)?.focus();
    };
    const onPointer = (event: PointerEvent) => {
      if (!(event.target as Element | null)?.closest('[data-popup]')) setPopup(null);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onPointer);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onPointer);
    };
  }, [popup]);

  const toggle = (next: Popup) => setPopup((current) => (current === next ? null : next));

  const wait = useNow(reactions?.blockedUntil ?? 0);
  const waitSeconds = reactions ? secondsLeft(reactions.blockedUntil, wait) : 0;
  const waitText = reactions?.tooFrequent
    ? `Слишком часто. Подождите ${waitSeconds} с`
    : `Подождите ${waitSeconds} с`;

  const secondary: SecondaryControl[] = [
    'participants',
    ...(devicesPanel ? (['devices'] as const) : []),
    ...(analysisEnabled ? (['analysis'] as const) : []),
    ...(isOrganizer && analysisEnabled ? (['emotions'] as const) : []),
  ];
  const separateEnd = onEnd !== undefined;
  const layout = layoutControls({
    width,
    primary: 2 + (reactions ? 1 : 0) + (showChat ? 1 : 0),
    secondary,
    leaveButtons: separateEnd ? 2 : 1,
    wideLeave: isOrganizer && !separateEnd,
  });

  const items: Record<
    SecondaryControl,
    {
      icon: LucideIcon;
      label: string;
      caption?: string;
      pressed: boolean;
      active: boolean;
      run: () => void;
    }
  > = {
    participants: {
      icon: Users,
      label: 'Участники',
      pressed: panel === 'participants',
      active: panel === 'participants',
      run: () => onTogglePanel('participants'),
    },
    devices: {
      icon: Settings,
      label: 'Устройства',
      pressed: popup === 'devices',
      active: popup === 'devices',
      run: () => setPopup('devices'),
    },
    analysis: {
      icon: ScanFace,
      label: 'Анализ моих эмоций',
      caption: analyzed ? 'Анализ вкл.' : 'Анализ выкл.',
      pressed: analyzed,
      active: analyzed,
      run: onToggleConsent,
    },
    emotions: {
      icon: Activity,
      label: 'Эмоции',
      pressed: panel === 'emotions',
      active: panel === 'emotions',
      run: () => onTogglePanel('emotions'),
    },
  };
  const secondaryButton = (id: SecondaryControl) => {
    const item = items[id];
    return (
      <ControlButton
        key={id}
        icon={item.icon}
        label={item.label}
        caption={item.caption}
        onClick={id === 'devices' ? () => toggle('devices') : item.run}
        pressed={item.pressed}
        popup={id === 'devices'}
        trigger={id === 'devices' ? 'devices' : undefined}
        tone={item.active ? 'active' : 'default'}
      />
    );
  };
  const inline = (id: SecondaryControl) => layout.inline.includes(id);

  return (
    <footer
      ref={footer}
      aria-label="Управление встречей"
      className="flex shrink-0 items-center justify-center gap-1 border-t border-room-border px-2 py-2 sm:gap-2"
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
        caption={cameraOn ? 'Камера' : 'Кам. выкл.'}
        onClick={onToggleCamera}
        pressed={cameraOn}
        tone={cameraOn ? 'default' : 'off'}
      />
      {inline('devices') && secondaryButton('devices')}
      {reactions && (
        <>
          <ControlButton
            icon={Smile}
            label={waitSeconds > 0 ? `Реакции. ${waitText}` : 'Реакции'}
            title={waitSeconds > 0 ? waitText : 'Реакции'}
            caption={waitSeconds > 0 ? `${waitSeconds} с` : 'Реакции'}
            onClick={() => toggle('reactions')}
            pressed={popup === 'reactions'}
            tone={popup === 'reactions' ? 'active' : 'default'}
            popup
            trigger="reactions"
            disabled={waitSeconds > 0}
          />
          {/* объявление для скринридера: полный текст, даже когда на кнопке короткое «N с» */}
          <span className="sr-only" aria-live="polite">
            {waitSeconds > 0 ? waitText : ''}
          </span>
        </>
      )}
      {inline('analysis') && secondaryButton('analysis')}
      {inline('participants') && secondaryButton('participants')}
      {inline('emotions') && secondaryButton('emotions')}
      {showChat && (
        <ControlButton
          icon={MessageSquare}
          label={unreadChat > 0 ? `Чат, непрочитанных: ${unreadChat}` : 'Чат'}
          caption="Чат"
          badge={unreadChat > 0 ? unreadBadge(unreadChat) : undefined}
          onClick={() => onTogglePanel('chat')}
          pressed={panel === 'chat'}
          tone={panel === 'chat' ? 'active' : 'default'}
        />
      )}
      {layout.more.length > 0 && (
        <ControlButton
          icon={Ellipsis}
          label="Ещё"
          onClick={() => toggle('more')}
          pressed={popup === 'more'}
          tone={popup === 'more' ? 'active' : 'default'}
          popup
          trigger="more"
        />
      )}

      <button
        type="button"
        onClick={onLeave}
        className={cn(
          'flex h-12 w-11 shrink-0 items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors md:w-auto md:px-4',
          isOrganizer && !separateEnd ? 'md:w-[196px]' : 'md:w-[108px]',
          separateEnd
            ? 'bg-room-surface text-room-foreground hover:bg-room-border'
            : 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        )}
      >
        {isOrganizer && !separateEnd ? (
          <PhoneOff className="size-5" aria-hidden />
        ) : (
          <LogOut className="size-5" aria-hidden />
        )}
        <span className="sr-only md:not-sr-only">
          {isOrganizer && !separateEnd ? 'Завершить встречу' : 'Выйти'}
        </span>
      </button>
      {onEnd && (
        <button
          type="button"
          onClick={onEnd}
          className="flex h-12 w-11 shrink-0 items-center justify-center gap-2 rounded-lg bg-destructive text-sm font-medium text-destructive-foreground transition-colors hover:bg-destructive/90 md:w-[196px] md:px-4"
        >
          <PhoneOff className="size-5" aria-hidden />
          <span className="sr-only md:not-sr-only">Завершить встречу</span>
        </button>
      )}

      {popup === 'devices' && devicesPanel && (
        <PopupPanel label="Выбор устройств">
          <div className="flex w-64 max-w-full flex-col gap-3">{devicesPanel}</div>
        </PopupPanel>
      )}
      {popup === 'reactions' && reactions && (
        <PopupPanel label="Выбор реакции">
          <ReactionsPanel
            blocked={waitSeconds > 0}
            onPick={(emoji) => {
              reactions.onPick(emoji);
              setPopup(null);
            }}
          />
        </PopupPanel>
      )}
      {popup === 'more' && layout.more.length > 0 && (
        <PopupPanel label="Ещё">
          <ul role="menu" className="flex w-60 flex-col gap-1">
            {layout.more.map((id) => {
              const item = items[id];
              const Icon = item.icon;
              return (
                <li key={id} role="none">
                  <button
                    type="button"
                    role="menuitem"
                    aria-pressed={
                      id === 'analysis' || id === 'participants' || id === 'emotions'
                        ? item.pressed
                        : undefined
                    }
                    onClick={() => {
                      // пункт работает как исходная кнопка; панель «Ещё» закрывается (а «Устройства» открываются)
                      setPopup(null);
                      item.run();
                    }}
                    className={cn(
                      'flex h-11 w-full items-center gap-3 rounded-lg px-3 text-left text-sm transition-colors hover:bg-room-border',
                      item.active && 'bg-room-border',
                    )}
                  >
                    <Icon className="size-5 shrink-0" aria-hidden />
                    {id === 'analysis'
                      ? analyzed
                        ? 'Анализ моих эмоций: вкл.'
                        : 'Анализ моих эмоций: выкл.'
                      : item.label}
                  </button>
                </li>
              );
            })}
          </ul>
        </PopupPanel>
      )}
    </footer>
  );
}
