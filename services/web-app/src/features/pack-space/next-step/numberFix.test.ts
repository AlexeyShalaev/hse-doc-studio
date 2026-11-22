import { describe, expect, it } from "vitest";
import { ApiError } from "@shared/api";
import type { PackVersionState } from "@entities/pack-studio";
import { GALLERY_REF } from "../galleryKit";
import { causeGroup, isNumberError, resolveNumberFix } from "./numberFix";

const state = (patch: Partial<PackVersionState> = {}): PackVersionState => ({
  version: {
    ...GALLERY_REF,
    path: "hse-cs-sse/templates/coursework/versions/2026.1.3",
  },
  status: "beta",
  released: false,
  modified: false,
  registered: false,
  release_outdated: false,
  is_default: false,
  base: "2026.1.2",
  minimum: "minor",
  suggested: "minor",
  by_number: "patch",
  declared: null,
  note: null,
  number_ok: false,
  headline: { ru: "", en: "" },
  reasons: [
    {
      code: "document_scope",
      path: "documents[ts].supported_kinds",
      change: "changed",
      minimum: "minor",
      suggested: "minor",
      hard: true,
      exception: false,
      message: { ru: "", en: "" },
    },
  ],
  numbers: { patch: "2026.1.4", minor: "2026.2.0", major: "2027.1.0" },
  changes: { ru: [], en: [] },
  breaking_changes: { ru: [], en: [] },
  draft_changes: { ru: [], en: [] },
  draft_breaking: { ru: [], en: [] },
  move_to: null,
  error: null,
  ...patch,
});

describe("resolveNumberFix: правки требуют номера выше", () => {
  it("копия сделана небольшой правкой, а условия меняют состав документов: номер 2026.2.0", () => {
    const fix = resolveNumberFix(state());
    expect(fix).toEqual({
      to: "2026.2.0",
      cls: "minor",
      cause: "document_scope",
    });
    expect(fix && causeGroup(fix)).toBe("documents");
  });

  it("номер подходит: менять нечего", () => {
    expect(resolveNumberFix(state({ number_ok: true }))).toBeNull();
  });

  it("версия выпущена или отчёта нет: номер не меняем", () => {
    expect(resolveNumberFix(state({ released: true }))).toBeNull();
    expect(resolveNumberFix(null)).toBeNull();
  });

  it("нет минимума или свободного номера нужного класса: менять нечем", () => {
    expect(resolveNumberFix(state({ minimum: null }))).toBeNull();
    expect(
      resolveNumberFix(
        state({ numbers: { patch: "2026.1.4", minor: null, major: null } }),
      ),
    ).toBeNull();
  });

  it("новая редакция регламента: своя группа слов, причина не нужна", () => {
    const fix = resolveNumberFix(state({ minimum: "major" }));
    expect(fix?.to).toBe("2027.1.0");
    expect(fix && causeGroup(fix)).toBe("regulation");
  });

  it("неизвестная причина: общая фраза", () => {
    const fix = resolveNumberFix(
      state({
        reasons: [
          {
            code: "something_new",
            path: "x",
            change: "changed",
            minimum: "minor",
            suggested: "minor",
            hard: true,
            exception: false,
            message: { ru: "", en: "" },
          },
        ],
      }),
    );
    expect(fix && causeGroup(fix)).toBeNull();
  });
});

describe("isNumberError", () => {
  it("отказы сервера про номер", () => {
    const make = (code: string) => new ApiError("x", code, 422, null);
    expect(isNumberError(make("class_softer_than_changes"))).toBe(true);
    expect(isNumberError(make("version_number_invalid"))).toBe(true);
    expect(isNumberError(make("lint_failed"))).toBe(false);
    expect(isNumberError(new Error("x"))).toBe(false);
  });
});
