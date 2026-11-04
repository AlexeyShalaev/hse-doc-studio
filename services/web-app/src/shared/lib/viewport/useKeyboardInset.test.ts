import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readKeyboardMetrics, useKeyboardInset } from "./useKeyboardInset";

describe("readKeyboardMetrics", () => {
  it("is zero without a keyboard", () => {
    expect(readKeyboardMetrics(844, { height: 844, offsetTop: 0 })).toEqual({
      inset: 0,
      height: 844,
    });
  });

  it("reports the part of the window the keyboard covers", () => {
    expect(readKeyboardMetrics(844, { height: 520, offsetTop: 0 })).toEqual({
      inset: 324,
      height: 520,
    });
  });

  it("subtracts the page scroll that iOS applies to keep the field visible", () => {
    expect(
      readKeyboardMetrics(844, { height: 520, offsetTop: 100 }).inset,
    ).toBe(224);
  });

  it("does not take the collapsing browser toolbar for a keyboard", () => {
    expect(readKeyboardMetrics(780, { height: 730, offsetTop: 0 }).inset).toBe(
      0,
    );
  });
});

describe("useKeyboardInset", () => {
  type Fake = {
    height: number;
    offsetTop: number;
    addEventListener: ReturnType<typeof vi.fn>;
    removeEventListener: ReturnType<typeof vi.fn>;
  };
  const original = Object.getOwnPropertyDescriptor(window, "visualViewport");

  const install = (fake: Fake | undefined): void => {
    Object.defineProperty(window, "visualViewport", {
      configurable: true,
      value: fake,
    });
  };

  afterEach(() => {
    if (original) Object.defineProperty(window, "visualViewport", original);
    else Reflect.deleteProperty(window, "visualViewport");
    document.documentElement.removeAttribute("style");
    document.documentElement.removeAttribute("data-keyboard");
  });

  it("writes the variables and removes them on unmount", () => {
    const fake: Fake = {
      height: window.innerHeight - 300,
      offsetTop: 0,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    };
    install(fake);
    const { unmount } = renderHook(() => {
      useKeyboardInset(true);
    });
    const root = document.documentElement;
    expect(root.style.getPropertyValue("--kb-inset")).toBe("300px");
    expect(root).toHaveAttribute("data-keyboard");
    unmount();
    expect(root.style.getPropertyValue("--kb-inset")).toBe("");
    expect(root).not.toHaveAttribute("data-keyboard");
    expect(fake.removeEventListener).toHaveBeenCalledTimes(2);
  });

  it("does nothing when disabled or without visualViewport", () => {
    install(undefined);
    renderHook(() => {
      useKeyboardInset(true);
    });
    expect(document.documentElement.style.getPropertyValue("--kb-inset")).toBe(
      "",
    );
  });
});
