import { describe, expect, it } from "vitest";
import { makeAnchor, resolveAnchor } from "./anchor";

const TEXT =
  "Введение.\nМы изучаем совместную правку текста в реальном времени.\nЗаключение.\n";
const QUOTE = "совместную правку";
const from = TEXT.indexOf(QUOTE);
const anchor = makeAnchor(TEXT, from, from + QUOTE.length);

describe("makeAnchor", () => {
  it("keeps the quote with context and a position hint", () => {
    expect(anchor.quote).toBe(QUOTE);
    expect(anchor.prefix.endsWith("изучаем ")).toBe(true);
    expect(anchor.suffix.startsWith(" текста")).toBe(true);
    expect([anchor.start, anchor.end]).toEqual([from, from + QUOTE.length]);
  });
});

describe("resolveAnchor", () => {
  it("is ok when the text did not change", () => {
    expect(resolveAnchor(TEXT, anchor)).toEqual({
      state: "ok",
      from,
      to: from + QUOTE.length,
    });
  });

  it("follows the fragment when text is inserted before it", () => {
    const edited = "Новый абзац перед всем.\n" + TEXT;
    const shift = "Новый абзац перед всем.\n".length;
    expect(resolveAnchor(edited, anchor)).toEqual({
      state: "moved",
      from: from + shift,
      to: from + shift + QUOTE.length,
    });
  });

  it("picks the occurrence whose context matches among duplicates", () => {
    const text = `${QUOTE} раз.\n${TEXT}${QUOTE} три.`;
    const resolved = resolveAnchor(text, anchor);
    expect(resolved.state).toBe("moved");
    expect(text.slice(resolved.from ?? 0, resolved.to ?? 0)).toBe(QUOTE);
    expect(text.slice((resolved.from ?? 0) - 8, resolved.from ?? 0)).toBe(
      "изучаем ",
    );
  });

  it("recovers a fragment edited inside by its surrounding context", () => {
    const edited = TEXT.replace(
      "совместную правку",
      "совместную онлайн-правку",
    );
    const resolved = resolveAnchor(edited, anchor);
    expect(resolved.state).toBe("edited");
    expect(edited.slice(resolved.from ?? 0, resolved.to ?? 0)).toBe(
      "совместную онлайн-правку",
    );
  });

  it("is lost when both the fragment and its context are gone", () => {
    expect(resolveAnchor("Совсем другой документ.", anchor)).toEqual({
      state: "lost",
      from: null,
      to: null,
    });
  });

  it("works for a fragment at the very start and end of the file", () => {
    const start = makeAnchor(TEXT, 0, 9);
    const end = makeAnchor(TEXT, TEXT.length - 12, TEXT.length);
    expect(resolveAnchor(TEXT, start).state).toBe("ok");
    expect(resolveAnchor("Preface\n" + TEXT, end).state).toBe("moved");
  });

  it("ignores an empty quote", () => {
    expect(resolveAnchor(TEXT, { ...anchor, quote: "" }).state).toBe("lost");
  });
});
