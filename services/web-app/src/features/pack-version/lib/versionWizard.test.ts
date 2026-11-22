import { describe, expect, it } from "vitest";
import type { PackVersionState } from "@entities/pack-studio";
import {
  isSofter,
  itemsOf,
  needsNote,
  notesOf,
  notesParallel,
} from "./versionWizard";

const state = (patch: Partial<PackVersionState>): PackVersionState =>
  ({
    by_number: "patch",
    minimum: "patch",
    suggested: "patch",
    ...patch,
  }) as PackVersionState;

describe("мастер «Новая версия»: помощники", () => {
  it("класс мягче: patch < minor < major", () => {
    expect(isSofter("patch", "minor")).toBe(true);
    expect(isSofter("major", "minor")).toBe(false);
    expect(isSofter("minor", "minor")).toBe(false);
  });

  it("заметки: по строке на пункт, пустые строки уходят", () => {
    expect(itemsOf(" Первый \n\n Второй\n")).toEqual(["Первый", "Второй"]);
    const notes = notesOf("а\nб", "a");
    expect(notes).toEqual({ ru: ["а", "б"], en: ["a"] });
    expect(notesParallel(notes)).toBe(false);
  });

  it("объяснение класса нужно, когда номер мягче предложения, но не мягче минимума", () => {
    expect(needsNote(state({ suggested: "minor" }))).toBe(true);
    expect(needsNote(state({}))).toBe(false);
    expect(needsNote(state({ minimum: "minor", suggested: "minor" }))).toBe(
      false,
    );
  });
});
