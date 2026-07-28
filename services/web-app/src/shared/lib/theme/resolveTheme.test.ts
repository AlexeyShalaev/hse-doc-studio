import { describe, expect, it } from "vitest";

import { resolveTheme } from "./resolveTheme";

describe("resolveTheme", () => {
  it("maps system to dark when the OS prefers dark", () => {
    expect(resolveTheme("system", true)).toBe("dark");
  });

  it("maps system to light when the OS does not prefer dark", () => {
    expect(resolveTheme("system", false)).toBe("light");
  });

  it("leaves explicit themes untouched regardless of the OS preference", () => {
    expect(resolveTheme("dark", false)).toBe("dark");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("blueprint", true)).toBe("blueprint");
    expect(resolveTheme("blueprint", false)).toBe("blueprint");
  });
});
