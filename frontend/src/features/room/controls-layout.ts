/**
 * Раскладка нижней панели управления: какие второстепенные кнопки помещаются в строку, а какие уходят в меню «Ещё».
 * Размеры совпадают с классами в `ControlBar.tsx`: кнопки фиксированной ширины, подписи у «Выйти» и «Завершить встречу»
 * показываются с 768 px, у остальных кнопок подписи с 640 px.
 */

export type SecondaryControl = 'participants' | 'devices' | 'analysis' | 'emotions';

/** Порядок важности: при нехватке места в «Ещё» уходят с конца. */
export const SECONDARY_PRIORITY: SecondaryControl[] = [
  'participants',
  'devices',
  'analysis',
  'emotions',
];

const PADDING = 16; // px-2 с обеих сторон
const SM = 640;
const MD = 768;

export const buttonWidth = (width: number) => (width >= SM ? 76 : 44);
export const gapWidth = (width: number) => (width >= SM ? 8 : 4);

/** Ширина «Выйти» и «Завершить встречу»: с подписью с 768 px, иначе только значок. */
export const leaveWidth = (width: number) => (width >= MD ? 108 : 44);
export const endWidth = (width: number) => (width >= MD ? 196 : 44);

export interface ControlsLayoutInput {
  /** Ширина панели управления в CSS-пикселях */
  width: number;
  /** Главные кнопки в строке: микрофон, камера, реакции, чат (сколько из них есть) */
  primary: number;
  /** Какие второстепенные кнопки вообще существуют (без учета места) */
  secondary: SecondaryControl[];
  /** Кнопка «Выйти» и еще одна («Завершить встречу») */
  leaveButtons: 1 | 2;
  /** Вместо «Выйти» одна кнопка шире (мок-комната организатора: «Завершить встречу») */
  wideLeave?: boolean;
}

export interface ControlsLayout {
  /** Второстепенные кнопки, которые остаются в строке */
  inline: SecondaryControl[];
  /** Те, что уходят в меню «Ещё»; если список не пуст, в строке появляется и кнопка «Ещё» */
  more: SecondaryControl[];
}

/**
 * Главные кнопки и выход всегда в строке. Второстепенные – если места хватает; иначе часть из них (с конца
 * списка важности) уходит в «Ещё», и место под саму кнопку «Ещё» резервируется.
 */
export function layoutControls(input: ControlsLayoutInput): ControlsLayout {
  const { width, primary, leaveButtons, wideLeave } = input;
  const available = input.secondary.slice().sort(byPriority);
  const gap = gapWidth(width);
  const button = buttonWidth(width);
  const leave = wideLeave ? endWidth(width) : leaveWidth(width);
  const fixed =
    PADDING +
    primary * button +
    leave +
    (leaveButtons === 2 ? endWidth(width) : 0) +
    (primary + leaveButtons - 1) * gap;
  const step = button + gap;

  if (fixed + available.length * step <= width) return { inline: available, more: [] };
  const room = Math.max(0, Math.floor((width - fixed - step) / step));
  const count = Math.min(room, available.length - 1);
  return { inline: available.slice(0, count), more: available.slice(count) };
}

function byPriority(a: SecondaryControl, b: SecondaryControl) {
  return SECONDARY_PRIORITY.indexOf(a) - SECONDARY_PRIORITY.indexOf(b);
}
