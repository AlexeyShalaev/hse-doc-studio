import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { I18nextProvider } from "react-i18next";
import { RouterProvider, createMemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient, setCsrfToken } from "@shared/api";
import { i18n } from "@shared/lib";
import { AuthLayout } from "@widgets/AuthLayout";
import { LoginPage } from "@pages/LoginPage";
import { FirstRunPage } from "@pages/FirstRunPage";
import { RootLayout } from "./RootLayout";

vi.mock("@features/agent-chat", () => ({ SystemChatPanel: () => null }));
vi.mock("@widgets/CommandPalette", () => ({ CommandPalette: () => null }));
vi.mock("@widgets/DockerStatusBanner", () => ({
  DockerStatusBanner: () => <div data-testid="docker-banner" />,
}));
vi.mock("@widgets/StartupChecks", () => ({
  StartupChecks: () => <div data-testid="startup-checks" />,
}));
vi.mock("@pages/SetupPage", () => ({
  SetupPage: () => <div data-testid="setup-page" />,
}));

const fixture = (name: string): unknown =>
  JSON.parse(
    readFileSync(
      join(
        import.meta.dirname,
        "../../../..",
        "contracts/server/fixtures/Bootstrap",
        `${name}.json`,
      ),
      "utf8",
    ),
  );

// Ответы по адресам; всё остальное падает, чтобы лишние запросы были видны.
const mockApi = (replies: Record<string, unknown>) => {
  const calls: string[] = [];
  vi.spyOn(apiClient, "get").mockImplementation((url) => {
    calls.push(url);
    const reply = replies[url];
    if (reply instanceof ApiError) return Promise.reject(reply);
    if (reply === undefined) {
      return Promise.reject(new ApiError("unexpected", "unknown_error", 500));
    }
    return Promise.resolve({ data: reply, config: { url } });
  });
  return calls;
};

const renderAt = (path: string) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter(
    [
      {
        element: <RootLayout />,
        children: [
          {
            element: <AuthLayout />,
            children: [
              { path: "/login", element: <LoginPage /> },
              { path: "/first-run", element: <FirstRunPage /> },
            ],
          },
          { path: "/", element: <div data-testid="home" /> },
          { path: "/projects/:id", element: <div data-testid="project" /> },
        ],
      },
    ],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>
        <RouterProvider router={router} />
      </I18nextProvider>
    </QueryClientProvider>,
  );
  return router;
};

const NOT_FOUND = new ApiError("nf", "unknown_error", 404);

describe("RootLayout gate", () => {
  beforeEach(() => {
    setCsrfToken(null);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows a spinner, not the app, until bootstrap answers", () => {
    vi.spyOn(apiClient, "get").mockReturnValue(new Promise(() => undefined));
    renderAt("/");
    expect(screen.getByTestId("server-gate-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("home")).not.toBeInTheDocument();
  });

  it("redirects an anonymous visitor to /login?next= without local requests", async () => {
    const calls = mockApi({
      "/session/bootstrap": fixture("server_anonymous"),
    });
    const router = renderAt("/projects/x");
    await waitFor(() => {
      expect(screen.getByTestId("auth-screen-login")).toBeInTheDocument();
    });
    expect(router.state.location.pathname).toBe("/login");
    expect(router.state.location.search).toBe(
      `?next=${encodeURIComponent("/projects/x")}`,
    );
    expect(screen.getByTestId("auth-layout")).toBeInTheDocument();
    expect(calls).toEqual(["/session/bootstrap"]);
    expect(screen.queryByTestId("docker-banner")).not.toBeInTheDocument();
    expect(screen.queryByTestId("startup-checks")).not.toBeInTheDocument();
  });

  it("leads to /first-run from any route when the admin is missing", async () => {
    const calls = mockApi({
      "/session/bootstrap": fixture("server_needs_admin"),
    });
    const router = renderAt("/projects/x");
    await waitFor(() => {
      expect(screen.getByTestId("auth-screen-firstRun")).toBeInTheDocument();
    });
    expect(router.state.location.pathname).toBe("/first-run");
    expect(calls).not.toContain("/setup/status");
  });

  it("opens the app for a signed-in user with no setup or docker requests", async () => {
    const calls = mockApi({ "/session/bootstrap": fixture("server_user") });
    renderAt("/projects/x");
    await waitFor(() => {
      expect(screen.getByTestId("project")).toBeInTheDocument();
    });
    expect(calls).toEqual(["/session/bootstrap"]);
    expect(screen.queryByTestId("docker-banner")).not.toBeInTheDocument();
    expect(screen.queryByTestId("startup-checks")).not.toBeInTheDocument();
    expect(screen.queryByTestId("setup-page")).not.toBeInTheDocument();
  });

  it("sends a signed-in user from /login to the app", async () => {
    mockApi({ "/session/bootstrap": fixture("server_user") });
    const router = renderAt("/login?next=%2Fprojects%2Fa");
    await waitFor(() => {
      expect(screen.getByTestId("project")).toBeInTheDocument();
    });
    expect(router.state.location.pathname).toBe("/projects/a");
  });

  it("shows the retry screen when the server does not answer", async () => {
    mockApi({
      "/session/bootstrap": new ApiError("down", "unknown_error", 503),
    });
    renderAt("/");
    await waitFor(() => {
      expect(screen.getByTestId("server-unavailable")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("home")).not.toBeInTheDocument();
  });

  it("keeps local mode as before: setup status, banner and checks", async () => {
    const calls = mockApi({
      "/session/bootstrap": NOT_FOUND,
      "/setup/status": {
        is_ready: true,
        deployment_mode: "native",
        checks: [],
        can_self_apply: true,
        app_version: "1",
      },
    });
    renderAt("/");
    await waitFor(() => {
      expect(screen.getByTestId("home")).toBeInTheDocument();
    });
    expect(screen.getByTestId("docker-banner")).toBeInTheDocument();
    expect(screen.getByTestId("startup-checks")).toBeInTheDocument();
    await waitFor(() => {
      expect(calls).toContain("/setup/status");
    });
  });

  it("shows the setup wizard in local mode when the install is not ready", async () => {
    mockApi({
      "/session/bootstrap": NOT_FOUND,
      "/setup/status": {
        is_ready: false,
        deployment_mode: "native",
        checks: [],
        can_self_apply: true,
        app_version: "1",
      },
    });
    renderAt("/");
    await waitFor(() => {
      expect(screen.getByTestId("setup-page")).toBeInTheDocument();
    });
  });

  it("does not expose sign-in screens in local mode", async () => {
    mockApi({
      "/session/bootstrap": NOT_FOUND,
      "/setup/status": {
        is_ready: true,
        deployment_mode: "native",
        checks: [],
        can_self_apply: true,
        app_version: "1",
      },
    });
    const router = renderAt("/login");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });
  });
});
