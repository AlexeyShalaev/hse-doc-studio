import { describe, expect, it } from "vitest";
import { packOutcomePath, packRulePath, safeOutcomeBack } from "./routes";

const REF = { pack: "hse-cs-se", template: "vkr", version: "2026.1.2" };

describe("переход к правилу: адреса", () => {
  it("packRulePath несёт файл, указатель, вкладку и адрес возврата", () => {
    const from = packOutcomePath(
      "w1",
      REF,
      "selected=documents%3Athesis&i.kind=research",
    );
    const url = packRulePath(
      "w1",
      "hse-cs-se/templates/vkr/versions/2026.1.2/version.yaml",
      {
        pointer: "/pack_submission/profiles/0/signing_slots/0/when",
        pane: "form",
        from,
      },
    );
    const [path, query] = url.split("?");
    expect(path).toBe("/pack-studio/w/w1");
    const params = new URLSearchParams(query);
    expect(params.get("file")).toBe(
      "hse-cs-se/templates/vkr/versions/2026.1.2/version.yaml",
    );
    expect(params.get("at")).toBe(
      "/pack_submission/profiles/0/signing_slots/0/when",
    );
    expect(params.get("pane")).toBe("form");
    expect(params.get("from")).toBe(from);
  });

  it("без указателя параметра at нет", () => {
    const url = packRulePath("w1", "a/b.yaml", {
      pointer: null,
      pane: "source",
      from: "/x",
    });
    expect(new URLSearchParams(url.split("?")[1]).has("at")).toBe(false);
  });

  it("safeOutcomeBack пропускает только экран «Результат» этого пространства", () => {
    const ok = packOutcomePath("w1", REF, "selected=documents%3Athesis");
    expect(safeOutcomeBack("w1", ok)).toBe(ok);
    expect(safeOutcomeBack("w1", "/pack-studio/w/w1/result")).toBe(
      "/pack-studio/w/w1/result",
    );
    expect(safeOutcomeBack("w1", null)).toBeNull();
    expect(safeOutcomeBack("w1", "")).toBeNull();
    expect(safeOutcomeBack("w1", ok.replace("w1", "w2"))).toBeNull();
    expect(
      safeOutcomeBack("w1", "https://evil.example/pack-studio/w/w1/result"),
    ).toBeNull();
    expect(safeOutcomeBack("w1", "//evil.example")).toBeNull();
    expect(
      safeOutcomeBack("w1", "/pack-studio/w/w1/result//evil.example"),
    ).toBeNull();
    expect(safeOutcomeBack("w1", "/pack-studio/w/w1?file=x")).toBeNull();
    expect(safeOutcomeBack("w1", "/pack-studio/w/w1/resultx")).toBeNull();
  });
});
