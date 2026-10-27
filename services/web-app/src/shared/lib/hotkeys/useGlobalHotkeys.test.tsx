import { fireEvent, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useGlobalHotkeys } from "./useGlobalHotkeys";

const press = (init: KeyboardEventInit, target: Window | Element = window) =>
  fireEvent.keyDown(target, init);

// Платформа определяется по userAgent при загрузке модуля; jsdom не mac,
// значит модификатор здесь Ctrl.
describe("useGlobalHotkeys sync shortcut", () => {
  it("Mod+Shift+S asks for a sync and the browser default is suppressed", () => {
    const onSync = vi.fn();
    renderHook(() => {
      useGlobalHotkeys({ onSync });
    });
    const notCancelled = fireEvent.keyDown(window, {
      key: "S",
      code: "KeyS",
      ctrlKey: true,
      shiftKey: true,
    });
    expect(onSync).toHaveBeenCalledTimes(1);
    expect(notCancelled).toBe(false);
  });

  it("works in the Cyrillic layout (by the physical key)", () => {
    const onSync = vi.fn();
    renderHook(() => {
      useGlobalHotkeys({ onSync });
    });
    press({ key: "Ы", code: "KeyS", ctrlKey: true, shiftKey: true });
    expect(onSync).toHaveBeenCalledTimes(1);
  });

  it("fires from a text field too, like the other Mod+Shift shortcuts", () => {
    const onSync = vi.fn();
    renderHook(() => {
      useGlobalHotkeys({ onSync });
    });
    const input = document.createElement("input");
    document.body.appendChild(input);
    press({ key: "S", code: "KeyS", ctrlKey: true, shiftKey: true }, input);
    expect(onSync).toHaveBeenCalledTimes(1);
    input.remove();
  });

  it("leaves Mod+S and Shift+S to the browser", () => {
    const onSync = vi.fn();
    renderHook(() => {
      useGlobalHotkeys({ onSync });
    });
    const plain = fireEvent.keyDown(window, {
      key: "s",
      code: "KeyS",
      ctrlKey: true,
    });
    const shifted = fireEvent.keyDown(window, {
      key: "S",
      code: "KeyS",
      shiftKey: true,
    });
    expect(onSync).not.toHaveBeenCalled();
    expect(plain && shifted).toBe(true);
  });

  it("does not swallow the key when the screen has no handler", () => {
    renderHook(() => {
      useGlobalHotkeys({});
    });
    const notCancelled = fireEvent.keyDown(window, {
      key: "S",
      code: "KeyS",
      ctrlKey: true,
      shiftKey: true,
    });
    expect(notCancelled).toBe(true);
  });
});
