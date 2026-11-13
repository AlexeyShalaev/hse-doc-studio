import { describe, expect, it } from "vitest";
import type { PlacementResponse } from "@shared/api/types";
import { newDateMark } from "./dateMarkEdit";

// Новая метка даты (docs/design/signing-route.md, 14.2): под рамкой подписи и внутри листа A4.
const placement = (x_mm: number, y_mm: number): PlacementResponse => ({
  enabled: true,
  page: 1,
  x_mm,
  y_mm,
  width_mm: 40,
  sign_date: null,
  dates: [],
  signed_at: null,
});

describe("newDateMark", () => {
  it("встаёт под рамкой подписи на её странице", () => {
    expect(newDateMark(placement(60, 230), 1, 20)).toMatchObject({
      page: 1,
      x_mm: 60,
      y_mm: 252,
      width_mm: 28,
      height_mm: 6,
      format: "date_numeric",
    });
  });

  it("подпись у правого и нижнего края: рамка остаётся на листе", () => {
    const mark = newDateMark(placement(190, 280), 1, 20);
    expect(mark.x_mm + mark.width_mm).toBeLessThanOrEqual(210);
    expect(mark.y_mm + mark.height_mm).toBeLessThanOrEqual(297);
  });

  it("на другой странице: середина листа", () => {
    expect(newDateMark(placement(60, 230), 2, 20)).toMatchObject({
      page: 2,
      x_mm: 90,
      y_mm: 140,
    });
  });
});
