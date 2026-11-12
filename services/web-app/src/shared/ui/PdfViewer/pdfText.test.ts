import { describe, expect, it } from "vitest";
import { foldText, locateText, type PageTextItem } from "./pdfText";

const line = (str: string, y: number, x = 72): PageTextItem => ({
  str,
  x,
  y,
  width: str.length * 6,
  height: 12,
});

describe("foldText", () => {
  it("оставляет буквы и цифры без регистра, диакритики и лигатур", () => {
    expect(foldText("Эффективный «ﬂow» — Ёлка, иссле-\nдование 7.32")).toBe(
      "эффективныиflowелкаисследование732",
    );
  });
});

describe("locateText", () => {
  const items = [
    line("Введение в задачу.", 100),
    line("Мы изучаем совмест-", 120),
    line("ную правку текста.", 134),
    line("Ещё раз совместную правку", 400),
  ];

  it("находит фрагмент через перенос и даёт прямоугольник на каждую строку", () => {
    const rects = locateText(items, "совместную правку", 125);

    expect(rects).toHaveLength(2);
    expect(rects?.[0]?.y).toBe(120);
    expect(rects?.[1]?.y).toBe(134);
    // Начало фрагмента внутри строки: «Мы изучаем » (11 знаков) по 6 пт.
    expect(rects?.[0]?.x).toBeCloseTo(72 + 11 * 6);
  });

  it("из двух вхождений берёт ближайшее к подсказке", () => {
    expect(locateText(items, "совместную правку", 390)?.[0]?.y).toBe(400);
  });

  it("не ищет слишком короткое и отсутствующее", () => {
    expect(locateText(items, "Мы", 120)).toBeNull();
    expect(locateText(items, "заключение работы", 120)).toBeNull();
  });
});
