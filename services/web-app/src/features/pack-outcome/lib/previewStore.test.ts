import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  EMPTY_PREVIEW_MEMORY,
  previewMemoryKey,
  readPreviewMemory,
  resetPreviewMemory,
  useAutoPreview,
  writePreviewMemory,
} from "./previewStore";

const KEY = "hse-studio.packOutcome.previewAuto";

describe("автосборка предпросмотра: переключатель", () => {
  afterEach(() => {
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("по умолчанию выключена, выбор пишется в sessionStorage и читается заново", () => {
    const first = renderHook(() => useAutoPreview());
    expect(first.result.current[0]).toBe(false);
    act(() => {
      first.result.current[1](true);
    });
    expect(first.result.current[0]).toBe(true);
    expect(window.sessionStorage.getItem(KEY)).toBe("1");
    expect(renderHook(() => useAutoPreview()).result.current[0]).toBe(true);
    act(() => {
      first.result.current[1](false);
    });
    expect(window.sessionStorage.getItem(KEY)).toBe("0");
  });

  it("без хранилища работает до перезагрузки, не падает", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    const view = renderHook(() => useAutoPreview());
    expect(view.result.current[0]).toBe(false);
    act(() => {
      view.result.current[1](true);
    });
    expect(view.result.current[0]).toBe(true);
  });
});

describe("память предпросмотра версии", () => {
  afterEach(resetPreviewMemory);

  it("пишется частями, по версиям раздельно, сбрасывается", () => {
    const ref = { pack: "p", template: "t", version: "1" };
    const key = previewMemoryKey("ws", ref);
    expect(readPreviewMemory(key)).toBe(EMPTY_PREVIEW_MEMORY);
    writePreviewMemory(key, { document: "report" });
    writePreviewMemory(key, { built: { buildId: "b", key: "k" } });
    expect(readPreviewMemory(key)).toMatchObject({
      document: "report",
      built: { buildId: "b", key: "k" },
    });
    expect(
      readPreviewMemory(previewMemoryKey("ws", { ...ref, version: "2" })),
    ).toBe(EMPTY_PREVIEW_MEMORY);
    resetPreviewMemory();
    expect(readPreviewMemory(key)).toBe(EMPTY_PREVIEW_MEMORY);
  });
});
