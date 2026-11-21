import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  PACK_STUDIO_UX_KEY,
  resetPackStudioUx,
  usePackStudioUx,
} from "./usePackStudioUx";

const at = (url: string) => {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[url]}>{children}</MemoryRouter>
  );
  return renderHook(() => usePackStudioUx(), { wrapper }).result.current;
};

describe("usePackStudioUx", () => {
  beforeEach(resetPackStudioUx);
  afterEach(() => {
    vi.restoreAllMocks();
    resetPackStudioUx();
  });

  it("по умолчанию прежний интерфейс", () => {
    expect(at("/pack-studio")).toBe(1);
  });

  it("?ux=2 включает новый и запоминается на следующие заходы", () => {
    expect(at("/pack-studio/w/w1?ux=2")).toBe(2);
    expect(window.localStorage.getItem(PACK_STUDIO_UX_KEY)).toBe("2");
    expect(at("/pack-studio/w/w1")).toBe(2);
  });

  it("?ux=1 возвращает прежний и тоже запоминается", () => {
    at("/pack-studio?ux=2");
    expect(at("/pack-studio?ux=1")).toBe(1);
    expect(at("/pack-studio")).toBe(1);
  });

  it("мусор в query и в памяти игнорируется", () => {
    window.localStorage.setItem(PACK_STUDIO_UX_KEY, "banana");
    expect(at("/pack-studio?ux=3")).toBe(1);
    window.localStorage.setItem(PACK_STUDIO_UX_KEY, "2");
    expect(at("/pack-studio?ux=")).toBe(2);
  });

  it("хранилище не открывается: выбор живёт в памяти вкладки", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(at("/pack-studio?ux=2")).toBe(2);
    expect(at("/pack-studio")).toBe(2);
  });
});
