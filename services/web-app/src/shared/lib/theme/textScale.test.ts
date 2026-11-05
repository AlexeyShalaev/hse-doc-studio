import { beforeEach, describe, expect, it } from "vitest";

import {
  DEFAULT_TEXT_SCALE,
  TEXT_SCALE_STEPS,
  applyTextScale,
  normalizeTextScale,
} from "./textScale";
import { useThemeStore } from "./themeStore";

describe("textScale", () => {
  beforeEach(() => {
    localStorage.clear();
    useThemeStore.setState({
      textScale: DEFAULT_TEXT_SCALE,
      textScaleChosen: false,
    });
    document.documentElement.removeAttribute("style");
    document.documentElement.removeAttribute("data-text-scale");
  });

  it("offers the steps the backend accepts, 100% among them", () => {
    expect([...TEXT_SCALE_STEPS]).toEqual([90, 100, 112, 125, 140]);
    expect(DEFAULT_TEXT_SCALE).toBe(100);
  });

  it("reads anything off the scale as the default size", () => {
    expect(normalizeTextScale(125)).toBe(125);
    for (const bad of [130, "125", null, undefined, 0, NaN]) {
      expect(normalizeTextScale(bad)).toBe(100);
    }
  });

  it("writes the factor and the step to the root element", () => {
    applyTextScale(document.documentElement, 125);
    expect(
      document.documentElement.style.getPropertyValue("--text-scale"),
    ).toBe("1.25");
    expect(document.documentElement.dataset.textScale).toBe("125");
  });

  it("keeps the choice in the same persisted store as the theme", () => {
    useThemeStore.getState().setTextScale(140);
    const stored = JSON.parse(
      localStorage.getItem("hse-studio-theme") ?? "{}",
    ) as { state?: { textScale?: number } };
    expect(stored.state?.textScale).toBe(140);
  });

  it("migrates an old record: a non-default size counts as chosen", async () => {
    localStorage.setItem(
      "hse-studio-theme",
      JSON.stringify({ state: { textScale: 125 }, version: 0 }),
    );
    await useThemeStore.persist.rehydrate();
    expect(useThemeStore.getState().textScaleChosen).toBe(true);
    localStorage.setItem(
      "hse-studio-theme",
      JSON.stringify({ state: { textScale: 100 }, version: 0 }),
    );
    await useThemeStore.persist.rehydrate();
    expect(useThemeStore.getState().textScaleChosen).toBe(false);
  });

  it("adopting the account value is not a choice", () => {
    useThemeStore.getState().adoptTextScale(125);
    expect(useThemeStore.getState().textScale).toBe(125);
    expect(useThemeStore.getState().textScaleChosen).toBe(false);
  });

  it("drops an off-scale value from the store", () => {
    useThemeStore.getState().setTextScale(130 as never);
    expect(useThemeStore.getState().textScale).toBe(100);
  });
});
