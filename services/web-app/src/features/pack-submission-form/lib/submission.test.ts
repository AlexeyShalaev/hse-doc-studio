import { describe, expect, it } from "vitest";
import {
  WHEN_KEYS,
  hintIssue,
  kindsKey,
  profileFindings,
  toggleMethod,
  toggleSignature,
  whenFromKey,
  whenKey,
} from "./submission";

const ITEM = {
  doc_id: "report",
  signatures: ["author"],
  methods: { author: ["image" as const] },
  skip_if_nda: false,
  supported_kinds: [],
};

describe("помощники формы точек сдачи", () => {
  it("условия `when` закрытым списком туда и обратно", () => {
    expect(WHEN_KEYS).toHaveLength(10);
    for (const key of WHEN_KEYS) expect(whenKey(whenFromKey(key))).toBe(key);
    expect(whenFromKey("supervisor:company")).toEqual({
      person: "supervisor",
      role: "company",
    });
    expect(whenFromKey("author")).toBeNull();
  });

  it("подпись уходит вместе со своими способами", () => {
    const withSupervisor = toggleSignature(ITEM, "supervisor", true);
    expect(withSupervisor.signatures).toEqual(["author", "supervisor"]);
    expect(toggleSignature(ITEM, "author", false)).toEqual({
      ...ITEM,
      signatures: [],
      methods: {},
    });
  });

  it("способы в порядке справки, пусто значит любой", () => {
    const both = toggleMethod(ITEM, "author", "detached", true);
    expect(both.methods.author).toEqual(["image", "detached"]);
    expect(toggleMethod(ITEM, "author", "image", false).methods).toEqual({});
  });

  it("подсказка срока: оба языка, до 200 знаков, без дат", () => {
    expect(hintIssue("Обычно в середине ноября")).toBeNull();
    expect(hintIssue("  ")).toBe("missing");
    expect(hintIssue("а".repeat(201))).toBe("long");
    expect(hintIssue("До 15 ноября")).toBe("date");
    expect(hintIssue("By November 15")).toBe("date");
    expect(hintIssue("Сдача 15.11")).toBe("date");
    expect(hintIssue("Версия 2026.1.4")).toBeNull();
  });

  it("вид работы: пусто и оба это «оба»", () => {
    expect(kindsKey([])).toBe("both");
    expect(kindsKey(["research", "project"])).toBe("both");
    expect(kindsKey(["project"])).toBe("project");
  });

  it("находки про профиль: по id в тексте линтера и по указателю схемы", () => {
    const findings = [
      { message: "профиль final: extra_items ссылается на 'x'", pointer: null },
      { message: "required", pointer: "/pack_submission/profiles/1/items/0" },
      { message: "профиль other: ...", pointer: null },
      { message: "x", pointer: "/pack_submission/profiles/10" },
    ];
    expect(profileFindings(findings, { id: "final", index: 1 })).toEqual(
      findings.slice(0, 2),
    );
  });
});
