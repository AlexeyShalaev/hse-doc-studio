import { describe, expect, it } from "vitest";
import type { PackTree } from "@entities/pack-studio";
import { GALLERY_TREE } from "../galleryKit";
import { hasVersion, resolveEntryPlace } from "./entry";

const REF = (version: string) => ({
  pack: "hse-cs-sse",
  template: "coursework",
  version,
});
const EMPTY: PackTree = { ...GALLERY_TREE, packs: [] };

describe("выбор места на входе", () => {
  it("hasVersion знает версии дерева", () => {
    expect(hasVersion(GALLERY_TREE, REF("2026.1.3"))).toBe(true);
    expect(hasVersion(GALLERY_TREE, REF("9.9.9"))).toBe(false);
    expect(hasVersion(GALLERY_TREE, { ...REF("2026.1.3"), pack: "x" })).toBe(
      false,
    );
  });

  it("без подсказок: версия по умолчанию первого шаблона, вкладка «Результат»", () => {
    expect(resolveEntryPlace(GALLERY_TREE)).toEqual({
      ref: REF("2026.1.2"),
      tab: "result",
      inputs: {},
    });
  });

  it("без версии по умолчанию берётся последняя в списке", () => {
    const tree: PackTree = structuredClone(GALLERY_TREE);
    const tpl = tree.packs[0]?.templates[0];
    if (tpl) tpl.default_version = "нет такой";
    expect(resolveEntryPlace(tree)?.ref.version).toBe("2026.1.3");
  });

  it("последнее место возвращает версию, вкладку и условия", () => {
    const last = {
      ref: REF("2026.1.3"),
      tab: "content" as const,
      inputs: { kind: "research" },
    };
    expect(resolveEntryPlace(GALLERY_TREE, { last })).toEqual(last);
  });

  it("последнего места нет в дереве: умолчание, условия не тянутся", () => {
    const last = {
      ref: REF("0.0.1"),
      tab: "check" as const,
      inputs: { kind: "x" },
    };
    expect(resolveEntryPlace(GALLERY_TREE, { last })).toEqual({
      ref: REF("2026.1.2"),
      tab: "result",
      inputs: {},
    });
  });

  it("версия из адреса старше памяти; вкладка из адреса старше вкладки из памяти", () => {
    const last = {
      ref: REF("2026.1.3"),
      tab: "check" as const,
      inputs: { a: "1" },
    };
    expect(
      resolveEntryPlace(GALLERY_TREE, {
        ref: REF("2026.1.2"),
        tab: "content",
        last,
      }),
    ).toEqual({ ref: REF("2026.1.2"), tab: "content", inputs: {} });
    expect(resolveEntryPlace(GALLERY_TREE, { tab: "content", last })).toEqual({
      ref: REF("2026.1.3"),
      tab: "content",
      inputs: { a: "1" },
    });
  });

  it("версии из адреса нет в дереве: идём дальше по порядку", () => {
    expect(
      resolveEntryPlace(GALLERY_TREE, { ref: REF("0.0.1") })?.ref.version,
    ).toBe("2026.1.2");
  });

  it("шаблон без версии (?newVersion=): его версия по умолчанию; чужой шаблон: общее умолчание", () => {
    const own = { pack: "hse-cs-sse", template: "coursework" };
    expect(
      resolveEntryPlace(GALLERY_TREE, { template: own, tab: "result" })?.ref,
    ).toEqual(REF("2026.1.2"));
    expect(
      resolveEntryPlace(GALLERY_TREE, {
        template: { pack: "x", template: "y" },
      })?.ref,
    ).toEqual(REF("2026.1.2"));
  });

  it("пустое дерево: места нет", () => {
    expect(resolveEntryPlace(EMPTY)).toBeNull();
  });
});
