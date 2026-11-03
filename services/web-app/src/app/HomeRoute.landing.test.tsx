import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { I18nextProvider } from "react-i18next";
import { RouterProvider, createMemoryRouter } from "react-router";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type Mock,
} from "vitest";
import { ApiError, apiClient, setCsrfToken } from "@shared/api";
import { i18n } from "@shared/lib";
import { AuthLayout } from "@widgets/AuthLayout";
import { LoginPage } from "@pages/LoginPage";
import { RegisterPage } from "@pages/RegisterPage";
import { HomeRoute } from "./HomeRoute";
import { RootLayout } from "./RootLayout";

vi.mock("@features/agent-chat", () => ({ SystemChatPanel: () => null }));
vi.mock("@widgets/CommandPalette", () => ({ CommandPalette: () => null }));
vi.mock("@widgets/DockerStatusBanner", () => ({
  DockerStatusBanner: () => <div data-testid="docker-banner" />,
}));
vi.mock("@widgets/StartupChecks", () => ({
  StartupChecks: () => <div data-testid="startup-checks" />,
}));
vi.mock("@widgets/AppTitlebar", () => ({
  AppTitlebar: () => <div data-testid="titlebar" />,
}));
vi.mock("@pages/SetupPage", () => ({
  SetupPage: () => <div data-testid="setup-page" />,
}));

type Json = Record<string, unknown>;

const fixture = (name: string): Json =>
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
  ) as Json;

const withAuth = (base: Json, auth: Json): Json => ({
  ...base,
  auth: { ...(base.auth as Json), ...auth },
});

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

