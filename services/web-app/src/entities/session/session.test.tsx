import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient, getCsrfToken, setCsrfToken } from "@shared/api";
import { i18n } from "@shared/lib";
import {
  LOCAL_BOOTSTRAP,
  RequireCapability,
  ServerUnavailable,
  useBootstrap,
  useSessionIdentityGuard,
} from "./index";

const fixture = (name: string): unknown =>
  JSON.parse(
    readFileSync(
      join(
        import.meta.dirname,
        "../../../../..",
        "contracts/server/fixtures/Bootstrap",
        `${name}.json`,
      ),
      "utf8",
    ),
  );

const wrap = (children: ReactNode) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
    </QueryClientProvider>
  );
};

const Probe = () => {
  const { data, isError } = useBootstrap();
  return (
    <div data-testid="probe">{isError ? "error" : (data?.mode ?? "…")}</div>
  );
};

describe("session bootstrap", () => {
  beforeEach(() => {
    setCsrfToken(null);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("parses the contract fixture and hands its CSRF token to the transport", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: fixture("server_user"),
      config: { url: "/session/bootstrap" },
    });
    render(wrap(<Probe />));
    await waitFor(() => {
      expect(screen.getByTestId("probe")).toHaveTextContent("server");
    });
    expect(getCsrfToken()).toBe("Wm3x0Qk7bVfN1c8RtYhA4uLsJp2eDg6o");
  });

  it("falls back to local capabilities when the backend has no bootstrap", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(
      new ApiError("nf", "unknown_error", 404),
    );
    render(wrap(<Probe />));
    await waitFor(() => {
      expect(screen.getByTestId("probe")).toHaveTextContent("local");
    });
    expect(LOCAL_BOOTSTRAP.capabilities.admin).toBe(false);
    expect(getCsrfToken()).toBeNull();
  });

  it("surfaces other failures instead of pretending to be local", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(
      new ApiError("down", "unknown_error", 503),
    );
    render(wrap(<Probe />));
    await waitFor(() => {
      expect(screen.getByTestId("probe")).toHaveTextContent("error");
    });
  });
});

describe("RequireCapability", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const mount = (capability: "admin" | "fs_browse") =>
    render(
      wrap(
        <RequireCapability
          capability={capability}
          fallback={<span data-testid="no">no</span>}
        >
          <span data-testid="yes">yes</span>
        </RequireCapability>,
      ),
    );

  it("shows a spinner, then children when the capability is on", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: fixture("server_admin"),
      config: {},
    });
    mount("admin");
    expect(
      screen.getByTestId("require-capability-loading"),
    ).toBeInTheDocument();
    expect(await screen.findByTestId("yes")).toBeInTheDocument();
  });

  it("shows the fallback when the capability is off", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: fixture("server_user"),
      config: {},
    });
    mount("admin");
    expect(await screen.findByTestId("no")).toBeInTheDocument();
    expect(screen.queryByTestId("yes")).toBeNull();
  });
});

describe("ServerUnavailable", () => {
  it.each(["ru", "en"])("renders in %s and retries", async (lng) => {
    await i18n.changeLanguage(lng);
    const onRetry = vi.fn();
    render(wrap(<ServerUnavailable onRetry={onRetry} />));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("server-unavailable-retry"));
    expect(onRetry).toHaveBeenCalledTimes(1);
    await i18n.changeLanguage("ru");
  });

  it("disables retry while retrying", () => {
    render(wrap(<ServerUnavailable onRetry={() => undefined} retrying />));
    expect(screen.getByTestId("server-unavailable-retry")).toBeDisabled();
  });
});

describe("useSessionIdentityGuard", () => {
  const Guard = () => {
    useSessionIdentityGuard();
    return null;
  };

  it("clears user-scoped cache when the signed-in user disappears", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({
      data: fixture("server_user"),
      config: {},
    });
    client.setQueryData(["projects", "list"], ["A"]);
    render(
      <QueryClientProvider client={client}>
        <Guard />
      </QueryClientProvider>,
    );
    await waitFor(() => {
      expect(client.getQueryData(["session", "bootstrap"])).toBeDefined();
    });
    expect(client.getQueryData(["projects", "list"])).toEqual(["A"]);

    get.mockResolvedValue({ data: fixture("server_anonymous"), config: {} });
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["session", "bootstrap"] });
    });
    await waitFor(() => {
      expect(client.getQueryData(["projects", "list"])).toBeUndefined();
    });
    expect(client.getQueryData(["session", "bootstrap"])).toBeDefined();
    get.mockRestore();
  });
});
