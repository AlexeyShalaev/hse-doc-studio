import { describe, expect, it } from "vitest";
import { FRAME_LABEL_LINE_HEIGHT, fitFrameLabel } from "./frameLabel";

const LABEL = "Академический руководитель";

/** Строки помещаются по высоте рамки: ни одна не наезжает на другую. */
const fitsHeight = (heightPx: number, fit: { fontPx: number; lines: number }) =>
  fit.lines * fit.fontPx * FRAME_LABEL_LINE_HEIGHT <= heightPx - 4 ||
  fit.lines === 1;

describe("fitFrameLabel", () => {
  it("широкая рамка: одна строка обычным кеглем", () => {
    expect(fitFrameLabel(LABEL, 400, 40)).toEqual({ fontPx: 10, lines: 1 });
  });

  it("узкая рамка: перенос по словам, не наложение", () => {
    // Случай с прода: «АКАДЕМИЧЕСКИЙ» и «РУКОВОДИТЕЛЬ» рисовались друг на друге.
    const fit = fitFrameLabel(LABEL, 110, 40);
    expect(fit.lines).toBe(2);
    expect(fitsHeight(40, fit)).toBe(true);
  });

  it("совсем узкая и низкая рамка: мельче шрифт, затем многоточие", () => {
    const fit = fitFrameLabel(LABEL, 40, 12);
    expect(fit.fontPx).toBe(6);
    expect(fit.lines).toBe(1);
    const tall = fitFrameLabel(LABEL, 60, 30);
    expect(tall.fontPx).toBeLessThan(10);
    expect(fitsHeight(30, tall)).toBe(true);
  });

  it("при любой ширине строки помещаются по высоте", () => {
    for (let width = 10; width <= 400; width += 7)
      for (const height of [8, 14, 22, 40, 80]) {
        const fit = fitFrameLabel(LABEL, width, height);
        expect(fit.lines).toBeGreaterThanOrEqual(1);
        expect(fitsHeight(height, fit)).toBe(true);
      }
  });

  it("пустая подпись не ломает расчёт", () => {
    expect(fitFrameLabel("", 50, 20)).toEqual({ fontPx: 10, lines: 1 });
  });
});
