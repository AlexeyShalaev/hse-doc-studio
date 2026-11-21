import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readPlace, readUi, writePlace, writeUi } from "./memory";

const PLACE = {
  ref: { pack: "p", template: "t", version: "1.0" },
  tab: "content" as const,
  inputs: { kind: "research" },
};

describe("память последнего места", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("пусто: места нет", () => {
    expect(readPlace("w1")).toBeNull();
    expect(readUi("w1", "more")).toBeUndefined();
  });

  it("круг записи и чтения, у пространств своя память", () => {
    writePlace("w1", PLACE);
    expect(readPlace("w1")).toEqual(PLACE);
    expect(readPlace("w2")).toBeNull();
  });

  it("мелочи интерфейса не затирают место и наоборот", () => {
    writePlace("w1", PLACE);
    writeUi("w1", "moreInputs", true);
    writeUi("w1", "hidden", "result");
    expect(readUi("w1", "moreInputs")).toBe(true);
    expect(readUi("w1", "hidden")).toBe("result");
    writePlace("w1", { ...PLACE, tab: "check" });
    expect(readUi("w1", "moreInputs")).toBe(true);
    expect(readPlace("w1")?.tab).toBe("check");
  });

  it("повреждённая или чужая запись считается отсутствующей", () => {
    window.localStorage.setItem("ps.space.w1", "{not json");
    expect(readPlace("w1")).toBeNull();
    window.localStorage.setItem(
      "ps.space.w1",
      JSON.stringify({ place: { ref: { pack: 1 }, tab: "result" } }),
    );
    expect(readPlace("w1")).toBeNull();
    window.localStorage.setItem(
      "ps.space.w1",
      JSON.stringify({ place: { ref: PLACE.ref, tab: "files" } }),
    );
    expect(readPlace("w1")).toBeNull();
    window.localStorage.setItem("ps.space.w1", "42");
    expect(readPlace("w1")).toBeNull();
  });

  it("хранилище не открывается: память живёт до закрытия вкладки", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    writePlace("w9", PLACE);
    expect(readPlace("w9")).toEqual(PLACE);
  });
});
