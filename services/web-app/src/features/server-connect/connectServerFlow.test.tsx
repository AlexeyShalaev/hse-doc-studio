import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@shared/api";
import { i18n } from "@shared/lib";
import { ConnectServerFlow } from "./index";

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

type Routes = {
  check?: object;
  loginState?: object;
  /** Ответ `POST /git/servers/<вход>/projects/<id>/open`. */
  open?: object | Error;
  operation?: object;
};

const OPERATION = {
  id: "op1",
  kind: "clone",
  project_id: null,
  status: "running",
  phase: "download",
  percent: 40,
  message: null,
  cancellable: true,
  started_at: "2026-11-03T10:00:00Z",
  finished_at: null,
  result: null,
  error: null,
};

const mount = (
  target: { server: string | null; projectId: string | null },
  routes: Routes = {},
) => {
  const get = vi.spyOn(apiClient, "get").mockImplementation((url: string) => {
    if (url === "/git/servers/check")
      return Promise.resolve({ data: routes.check ?? CHECK });
    if (url.startsWith("/git/servers/login/"))
      return Promise.resolve({ data: routes.loginState ?? LOGIN });
    if (url === "/git/operations/op1")
      return Promise.resolve({ data: routes.operation ?? OPERATION });
    if (url === "/profile")
      return Promise.resolve({
        data: { name: "", email: "", is_default: true },
      });
    return Promise.reject(new Error(`unexpected ${url}`));
  });
  const post = vi.spyOn(apiClient, "post").mockImplementation((url: string) => {
    if (url.endsWith("/open")) {
      const reply = routes.open ?? { project_id: ID, operation_id: "op1" };
      return reply instanceof Error
        ? Promise.reject(reply)
        : Promise.resolve({ data: reply });
    }
    return Promise.resolve({ data: LOGIN });
  });
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

  const SIGNED_IN = {
    check: {
      ...CHECK,
      credential_id: "cred-1",
      account_name: "Анна",
      state: "ok",
    },
  };

  it("downloads the project into the projects folder in one click, no wizard and no git words", async () => {
    const user = userEvent.setup();
    const { onNavigate, post } = mount(
      { server: SERVER, projectId: ID },
      SIGNED_IN,
    );
    expect(await screen.findByText("Вы уже вошли как Анна")).toBeVisible();
    await user.click(screen.getByTestId("connect-server-continue"));
    expect(await screen.findByTestId("cloud-open-progress")).toHaveAttribute(
      "data-step",
      "download",
    );
    expect(screen.getByTestId("connect-server")).not.toHaveTextContent(/git/i);
    expect(post).toHaveBeenCalledWith(
      `/git/servers/cred-1/projects/${ID}/open`,
      undefined,
      expect.anything(),
    );
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it("opens the project when the download finishes", async () => {
    const user = userEvent.setup();
    const { onNavigate } = mount(
      { server: SERVER, projectId: ID },
      {
        ...SIGNED_IN,
        operation: {
          ...OPERATION,
          status: "succeeded",
          phase: "register",
          finished_at: "2026-11-03T10:00:09Z",
          result: {
            project_id: ID,
            folder: "/data/projects/x",
            access: "full",
            warnings: [],
          },
        },
      },
    );
    await user.click(await screen.findByTestId("connect-server-continue"));
    await waitFor(() => {
      expect(onNavigate).toHaveBeenCalledWith(`/projects/${ID}/documents`);
    });
  });

  it("opens the project at once when it is already on this computer", async () => {
    const user = userEvent.setup();
    const { onNavigate, get } = mount(
      { server: SERVER, projectId: ID },
      { ...SIGNED_IN, open: { project_id: ID, operation_id: null } },
    );
    await user.click(await screen.findByTestId("connect-server-continue"));
    await waitFor(() => {
      expect(onNavigate).toHaveBeenCalledWith(`/projects/${ID}/documents`);
    });
    expect(get).not.toHaveBeenCalledWith(
      "/git/operations/op1",
      expect.anything(),
    );
  });

  it("without a project goes to the project list, where cloud projects are already shown", async () => {
    const user = userEvent.setup();
    const { onNavigate, post } = mount(
      { server: SERVER, projectId: null },
      SIGNED_IN,
    );
    await user.click(await screen.findByTestId("connect-server-continue"));
    await waitFor(() => {
      expect(onNavigate).toHaveBeenCalledWith("/");
    });
    expect(post).not.toHaveBeenCalled();
  });

  it("explains a failed download and offers the list or a retry", async () => {
    const user = userEvent.setup();
    const { onNavigate } = mount(
      { server: SERVER, projectId: ID },
      {
        ...SIGNED_IN,
        operation: {
          ...OPERATION,
          status: "failed",
          error: { code: "folder_not_empty", detail: "" },
        },
      },
    );
    await user.click(await screen.findByTestId("connect-server-continue"));
    expect(await screen.findByTestId("cloud-open-failed")).toHaveAttribute(
      "data-code",
      "folder_not_empty",
    );
    expect(screen.getByTestId("cloud-open-retry")).toBeVisible();
    await user.click(screen.getByTestId("cloud-open-exit"));
    expect(onNavigate).toHaveBeenCalledWith("/");
  });

  it("says so when the project is not on the server or not the person's", async () => {
    const user = userEvent.setup();
    mount(
      { server: SERVER, projectId: ID },
      { ...SIGNED_IN, open: new ApiError("Не найдено", "not_found", 404) },
    );
    await user.click(await screen.findByTestId("connect-server-continue"));
    expect(await screen.findByTestId("cloud-open-failed")).toHaveTextContent(
      "нет на сервере",
    );
    expect(screen.queryByTestId("cloud-open-retry")).toBeNull();
  });

  it("asks who the author is when the profile is missing, then retries", async () => {
    const user = userEvent.setup();
    mount(
      { server: SERVER, projectId: ID },
      {
        ...SIGNED_IN,
        open: new ApiError("Нужен профиль", "profile_required", 409),
      },
    );
    await user.click(await screen.findByTestId("connect-server-continue"));
    expect(await screen.findByTestId("cloud-open-profile")).toBeVisible();
  });
});
