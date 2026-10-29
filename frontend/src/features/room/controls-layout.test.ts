import {
  buttonWidth,
  endWidth,
  gapWidth,
  layoutControls,
  leaveWidth,
  type SecondaryControl,
} from './controls-layout';

const ALL: SecondaryControl[] = ['participants', 'devices', 'analysis', 'emotions'];
const GUEST: SecondaryControl[] = ['participants', 'devices', 'analysis'];
const WIDTHS = [360, 768, 960, 1024, 1280, 1920];

/** Сколько места занимает строка при данной раскладке – считается независимо от `layoutControls`. */
function usedWidth(width: number, inline: number, more: boolean, org: boolean) {
  const items = 4 + inline + (more ? 1 : 0) + (org ? 2 : 1);
  return (
    16 +
    (4 + inline + (more ? 1 : 0)) * buttonWidth(width) +
    leaveWidth(width) +
    (org ? endWidth(width) : 0) +
    (items - 1) * gapWidth(width)
  );
}

describe('раскладка нижней панели: что остается в строке, что уходит в «Ещё»', () => {
  it.each(WIDTHS)('при ширине %i px ничего не выходит за окно (организатор и гость)', (width) => {
    for (const org of [true, false]) {
      const layout = layoutControls({
        width,
        primary: 4,
        secondary: org ? ALL : GUEST,
        leaveButtons: org ? 2 : 1,
      });
      const used = usedWidth(width, layout.inline.length, layout.more.length > 0, org);
      expect(
        used,
        `${org ? 'организатор' : 'гость'}: ${JSON.stringify(layout)}`,
      ).toBeLessThanOrEqual(width);
      // всё, что есть, либо в строке, либо в «Ещё»
      expect([...layout.inline, ...layout.more].sort()).toEqual((org ? ALL : GUEST).slice().sort());
    }
  });

  it('360 px: всё второстепенное в «Ещё»; 960 px: «Ещё» есть, главные кнопки на месте; 1280 px: «Ещё» не нужно', () => {
    const at = (width: number) =>
      layoutControls({ width, primary: 4, secondary: ALL, leaveButtons: 2 });
    expect(at(360)).toEqual({ inline: [], more: ALL });
    expect(at(960)).toEqual({
      inline: ['participants', 'devices'],
      more: ['analysis', 'emotions'],
    });
    expect(at(1280)).toEqual({ inline: ALL, more: [] });
    expect(at(1920).more).toEqual([]);
  });

  it('в «Ещё» уходят с конца списка важности: сначала эмоции и анализ, участники – последними', () => {
    for (let width = 360; width <= 1100; width += 20) {
      const { inline, more } = layoutControls({
        width,
        primary: 4,
        secondary: ALL,
        leaveButtons: 2,
      });
      expect([...inline, ...more]).toEqual(ALL); // порядок важности сохраняется
    }
  });

  it('место под саму кнопку «Ещё» резервируется: при нехватке места на один пункт в «Ещё» уходит ровно он', () => {
    const wide = layoutControls({ width: 980, primary: 4, secondary: ALL, leaveButtons: 2 });
    expect(wide.more.length).toBeGreaterThan(0);
    expect(usedWidth(980, wide.inline.length, true, true)).toBeLessThanOrEqual(980);
  });

  it('без реакций и чата (мок-комната) главных кнопок меньше – помещается больше', () => {
    const full = layoutControls({ width: 960, primary: 4, secondary: ALL, leaveButtons: 2 });
    const small = layoutControls({ width: 960, primary: 2, secondary: ALL, leaveButtons: 1 });
    expect(small.inline.length).toBeGreaterThan(full.inline.length);
  });
});
