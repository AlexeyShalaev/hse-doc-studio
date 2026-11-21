import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { gitRemoteApi, type GitCredential } from "@entities/git-remote";
import {
  PackOfficialSchema,
  PackWorkspaceSchema,
  packStudioApi,
  type PackOfficial,
  type PackWorkspace,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { WorkspacesView } from "./WorkspacesView";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-studio/fixtures",
);
const read = (dir: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8"));
const official = (name: string): PackOfficial =>
  PackOfficialSchema.parse(read("PackOfficial", name));
const WORKSPACE = PackWorkspaceSchema.parse(
  read("PackWorkspace", "git_official"),
);

const credential = (id: string, host: string): GitCredential => ({
  id,
  kind: "pat",
  label: `Токен ${id}`,
  host,
  status: "ok",
  created_at: "2026-11-15T09:00:00Z",
  used_by: [],
});

const GITLAB = credential("gl", "gitlab.example.org");
const FRESH = credential("fresh", "github.com");

const checked = (
  sufficiency: string,
  scopes: string[],
  missing: string[] = [],
) => ({
  credential: FRESH,
  provider_info: { id: "github", detected_by: "host", version: null },
  token_info: { login: "anna", scopes, expires_at: null, sufficiency, missing },
});

// Окружение окна без токена GitHub: список доступов, настройки серверов, хранилище.
const noGithubToken = () => {
  vi.spyOn(packStudioApi, "official").mockResolvedValue(official("available"));
  vi.spyOn(gitRemoteApi, "listHostSettings").mockResolvedValue([]);
  vi.spyOn(gitRemoteApi, "getSecretsStatus").mockResolvedValue({
    ok: true,
    source: "file",
    permissions_enforced: true,
    credentials_total: 1,
    credentials_unreadable: 0,
    data_dir_shared_folder: null,
  });
  return vi.spyOn(gitRemoteApi, "listCredentials");
};

const tokenField = (): HTMLInputElement => {
  const field = screen.getByLabelText("Токен");
  if (!(field instanceof HTMLInputElement)) throw new Error("нет поля");
  return field;
};

// Пустой список: три пути подключения, официальный среди них (если установка его знает).
const mount = (onOpen = vi.fn(), existing: PackWorkspace[] = []) => {
  vi.spyOn(packStudioApi, "workspaces").mockResolvedValue(existing);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <WorkspacesView onOpen={onOpen} allowFolder={false} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return onOpen;
};

describe("официальные шаблоны: подключение", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("установка без официального репозитория: этого пути нет, остаётся свой репозиторий", async () => {
    const info = vi
      .spyOn(packStudioApi, "official")
      .mockResolvedValue(official("hidden"));
    mount();
    await waitFor(() => {
      expect(info).toHaveBeenCalled();
    });
    expect(await screen.findByTestId("ws-path-git")).toBeInTheDocument();
    expect(screen.queryByTestId("ws-path-official")).not.toBeInTheDocument();
  });

  it("официальное пространство уже подключено: оно в списке, пути подключения нет", async () => {
    const data = official("existing");
    vi.spyOn(packStudioApi, "official").mockResolvedValue(data);
    mount(vi.fn(), [WORKSPACE]);
    expect(await screen.findByTestId("ws-list")).toBeInTheDocument();
    expect(screen.queryByTestId("ws-path-official")).not.toBeInTheDocument();
    expect(screen.queryByTestId("official-dialog")).not.toBeInTheDocument();
  });

  it("свой токен: в списке только доступы хоста репозитория, бота нет", async () => {
    vi.spyOn(packStudioApi, "official").mockResolvedValue(
      official("available"),
    );
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([
      credential("gl", "gitlab.example.org"),
      credential("gh", "github.com"),
    ]);
    const open = vi
      .spyOn(packStudioApi, "openOfficial")
      .mockResolvedValue(WORKSPACE);
    const onOpen = mount();
    await userEvent.click(await screen.findByTestId("ws-connect-official"));
    expect(
      await screen.findByTestId("official-access-token"),
    ).toHaveTextContent("форк");
    expect(screen.queryByTestId("official-access-bot")).not.toBeInTheDocument();
    expect(screen.getByTestId("official-dialog")).not.toHaveTextContent(
      "служебный аккаунт",
    );
    await userEvent.click(screen.getByTestId("official-submit"));
    await waitFor(() => {
      expect(open).toHaveBeenCalledWith({ credential_id: "gh" });
    });
    expect(onOpen).toHaveBeenCalledWith(WORKSPACE.id);
  });

  it("нет токена GitHub: поле токена в окне, подсказка про классический public_repo", async () => {
    noGithubToken().mockResolvedValue([GITLAB]);
    mount();
    await userEvent.click(await screen.findByTestId("ws-connect-official"));
    expect(await screen.findByTestId("official-nothing")).toHaveTextContent(
      "нужен ваш токен GitHub",
    );
    const dialog = screen.getByTestId("official-dialog");
    // Поле есть прямо в окне, токен не виден на экране.
    expect(tokenField()).toHaveAttribute("type", "password");
    expect(screen.getByTestId("add-token-submit")).toBeDisabled();
    expect(screen.getByTestId("official-submit")).toBeDisabled();
    // Классический токен с public_repo и описанием, без «Only select repositories».
    const link = await screen.findByTestId("token-create-link");
    expect(link.getAttribute("href")).toMatch(
      /^https:\/\/github\.com\/settings\/tokens\/new\?scopes=public_repo&description=/,
    );
    expect(dialog).toHaveTextContent("public_repo");
    expect(screen.getByTestId("github-fork-note")).toHaveTextContent("форк");
    expect(screen.queryByTestId("github-repo-note")).not.toBeInTheDocument();
    expect(dialog).not.toHaveTextContent("Only select repositories");
    expect(dialog).not.toHaveTextContent("check-runs");
    // Точный токен остаётся вариантом для владельца репозитория.
    expect(screen.getByTestId("token-fallback")).toHaveTextContent(
      "владелец или сопровождающий",
    );
    expect(screen.queryByTestId("token-broad-warning")).not.toBeInTheDocument();
    // Вторичная ссылка на «Доступы git» осталась.
    expect(
      screen.getByRole("link", { name: "Открыть «Доступы git»" }),
    ).toHaveAttribute("href", "/settings/git-access");
  });

  it("токен из окна: проверка под packs_fork, доступ выбран, кнопка включена", async () => {
    noGithubToken()
      .mockResolvedValueOnce([GITLAB])
      .mockResolvedValue([GITLAB, FRESH]);
    const create = vi
      .spyOn(gitRemoteApi, "createCredential")
      .mockResolvedValue(FRESH);
    const check = vi
      .spyOn(gitRemoteApi, "checkCredential")
      .mockResolvedValue(checked("sufficient", ["public_repo"]));
    const open = vi
      .spyOn(packStudioApi, "openOfficial")
      .mockResolvedValue(WORKSPACE);
    const onOpen = mount();
    await userEvent.click(await screen.findByTestId("ws-connect-official"));
    await screen.findByTestId("official-nothing");
    await userEvent.type(tokenField(), "ghp_secret");
    await userEvent.click(screen.getByTestId("add-token-submit"));
    await waitFor(() => {
      expect(create).toHaveBeenCalledWith({
        kind: "pat",
        label: "GitHub, github.com",
        host: "github.com",
        token: "ghp_secret",
      });
    });
    expect(check).toHaveBeenCalledWith(FRESH.id, "packs_fork");
    expect(
      await screen.findByTestId("official-token-added"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("official-nothing")).not.toBeInTheDocument();
    const submit = screen.getByTestId("official-submit");
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    await waitFor(() => {
      expect(open).toHaveBeenCalledWith({ credential_id: FRESH.id });
    });
    expect(onOpen).toHaveBeenCalledWith(WORKSPACE.id);
  });

  it("токен не принят: понятная ошибка у поля, доступ удалён, открыть нельзя", async () => {
    noGithubToken().mockResolvedValue([GITLAB]);
    vi.spyOn(gitRemoteApi, "createCredential").mockResolvedValue(FRESH);
    vi.spyOn(gitRemoteApi, "checkCredential").mockRejectedValue(
      new ApiError("Bad credentials", "auth_failed", 401),
    );
    const remove = vi
      .spyOn(gitRemoteApi, "deleteCredential")
      .mockResolvedValue(undefined);
    mount();
    await userEvent.click(await screen.findByTestId("ws-connect-official"));
    await screen.findByTestId("official-nothing");
    await userEvent.type(tokenField(), "ghp_wrong");
    await userEvent.click(screen.getByTestId("add-token-submit"));
    const form = screen.getByTestId("add-token-form");
    expect(
      await within(form).findByTestId("token-check-auth_failed"),
    ).toHaveTextContent("Сервер не принял токен");
    expect(remove).toHaveBeenCalledWith(FRESH.id);
    // Токен не остаётся в поле после запроса.
    expect(tokenField()).toHaveValue("");
    expect(screen.getByTestId("official-submit")).toBeDisabled();
    expect(
      screen.queryByTestId("official-token-added"),
    ).not.toBeInTheDocument();
  });

  it("мало прав (нет public_repo): ошибка с недостающим правом, доступ не сохранён", async () => {
    noGithubToken().mockResolvedValue([GITLAB]);
    vi.spyOn(gitRemoteApi, "createCredential").mockResolvedValue(FRESH);
    vi.spyOn(gitRemoteApi, "checkCredential").mockResolvedValue(
      checked("too_narrow", ["read:user"], ["public_repo"]),
    );
    const remove = vi
      .spyOn(gitRemoteApi, "deleteCredential")
      .mockResolvedValue(undefined);
    mount();
    await userEvent.click(await screen.findByTestId("ws-connect-official"));
    await screen.findByTestId("official-nothing");
    await userEvent.type(tokenField(), "ghp_narrow");
    await userEvent.click(screen.getByTestId("add-token-submit"));
    expect(
      await screen.findByTestId("token-check-too_narrow"),
    ).toHaveTextContent("public_repo");
    expect(remove).toHaveBeenCalledWith(FRESH.id);
    expect(screen.getByTestId("official-submit")).toBeDisabled();
  });
});
