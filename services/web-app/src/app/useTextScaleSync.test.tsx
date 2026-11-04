import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
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

describe("useTextScaleSync", () => {
  beforeEach(() => {
    useThemeStore.setState({ textScale: 100 });
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("takes the account value while this device is on the default size", async () => {
    vi.spyOn(settingsApi, "get").mockResolvedValue({
      text_scale: 125,
    } as SettingsData);
    renderHook(
      () => {
        useTextScaleSync(true);
      },
      { wrapper },
    );
    await waitFor(() => {
      expect(useThemeStore.getState().textScale).toBe(125);
    });
  });

  it("keeps the size chosen on this device", async () => {
    useThemeStore.setState({ textScale: 140 });
    const get = vi
      .spyOn(settingsApi, "get")
      .mockResolvedValue({ text_scale: 112 } as SettingsData);
    renderHook(
      () => {
        useTextScaleSync(true);
      },
      { wrapper },
    );
    await waitFor(() => {
      expect(get).toHaveBeenCalled();
    });
    expect(useThemeStore.getState().textScale).toBe(140);
  });

  it("does not ask the account before sign-in", () => {
    const get = vi.spyOn(settingsApi, "get");
    renderHook(
      () => {
        useTextScaleSync(false);
      },
      { wrapper },
    );
    expect(get).not.toHaveBeenCalled();
  });
});
