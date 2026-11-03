import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api";
import { i18n } from "@shared/lib/i18n";
import { CloudBuildHint } from "./CloudBuildHint";

const caps = vi.hoisted(() => ({ lacking: new Set<string>() }));
vi.mock("@entities/session", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/session")),
  useCapabilities: () => ({
    has: (name: string) => !caps.lacking.has(name),
    lacks: (name: string) => caps.lacking.has(name),
  }),
}));

const SERVER = {
  credential_id: "c1",
  server_url: "https://studio.example.org",
  host: "studio.example.org",
  account_name: "Анна",
  scopes: ["git:read", "git:write"],
  expires_at: null,
  state: "ok",
};

type Reply = { servers: object[]; available: boolean };

const mount = ({ servers, available }: Reply) => {
  const get = vi.spyOn(apiClient, "get").mockImplementation((url: string) => {
    if (url === "/git/servers")
      return Promise.resolve({ data: { items: servers } });
    if (url === "/projects/p1/git")
      return Promise.resolve({
        data: {
          connected: false,
          ui_state: "no_remote",
          relation: "none",
          ahead: 0,
          behind: 0,
          behind_files: 0,
          health: "ok",
          profile_ok: true,
          incoming: [],
          outgoing: [],
          auto_fetch: { enabled: false, interval_s: 0 },
          bot_authored_commits: 0,
          auto_sync: { enabled: false, explicit: false },
          pdf_upload: { enabled: available, available },
        },
      });
    return Promise.reject(new Error(`unexpected ${url}`));
  });
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <CloudBuildHint projectId="p1" />
    </QueryClientProvider>,
  );
  return get;
};

describe("CloudBuildHint", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    caps.lacking = new Set();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("tells that the PDF stays here and links to the docs when the project is not in the cloud", async () => {
    mount({ servers: [SERVER], available: false });
    const hint = await screen.findByTestId("cloud-build-hint");
    expect(hint).toHaveTextContent(
      "Проект не подключён к облаку, PDF останется на этом компьютере.",
    );
    expect(screen.getByTestId("cloud-build-hint-docs")).toHaveAttribute(
      "href",
      "https://alexeyshalaev.github.io/hse-doc-studio/start/local-from-cloud/",
    );
  });

  it("links to the English docs in English", async () => {
    await i18n.changeLanguage("en");
    mount({ servers: [SERVER], available: false });
    expect(await screen.findByTestId("cloud-build-hint-docs")).toHaveAttribute(
      "href",
      "https://alexeyshalaev.github.io/hse-doc-studio/en/start/local-from-cloud/",
    );
  });

  it("is silent for a project that already goes to the cloud", async () => {
    const get = mount({ servers: [SERVER], available: true });
    await waitFor(() => {
      expect(get).toHaveBeenCalledWith("/projects/p1/git", expect.anything());
    });
    expect(screen.queryByTestId("cloud-build-hint")).toBeNull();
  });

  it("is silent when the Studio is not signed in to any server", async () => {
    const get = mount({ servers: [], available: false });
    await waitFor(() => {
      expect(get).toHaveBeenCalledWith("/git/servers", expect.anything());
    });
    expect(screen.queryByTestId("cloud-build-hint")).toBeNull();
  });

  it("is silent when the sign-in is no longer valid", async () => {
    const get = mount({
      servers: [{ ...SERVER, state: "revoked" }],
      available: false,
    });
    await waitFor(() => {
      expect(get).toHaveBeenCalledWith("/git/servers", expect.anything());
    });
    expect(screen.queryByTestId("cloud-build-hint")).toBeNull();
  });

  it("does not exist on a server, where local builds are not a thing", async () => {
    caps.lacking = new Set(["git_server_login"]);
    const get = mount({ servers: [SERVER], available: false });
    expect(screen.queryByTestId("cloud-build-hint")).toBeNull();
    expect(get).not.toHaveBeenCalled();
  });
});
