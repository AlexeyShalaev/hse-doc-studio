import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { settingsApi, type SettingsData } from "@entities/app-settings";
import { useThemeStore } from "@shared/lib";
import { useTextScaleSync } from "./useTextScaleSync";

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient()}>
    {children}
  </QueryClientProvider>
);

const settings = (text_scale: number) => ({ text_scale }) as SettingsData;
const mount = (enabled = true) =>
  renderHook(
    () => {
      useTextScaleSync(enabled);
    },
    { wrapper },
  );

describe("useTextScaleSync", () => {
  beforeEach(() => {
    useThemeStore.setState({ textScale: 100, textScaleChosen: false });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("takes the account value on a device where nothing was chosen", async () => {
    vi.spyOn(settingsApi, "get").mockResolvedValue(settings(125));
    mount();
    await waitFor(() => {
      expect(useThemeStore.getState().textScale).toBe(125);
    });
    expect(useThemeStore.getState().textScaleChosen).toBe(false);
  });

  it("keeps the size chosen on this device and saves it to the account", async () => {
    useThemeStore.getState().setTextScale(140);
    vi.spyOn(settingsApi, "get").mockResolvedValue(settings(112));
    const update = vi
      .spyOn(settingsApi, "update")
      .mockResolvedValue(settings(140));
    mount();
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith({ text_scale: 140 });
    });
    expect(useThemeStore.getState().textScale).toBe(140);
  });

  it("an explicit 100% beats an account at 140%, also while the PUT is slow", async () => {
    vi.spyOn(settingsApi, "get").mockResolvedValue(settings(140));
    let finish: (value: SettingsData) => void = () => undefined;
    const update = vi.spyOn(settingsApi, "update").mockReturnValue(
      new Promise<SettingsData>((resolve) => {
        finish = resolve;
      }),
    );
    mount();
    await waitFor(() => {
      expect(useThemeStore.getState().textScale).toBe(140);
    });
    act(() => {
      useThemeStore.getState().setTextScale(100);
    });
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith({ text_scale: 100 });
    });
    // Сервер ещё отвечает 140, а выбор уже сделан: размер не откатывается.
    expect(useThemeStore.getState().textScale).toBe(100);
    expect(update).toHaveBeenCalledTimes(1);
    await act(async () => {
      finish(settings(100));
      await Promise.resolve();
    });
    expect(useThemeStore.getState().textScale).toBe(100);
  });

  it("retries the save after a failure", async () => {
    vi.spyOn(settingsApi, "get").mockResolvedValue(settings(100));
    const update = vi
      .spyOn(settingsApi, "update")
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue(settings(125));
    useThemeStore.getState().setTextScale(125);
    mount();
    await waitFor(() => {
      expect(update).toHaveBeenCalledTimes(1);
    });
    await waitFor(
      () => {
        expect(update).toHaveBeenCalledTimes(2);
      },
      { timeout: 6000 },
    );
    expect(useThemeStore.getState().textScale).toBe(125);
  });

  it("does not ask the account before sign-in", () => {
    const get = vi.spyOn(settingsApi, "get");
    mount(false);
    expect(get).not.toHaveBeenCalled();
  });
});
