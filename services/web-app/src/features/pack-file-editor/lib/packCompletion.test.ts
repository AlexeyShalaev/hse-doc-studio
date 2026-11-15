import {
  CompletionContext,
  type CompletionResult,
  type CompletionSource,
} from "@codemirror/autocomplete";
import { EditorState } from "@codemirror/state";
import { beforeAll, describe, expect, it } from "vitest";
import type { PackEditorHints } from "@entities/pack-studio";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { insideJinja, packCompletionExtension } from "./packCompletion";

const HINTS: PackEditorHints = {
  version: "p/templates/t/versions/2026.1.0",
  meta_fields: [
    {
      key: "year",
      type: "string",
      label: { ru: "Учебный год", en: "Academic year" },
      group: "study",
    },
  ],
  macros: [
    {
      name: "hseTitleEn",
      keys: ["name_en"],
      source: "p/templates/t/versions/2026.1.0/files/common/meta.tex.j2",
    },
  ],
};

/** Все источники, которые расширение кладёт в languageData, и их ответы у конца текста. */
const complete = async (
  doc: string,
  options: { jinja: boolean; macros: boolean },
  explicit = false,
): Promise<CompletionResult[]> => {
  const state = EditorState.create({
    doc,
    extensions: [
      packCompletionExtension({ getHints: () => HINTS, ...options }),
    ],
  });
  const sources = state.languageDataAt<CompletionSource>(
    "autocomplete",
    doc.length,
  );
  const context = new CompletionContext(state, doc.length, explicit);
  const results: (CompletionResult | null)[] = [];
  for (const source of sources) results.push(await source(context));
  return results.filter((r): r is CompletionResult => r !== null);
};

const labels = (results: CompletionResult[]): string[] =>
  results.flatMap((r) => r.options.map((o) => o.label));

describe("автодополнение шаблонов пака", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
  });

  it("выражение Jinja открыто, пока не закрыто в строке", () => {
    expect(insideJinja("\\hseYear{{{ project.")).toBe(true);
    expect(insideJinja("((* if project.kind ")).toBe(true);
    expect(insideJinja("{{ x }} и дальше")).toBe(false);
    expect(insideJinja("((* endif *)) текст")).toBe(false);
  });

  it("внутри {{ }} переменные контекста и поля анкеты версии", async () => {
    const results = await complete("Год: {{ project.me", {
      jinja: true,
      macros: false,
    });
    const found = labels(results);
    expect(found).toContain("project.meta.year");
    expect(found).toContain("project.name");
    expect(results[0]?.from).toBe("Год: {{ ".length);
  });

  it("после | фильтры пака", async () => {
    const found = labels(
      await complete("{{ project.name | tex", { jinja: true, macros: false }),
    );
    expect(found).toContain("texesc");
    expect(found).not.toContain("project.name");
  });

  it("в ((* *)) ключевые слова блока", async () => {
    expect(
      labels(await complete("((* ", { jinja: true, macros: false }, true)),
    ).toContain("if");
  });

  it("вне Jinja переменных нет, а макросы \\hse... есть", async () => {
    expect(
      labels(await complete("Текст project.", { jinja: true, macros: false })),
    ).toEqual([]);
    const macros = await complete("\\title{\\hse", {
      jinja: false,
      macros: true,
    });
    expect(labels(macros)).toEqual(["\\hseTitleEn"]);
    expect(macros[0]?.options[0]?.detail).toContain("name_en");
  });

  it("без включённых источников расширение пустое", async () => {
    expect(
      await complete("{{ project.", { jinja: false, macros: false }),
    ).toEqual([]);
  });
});
