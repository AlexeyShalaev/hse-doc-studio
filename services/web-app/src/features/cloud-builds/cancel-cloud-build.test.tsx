import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, type AxiosResponse } from "axios";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import { cancelErrorKey, useCloudBuildStop } from "./model/useCancelCloudBuild";

const api = vi.hoisted(() => ({
  local: vi.fn(),
  cancel: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@entities/project-build/api/buildApi", () => ({
  cloudBuildsApi: { list: vi.fn() },
  localBuildsApi: {
    list: api.local,
    fetch: vi.fn(),
    cancelCloud: api.cancel,
  },
}));
vi.mock("@entities/session", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/session")),
  useBootstrap: () => ({ data: { mode: "local" } }),
}));
vi.mock("@shared/lib", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@shared/lib")),
  toast: api.toast,
}));

const failure = (status: number | undefined) =>
  new AxiosError(
    "x",
    undefined,
    undefined,
    undefined,
    status === undefined
      ? undefined
      : ({
          status,
          data: {},
          statusText: "",
          headers: {},
          config: {},
        } as unknown as AxiosResponse),
  );

const Probe = () => {
  const stop = useCloudBuildStop("p1");
  if (!stop.isCloudRunning) return <span>idle</span>;
  return (
    <button type="button" onClick={stop.stop} disabled={stop.isStopping}>
      {stop.isStopping ? "stopping" : "stop"}
    </button>
  );
};

const mount = () =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <I18nextProvider i18n={i18n}>
        <Probe />
      </I18nextProvider>
    </QueryClientProvider>,
  );

const running = (flag: boolean) => ({
  connected: true,
  cloud_error: null,
  local_head: null,
  local_dirty: false,
  cloud_head: null,
  documents: [
    {
      doc_id: "tz",
      local: null,
      cloud: null,
      cloud_running: flag,
      studio: null,
      relation: "none",
      can_fetch: false,
    },
  ],
});

describe("stopping a cloud build from the local Studio", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    vi.clearAllMocks();
  });
  afterEach(cleanup);

  it("maps the server answer to a readable reason", () => {
    expect(cancelErrorKey(failure(403))).toBe("cancelForbidden");
    expect(cancelErrorKey(failure(401))).toBe("cancelSignIn");
    expect(cancelErrorKey(failure(501))).toBe("cancelUnsupported");
    expect(cancelErrorKey(failure(502))).toBe("cancelOffline");
    expect(cancelErrorKey(failure(undefined))).toBe("cancelOffline");
    expect(cancelErrorKey(new Error("x"))).toBe("cancelFailed");
  });

  it("shows nothing to stop while the cloud is idle", async () => {
    api.local.mockResolvedValue(running(false));
    mount();
    await waitFor(() => {
      expect(api.local).toHaveBeenCalled();
    });
    expect(screen.getByText("idle")).toBeTruthy();
  });

  it("sends the cancel and tells the result", async () => {
    api.local.mockResolvedValue(running(true));
    api.cancel.mockResolvedValue({ cancelled: 1 });
    mount();
    await userEvent.click(await screen.findByText("stop"));
    await waitFor(() => {
      expect(api.cancel).toHaveBeenCalledWith("p1", null);
    });
    await waitFor(() => {
      expect(api.toast.success).toHaveBeenCalledWith(
        "Облачная сборка остановлена",
      );
    });
  });

  it("says so when there is nothing left to stop (repeat)", async () => {
    api.local.mockResolvedValue(running(true));
    api.cancel.mockResolvedValue({ cancelled: 0 });
    mount();
    await userEvent.click(await screen.findByText("stop"));
    await waitFor(() => {
      expect(api.toast.success).toHaveBeenCalledWith(
        "Облачных сборок в работе уже нет",
      );
    });
  });

  it("reports a missing right and a lost connection", async () => {
    api.local.mockResolvedValue(running(true));
    api.cancel.mockRejectedValueOnce(failure(403));
    mount();
    await userEvent.click(await screen.findByText("stop"));
    await waitFor(() => {
      expect(api.toast.error).toHaveBeenCalledWith(
        "Нет права останавливать сборки в этом проекте",
      );
    });
    api.cancel.mockRejectedValueOnce(failure(undefined));
    await userEvent.click(await screen.findByText("stop"));
    await waitFor(() => {
      expect(api.toast.error).toHaveBeenLastCalledWith(
        expect.stringContaining("Нет связи с сервером Студии"),
      );
    });
  });
});