const setWide = (wide: boolean) => {
  (window.matchMedia as unknown as Mock).mockImplementation(
    (query: string) => ({
      matches: wide && query.includes("min-width: 960px"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  );
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
              { path: "/register", element: <RegisterPage /> },
            ],
          },
          {
            path: "/",
            element: <HomeRoute welcome={<div data-testid="welcome" />} />,
          },
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

// Лендинг и его словарь грузятся лениво: на нагруженной машине секунды по умолчанию мало.
const SLOW = { timeout: 8000 };

describe("landing on the home page", () => {
  beforeEach(() => {
    setCsrfToken(null);
    setWide(true);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the landing with the sign-in form next to the description to an anonymous visitor", async () => {
    const calls = mockApi({
      "/session/bootstrap": fixture("server_anonymous"),
    });
    const router = renderAt("/");

    expect(
      await screen.findByTestId("landing-page", {}, SLOW),
    ).toBeInTheDocument();
    const card = screen.getByTestId("landing-login-card");
    expect(within(card).getByTestId("login-form")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 1, name: /ГОСТ/ }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
    // Без титлбара, баннера Docker и проверок запуска, и без лишних запросов.
    expect(screen.queryByTestId("titlebar")).not.toBeInTheDocument();
    expect(screen.queryByTestId("docker-banner")).not.toBeInTheDocument();
    expect(screen.queryByTestId("welcome")).not.toBeInTheDocument();
    expect(calls).toEqual(["/session/bootstrap"]);
  });

  it("takes the installation name from the bootstrap", async () => {
    mockApi({
      "/session/bootstrap": {
        ...fixture("server_anonymous"),
        landing: { enabled: true, name: "Studio кафедры" },
      },
    });
    renderAt("/");
    await screen.findByTestId("landing-page", {}, SLOW);
    expect(screen.getAllByText(/Studio кафедры/).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(document.title).toContain("Studio кафедры");
    });
  });

  it("opens the form from the Sign in button on a narrow screen", async () => {
    setWide(false);
    mockApi({ "/session/bootstrap": fixture("server_anonymous") });
    renderAt("/");
    await screen.findByTestId("landing-page", {}, SLOW);
    expect(screen.queryByTestId("login-form")).not.toBeInTheDocument();

    await userEvent.click(screen.getByTestId("landing-login-button"));

    expect(
      await screen.findByTestId("login-form", {}, SLOW),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("offers registration only where the form would open", async () => {
    mockApi({ "/session/bootstrap": fixture("server_anonymous") });
    renderAt("/");
    const link = await screen.findByTestId("landing-register", {}, SLOW);
    expect(link).toHaveAttribute("href", "/register");
  });

  it("explains an invitation-only installation instead of a dead registration link", async () => {
    mockApi({
      "/session/bootstrap": withAuth(fixture("server_anonymous"), {
        registration_mode: "invite",
      }),
    });
    renderAt("/");
    expect(
      await screen.findByTestId("landing-invite-only", {}, SLOW),
    ).toBeVisible();
    expect(screen.queryByTestId("landing-register")).not.toBeInTheDocument();
  });

  it("keeps the return address in the single sign-on link", async () => {
    mockApi({
      "/session/bootstrap": withAuth(fixture("server_anonymous"), {
        oidc_providers: [{ id: "hse", label: "HSE ID" }],
      }),
    });
    renderAt(`/?next=${encodeURIComponent("/projects/a")}`);
    const card = await screen.findByTestId("landing-login-card", {}, SLOW);
    const sso = within(card).getByRole("link", { name: /HSE ID/ });
    expect(sso).toHaveAttribute(
      "href",
      `/api/v1/auth/oidc/hse/start?next=${encodeURIComponent("/projects/a")}`,
    );
  });

  it("does not leak the version or any server address on the page", async () => {
    mockApi({
      "/session/bootstrap": {
        ...fixture("server_anonymous"),
        version: "9.8.7",
      },
    });
    renderAt("/");
    await screen.findByTestId("landing-page", {}, SLOW);
    const text = screen.getByTestId("landing-page").textContent;
    expect(text).not.toContain("9.8.7");
    expect(text).not.toMatch(/localhost|127\.0\.0\.1/);
  });

  it("goes straight to the sign-in screen when the admin switched the landing off", async () => {
    mockApi({
      "/session/bootstrap": {
        ...fixture("server_anonymous"),
        landing: { enabled: false, name: "HSE Doc Studio" },
      },
    });
    const router = renderAt("/");
    expect(
      await screen.findByTestId("auth-screen-login", {}, SLOW),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(screen.queryByTestId("landing-page")).not.toBeInTheDocument();
  });

  it("does not show the landing to a signed-in user", async () => {
    mockApi({ "/session/bootstrap": fixture("server_user") });
    renderAt("/");
    expect(await screen.findByTestId("welcome", {}, SLOW)).toBeInTheDocument();
    expect(screen.queryByTestId("landing-page")).not.toBeInTheDocument();
  });

  it("does not show the landing in the local Studio", async () => {
    mockApi({
      "/session/bootstrap": new ApiError("nf", "unknown_error", 404),
      "/setup/status": {
        is_ready: true,
        deployment_mode: "native",
        checks: [],
        can_self_apply: true,
        app_version: "1",
      },
    });
    renderAt("/");
    expect(await screen.findByTestId("welcome", {}, SLOW)).toBeInTheDocument();
    expect(screen.queryByTestId("landing-page")).not.toBeInTheDocument();
  });

  it("keeps the direct sign-in address and its return address working", async () => {
    mockApi({ "/session/bootstrap": fixture("server_anonymous") });
    const router = renderAt(`/login?next=${encodeURIComponent("/projects/a")}`);
    expect(
      await screen.findByTestId("auth-screen-login", {}, SLOW),
    ).toBeInTheDocument();
    expect(router.state.location.search).toBe(
      `?next=${encodeURIComponent("/projects/a")}`,
    );
    expect(screen.queryByTestId("landing-page")).not.toBeInTheDocument();
  });

  it("sends a guest of a closed address to /login with ?next= as before", async () => {
    mockApi({ "/session/bootstrap": fixture("server_anonymous") });
    const router = renderAt("/projects/x");
    expect(
      await screen.findByTestId("auth-screen-login", {}, SLOW),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(router.state.location.search).toBe(
      `?next=${encodeURIComponent("/projects/x")}`,
    );
  });
});
