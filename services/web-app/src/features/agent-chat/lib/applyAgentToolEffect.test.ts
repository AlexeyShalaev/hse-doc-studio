import { beforeEach, describe, expect, it } from "vitest";

import { useThemeStore } from "@shared/lib";

import { applyAgentToolEffect } from "./applyAgentToolEffect";

describe("applyAgentToolEffect", () => {
  beforeEach(() => {
    useThemeStore.getState().setTheme("light");
  });

  it("applies set_theme to the client theme store", () => {
    const applied = applyAgentToolEffect("set_theme", { theme: "dark" });

    expect(applied).toBe(true);
    expect(useThemeStore.getState().theme).toBe("dark");
  });

  it("applies the system theme", () => {
    const applied = applyAgentToolEffect("set_theme", { theme: "system" });

    expect(applied).toBe(true);
    expect(useThemeStore.getState().theme).toBe("system");
  });

  it("ignores an invalid theme value", () => {
    const applied = applyAgentToolEffect("set_theme", { theme: "neon" });

    expect(applied).toBe(false);
    expect(useThemeStore.getState().theme).toBe("light");
  });

  it("ignores a non-string theme arg", () => {
    const applied = applyAgentToolEffect("set_theme", { theme: 42 });

    expect(applied).toBe(false);
    expect(useThemeStore.getState().theme).toBe("light");
  });

  it("ignores unknown tools", () => {
    const applied = applyAgentToolEffect("set_engine", { engine: "xelatex" });

    expect(applied).toBe(false);
    expect(useThemeStore.getState().theme).toBe("light");
  });
});
