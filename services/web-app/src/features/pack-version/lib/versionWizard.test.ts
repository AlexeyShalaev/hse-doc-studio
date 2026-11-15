import { describe, expect, it } from "vitest";
import type {
  PackVersionReason,
  PackVersionState,
} from "@entities/pack-studio";
import {
  isSofter,
  itemsOf,
  needsNote,
  notesOf,
  notesParallel,
  reasonTarget,
} from "./versionWizard";

const reason = (path: string): PackVersionReason => ({
  code: "file_changed",
  path,
  change: "changed",
  minimum: "patch",
  suggested: "patch",
  hard: false,
  exception: false,
  message: { ru: path, en: path },
});

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

  it("причина ведёт в файл версии или в манифест", () => {
    const dir = "demo/templates/report/versions/2026.1.1";
    expect(reasonTarget(dir, reason("files/report/main.tex"))).toBe(
      `${dir}/files/report/main.tex`,
    );
    expect(reasonTarget(dir, reason("checks[gost.yaml].rules[x]"))).toBe(
      `${dir}/checks/gost.yaml`,
    );
    expect(reasonTarget(dir, reason("meta_fields.city"))).toBe(
      `${dir}/version.yaml`,
    );
  });
});
