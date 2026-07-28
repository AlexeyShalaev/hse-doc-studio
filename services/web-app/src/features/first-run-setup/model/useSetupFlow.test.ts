import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setupApi } from "@entities/setup";
import { useSetupFlow } from "./useSetupFlow";

vi.mock("@entities/setup", () => ({
  setupApi: {
    status: vi.fn(),
    probeFolder: vi.fn(),
    apply: vi.fn(),
  },
}));

const mocked = vi.mocked(setupApi);

const okProbe = {
  status: "ok" as const,
  exists: true,
  entries: [
    { name: "diploma", is_dir: true },
    { name: "coursework", is_dir: true },
  ],
  is_empty: false,
  writable: true,
  looks_like_install: false,
  reason: null,
  detail: null,
};

describe("useSetupFlow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows what the folder contains so a typo is recognisable", async () => {
    mocked.probeFolder.mockResolvedValue(okProbe);
    const { result } = renderHook(() => useSetupFlow());

    act(() => {
      result.current.checkFolder("C:/Users/me/HSE");
    });

    await waitFor(() => {
      expect(result.current.status).toBe("probed");
    });
    expect(result.current.probe?.entries.map((e) => e.name)).toEqual([
      "diploma",
      "coursework",
    ]);
    expect(mocked.probeFolder).toHaveBeenCalledWith("C:/Users/me/HSE");
  });

  it("surfaces a rejected apply instead of waiting for a restart that never happens", async () => {
    mocked.apply.mockResolvedValue({
      applied: false,
      error_code: "not_absolute",
      probe: null,
    });
    const { result } = renderHook(() => useSetupFlow());

    act(() => {
      result.current.apply("../data");
    });

    await waitFor(() => {
      expect(result.current.status).toBe("failed");
    });
    expect(result.current.errorCode).toBe("not_absolute");
    // Опрос состояния не начинался: перезапускать нечего.
    expect(mocked.status).not.toHaveBeenCalled();
  });

  it("keeps polling through the offline window while the container is recreated", async () => {
    mocked.apply.mockResolvedValue({
      applied: true,
      error_code: null,
      probe: okProbe,
    });
    // Первые опросы падают — контейнера в этот момент действительно нет.
    mocked.status
      .mockRejectedValueOnce(new Error("offline"))
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue({
        is_ready: true,
        deployment_mode: "all-in-one",
        checks: [],
        compose_project: null,
        can_self_apply: true,
        app_version: "0.1.0",
      });

    // Только reload: window.location — экземпляр класса, и распылять его в
    // литерал нельзя, прототип потеряется. Поток трогает ровно этот метод.
    const reload = vi.fn();
    vi.stubGlobal("location", { href: window.location.href, reload });

    const { result } = renderHook(() => useSetupFlow());

    act(() => {
      result.current.apply("C:/Users/me/HSE");
    });

    await waitFor(() => {
      expect(result.current.status).toBe("restarting");
    });
    await waitFor(
      () => {
        expect(result.current.status).toBe("done");
      },
      { timeout: 15_000 },
    );
    // reload приходит через RELOAD_DELAY_MS после «done» — дефолтного 1s waitFor
    // впритык, на нагруженном CI-раннере не хватает.
    await waitFor(
      () => {
        expect(reload).toHaveBeenCalled();
      },
      { timeout: 5_000 },
    );

    vi.unstubAllGlobals();
  }, 20_000);
});
