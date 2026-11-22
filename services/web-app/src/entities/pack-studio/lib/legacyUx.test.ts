import { afterEach, describe, expect, it, vi } from "vitest";
import { forgetLegacyUxFlag, withoutUxParam } from "./legacyUx";

describe("прежний флаг ?ux=", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("без ux адрес не трогаем", () => {
    expect(withoutUxParam("")).toBeNull();
    expect(withoutUxParam("?i.kind=research")).toBeNull();
  });

  it("ux=2, ux=1 и мусор убираются, остальное остаётся по порядку", () => {
    expect(withoutUxParam("?ux=2")).toBe("");
    expect(withoutUxParam("?ux=1")).toBe("");
    expect(withoutUxParam("ux=banana")).toBe("");
    expect(withoutUxParam("?sel=documents%3Ats&ux=2&i.kind=research")).toBe(
      "?sel=documents%3Ats&i.kind=research",
    );
  });

  it("память флага стирается, без хранилища тихо", () => {
    window.localStorage.setItem("ps.ux", "1");
    forgetLegacyUxFlag();
    expect(window.localStorage.getItem("ps.ux")).toBeNull();
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(() => {
      forgetLegacyUxFlag();
    }).not.toThrow();
  });
});
