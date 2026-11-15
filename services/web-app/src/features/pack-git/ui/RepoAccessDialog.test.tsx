import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { gitRemoteApi, type GitCredential } from "@entities/git-remote";
import type { PackWorkspace } from "@entities/pack-studio";
import { i18n } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { RepoAccessDialog } from "./RepoAccessDialog";

const NOW = "2026-11-15T09:00:00Z";

const CREDENTIAL: GitCredential = {
  id: "cred-1",
  kind: "pat",
  label: "GitHub паки",
  host: "github.com",
  status: "ok",
  token_family: "github_pat",
  created_at: NOW,
  used_by: [],
};

const WORKSPACE: PackWorkspace = {
  id: "ws-1",
  kind: "git",
  label: "e2e/packs",
  state: "ready",
  busy: false,
  packs_path: "packs",
  url: "https://github.com/e2e/packs.git",
  credential_id: CREDENTIAL.id,
  service_access: false,
  insecure_http: false,
  folder: null,
  base_branch: "master",
  base_sha: null,
  fetched_at: NOW,
  work_branch: null,
  pr_url: null,
  pr_number: null,
  ci_status: null,
  fork_url: null,
  pushed_sha: null,
  error: null,
  created_at: NOW,
  updated_at: NOW,
};

const mount = (workspace: PackWorkspace) =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <RepoAccessDialog workspace={workspace} isOpen onClose={vi.fn()} />
    </QueryClientProvider>,
  );

describe("доступ пространства к репозиторию", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("личный токен проверяется под профиль прав packs", async () => {
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([CREDENTIAL]);
    vi.spyOn(gitRemoteApi, "listHostSettings").mockResolvedValue([]);
    const check = vi.spyOn(gitRemoteApi, "checkCredential").mockResolvedValue({
      credential: CREDENTIAL,
      provider_info: { id: "github", detected_by: "host", version: null },
      token_info: {
        login: "ivanov",
        scopes: ["contents:write"],
        expires_at: null,
        sufficiency: "too_narrow",
        missing: ["pull_requests:write"],
      },
    });
    mount(WORKSPACE);
    expect(
      await screen.findByTestId("git-access-credential"),
    ).toHaveTextContent("GitHub паки");
    await userEvent.click(screen.getByTestId("credential-check"));
    await waitFor(() => {
      expect(check).toHaveBeenCalledWith(CREDENTIAL.id, "packs");
    });
    expect(
      await screen.findByTestId("token-check-too_narrow"),
    ).toHaveTextContent("pull_requests:write");
  });

  it("официальные паки: проверка и памятка под packs_fork (классический public_repo)", async () => {
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([CREDENTIAL]);
    vi.spyOn(gitRemoteApi, "listHostSettings").mockResolvedValue([]);
    const check = vi.spyOn(gitRemoteApi, "checkCredential").mockResolvedValue({
      credential: CREDENTIAL,
      provider_info: { id: "github", detected_by: "host", version: null },
      token_info: {
        login: "ivanov",
        scopes: ["public_repo"],
        expires_at: null,
        sufficiency: "sufficient",
        missing: [],
      },
    });
    mount({ ...WORKSPACE, official: true });
    await userEvent.click(await screen.findByTestId("credential-check"));
    await waitFor(() => {
      expect(check).toHaveBeenCalledWith(CREDENTIAL.id, "packs_fork");
    });
    expect(
      await screen.findByTestId("token-check-sufficient"),
    ).toBeInTheDocument();
    const link = screen.getByTestId("token-create-link");
    expect(link.getAttribute("href")).toContain("scopes=public_repo");
    // Поля токена тут нет: шаг «Вставьте» ведёт к кнопке замены.
    expect(screen.getByTestId("token-helper-steps")).toHaveTextContent(
      "Заменить токен",
    );
  });

  it("без токена: пояснение и памятка о токене с правами packs", async () => {
    vi.spyOn(gitRemoteApi, "listHostSettings").mockResolvedValue([]);
    mount({ ...WORKSPACE, credential_id: null });
    expect(await screen.findByTestId("git-access")).toHaveTextContent(
      "У пространства нет токена",
    );
    expect(screen.getByTestId("token-link-card")).toBeInTheDocument();
    expect(screen.getByTestId("token-helper-steps")).not.toHaveTextContent(
      "поле ниже",
    );
  });
});
