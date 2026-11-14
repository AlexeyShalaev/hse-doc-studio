import { describe, expect, it } from "vitest";
import type { PlacementOrigin, PlaceAnchorState } from "@shared/api/types";
import { anchorNoteOf, placeOnLine } from "./packPlaces";

const placed = (
  origin: PlacementOrigin,
  state: PlaceAnchorState | null,
  enabled = true,
) => ({
  enabled,
  origin,
  preset_available: true,
  source: origin === "manual" ? null : ("anchor" as const),
  anchor: state === null ? null : { id: "supervisor", state },
});

describe("пометка «Место по строке шаблона» (15.17.14)", () => {
  it("только у места как в шаблоне на якоре", () => {
    expect(placeOnLine(placed("pack", "found"))).toBe(true);
    expect(placeOnLine({ ...placed("pack", null), source: "mm" })).toBe(false);
    expect(placeOnLine(placed("manual", "found"))).toBe(false);
    expect(placeOnLine(undefined)).toBe(false);
  });
});

describe("подсказки места на якоре", () => {
  it("строка есть или место пака в мм: подсказки нет", () => {
    expect(anchorNoteOf(placed("pack", "found"))).toBeNull();
    expect(anchorNoteOf(placed("manual", null))).toBeNull();
    expect(anchorNoteOf(undefined)).toBeNull();
  });

  it("строки нет: всегда, и у выключенного, и у ручного места", () => {
    expect(anchorNoteOf(placed("pack", "missing", false))).toBe("missing");
    expect(anchorNoteOf(placed("manual", "missing"))).toBe("missing");
    expect(anchorNoteOf(placed("manual", "missing"), { ownPdf: true })).toBe(
      "missing",
    );
  });

  it("свой PDF: строк шаблона нет, запасное место не применяется", () => {
    expect(
      anchorNoteOf(placed("pack", "unknown"), {
        ownPdf: true,
        hasMmPlace: true,
      }),
    ).toBe("own_pdf");
  });

  it("якоря неизвестны: подсказка, пока места нет или оно изменено, и только без запасного места", () => {
    expect(anchorNoteOf(placed("seed", "unknown", false))).toBe("unknown");
    expect(anchorNoteOf(placed("manual", "unknown"))).toBe("unknown");
    expect(anchorNoteOf(placed("pack", "unknown"))).toBeNull();
    expect(
      anchorNoteOf(placed("manual", "unknown"), { hasMmPlace: true }),
    ).toBeNull();
  });
});
