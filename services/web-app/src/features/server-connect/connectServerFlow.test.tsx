import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api";
import { i18n } from "@shared/lib";
import { ConnectServerFlow } from "./index";

// Список локальных проектов: есть ли уже этот проект у человека.
const local = vi.hoisted(() => ({ projects: [] as { id: string }[] }));
vi.mock("@entities/project", () => ({
  useProjects: () => ({ data: local.projects }),
}));

const ID = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b";
const SERVER = "https://studio.example.org";
const CHECK = {
  server_url: SERVER,
  server_version: "0.3.0",
  local_version: "0.3.1",
  compat: "compatible",
  credential_id: null,
  account_name: null,
  state: null,
};
const LOGIN = {
  login_id: "gsl_1",
  server_url: SERVER,
  state: "pending",
  user_code: "BCDF-2345",
  verification_uri_complete: `${SERVER}/device?code=BCDF-2345`,
  expires_at: null,
  credential_id: null,
  code: null,
};

type Routes = { check?: object; loginState?: object };

const mount = (
  target: { server: string | null; projectId: string | null },
  routes: Routes = {},
) => {
  const get = vi.spyOn(apiClient, "get").mockImplementation((url: string) => {
    if (url === "/git/servers/check")
      return Promise.resolve({ data: routes.check ?? CHECK });
    if (url.startsWith("/git/servers/login/"))
      return Promise.resolve({ data: routes.loginState ?? LOGIN });
    return Promise.reject(new Error(`unexpected ${url}`));
  });
  const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: LOGIN });
  const onNavigate = vi.fn();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <ConnectServerFlow
            target={target}
            clientName="Студия на этом компьютере"
            onNavigate={onNavigate}
          />
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
  return { get, post, onNavigate };
};

describe("ConnectServerFlow", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    local.projects = [];
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("asks for the address when the link carried none", async () => {
    const user = userEvent.setup();
    const { get } = mount({ server: null, projectId: null });
    await user.type(screen.getByTestId("connect-server-url"), SERVER);
    await user.click(screen.getByTestId("connect-server-check"));
    expect(await screen.findByTestId("connect-server-card")).toHaveTextContent(
      "studio.example.org",
    );
    expect(get).toHaveBeenCalledWith(
      "/git/servers/check",
      expect.objectContaining({ params: { url: SERVER } }),
    );
  });

  it("starts the device login in one click and shows the code", async () => {
    const user = userEvent.setup();
    const { post } = mount({ server: SERVER, projectId: null });
    await user.click(await screen.findByTestId("connect-server-login"));
    expect(
      await screen.findByTestId("git-server-login-user-code"),
    ).toHaveTextContent("BCDF");
    expect(post).toHaveBeenCalledWith(
      "/git/servers/login",
      { server_url: SERVER, client_name: "Студия на этом компьютере" },
      expect.anything(),
    );
  });

  it.each([
    ["local_older", /старше сервера/],
    ["local_newer", /новее сервера/],
  ])("warns about %s versions", async (compat, text) => {
    mount(
      { server: SERVER, projectId: null },
      { check: { ...CHECK, compat, local_version: "0.2.0" } },
    );
    expect(
      await screen.findByTestId("connect-server-compat"),
    ).toHaveTextContent(text);
  });

  it("clones the project with the saved access when already signed in", async () => {
    const user = userEvent.setup();
    const { onNavigate } = mount(
      { server: SERVER, projectId: ID },
      {
        check: {
          ...CHECK,
          credential_id: "cred-1",
          account_name: "Анна",
          state: "ok",
        },
      },
    );
    expect(await screen.findByText("Вы уже вошли как Анна")).toBeVisible();
    await user.click(screen.getByTestId("connect-server-continue"));
    await waitFor(() => {
      expect(onNavigate).toHaveBeenCalledTimes(1);
    });
    const path = new URL(String(onNavigate.mock.calls[0]?.[0]), "http://x");
    expect(path.pathname).toBe("/wizard");
    expect(path.searchParams.get("url")).toBe(`${SERVER}/git/${ID}.git`);
    expect(path.searchParams.get("credential")).toBe("cred-1");
  });

  it("opens the project when it is already here", async () => {
    const user = userEvent.setup();
    local.projects = [{ id: ID }];
    const { onNavigate } = mount(
      { server: SERVER, projectId: ID },
      { check: { ...CHECK, credential_id: "cred-1", state: "ok" } },
    );
    await user.click(await screen.findByTestId("connect-server-continue"));
    await waitFor(() => {
      expect(onNavigate).toHaveBeenCalledWith(`/projects/${ID}/documents`);
    });
  });
});
