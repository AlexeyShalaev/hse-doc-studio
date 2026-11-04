import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useApplyTheme } from "./useApplyTheme";
import { useThemeStore } from "./themeStore";

describe("useApplyTheme: text size", () => {
  it("applies the stored size and follows changes on the fly", () => {
    useThemeStore.setState({ textScale: 112 });
    renderHook(() => {
      useApplyTheme();
    });
    const root = document.documentElement;
    expect(root.style.getPropertyValue("--text-scale")).toBe("1.12");
    act(() => {
      useThemeStore.getState().setTextScale(140);
    });
    expect(root.style.getPropertyValue("--text-scale")).toBe("1.4");
    expect(root.dataset.textScale).toBe("140");
  });
});
