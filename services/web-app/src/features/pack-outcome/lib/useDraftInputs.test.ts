import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { INPUTS_DEBOUNCE_MS, useDraftInputs } from "./useDraftInputs";

type Props = {
  source: Record<string, string>;
  at: string;
  auto: boolean;
};

const setup = (initial: Props) => {
  const commit = vi.fn();
  const view = renderHook(
    (props: Props) => useDraftInputs({ ...props, commit }),
    {
      initialProps: initial,
    },
  );
  return { commit, view };
};

describe("useDraftInputs: запись в адрес по паузе", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("пауза 250 мс", () => {
    expect(INPUTS_DEBOUNCE_MS).toBe(250);
  });

  it("черновик виден сразу, запись одна и только после паузы", () => {
    const { commit, view } = setup({ source: {}, at: "a", auto: true });
    act(() => {
      view.result.current.set({ kind: "research" });
    });
    expect(view.result.current.value).toEqual({ kind: "research" });
    expect(view.result.current.pending).toBe(true);
    act(() => {
      vi.advanceTimersByTime(INPUTS_DEBOUNCE_MS - 1);
    });
    expect(commit).not.toHaveBeenCalled();
    act(() => {
      view.result.current.set({ kind: "research", staffing: "team2" });
      vi.advanceTimersByTime(INPUTS_DEBOUNCE_MS - 1);
    });
    // Новый выбор сдвинул паузу: прежнего значения в адресе не будет.
    expect(commit).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(commit).toHaveBeenCalledTimes(1);
    expect(commit).toHaveBeenCalledWith({
      kind: "research",
      staffing: "team2",
    });
  });

  it("когда адрес обновился, черновик уступает ему место", () => {
    const { commit, view } = setup({ source: {}, at: "a", auto: true });
    act(() => {
      view.result.current.set({ kind: "research" });
      vi.advanceTimersByTime(INPUTS_DEBOUNCE_MS);
    });
    view.rerender({ source: { kind: "research" }, at: "b", auto: true });
    expect(view.result.current.value).toEqual({ kind: "research" });
    expect(view.result.current.pending).toBe(false);
    expect(commit).toHaveBeenCalledTimes(1);
  });

  it("адрес сменился снаружи до записи: устаревший выбор не пишется поверх", () => {
    const { commit, view } = setup({ source: {}, at: "a", auto: true });
    act(() => {
      view.result.current.set({ kind: "research" });
    });
    view.rerender({ source: { staffing: "team3" }, at: "b", auto: true });
    expect(view.result.current.value).toEqual({ staffing: "team3" });
    act(() => {
      vi.advanceTimersByTime(INPUTS_DEBOUNCE_MS * 2);
    });
    expect(commit).not.toHaveBeenCalled();
  });

  it("now записывает сразу и снимает паузу", () => {
    const { commit, view } = setup({
      source: { kind: "research" },
      at: "a",
      auto: true,
    });
    act(() => {
      view.result.current.set({ kind: "research", staffing: "team2" });
      view.result.current.set({ kind: "research" }, true);
    });
    expect(commit).toHaveBeenCalledTimes(1);
    expect(commit).toHaveBeenCalledWith({ kind: "research" });
    act(() => {
      vi.advanceTimersByTime(INPUTS_DEBOUNCE_MS * 2);
    });
    expect(commit).toHaveBeenCalledTimes(1);
  });

  it("discard отменяет запись и забывает черновик", () => {
    const { commit, view } = setup({ source: {}, at: "a", auto: true });
    act(() => {
      view.result.current.set({ kind: "research" });
      view.result.current.discard();
      vi.advanceTimersByTime(INPUTS_DEBOUNCE_MS * 2);
    });
    expect(commit).not.toHaveBeenCalled();
    expect(view.result.current.value).toEqual({});
    expect(view.result.current.pending).toBe(false);
  });

  it("при закрытии панели незаписанный выбор записывается, а не теряется", () => {
    const { commit, view } = setup({ source: {}, at: "a", auto: true });
    act(() => {
      view.result.current.set({ kind: "research" });
    });
    view.unmount();
    expect(commit).toHaveBeenCalledWith({ kind: "research" });
  });

  it("без автозаписи (телефон) пишет только flush", () => {
    const { commit, view } = setup({ source: {}, at: "a", auto: false });
    act(() => {
      view.result.current.set({ kind: "research" });
      vi.advanceTimersByTime(INPUTS_DEBOUNCE_MS * 4);
    });
    expect(commit).not.toHaveBeenCalled();
    expect(view.result.current.pending).toBe(true);
    act(() => {
      view.result.current.flush();
    });
    expect(commit).toHaveBeenCalledWith({ kind: "research" });
    view.unmount();
    expect(commit).toHaveBeenCalledTimes(1);
  });
});
