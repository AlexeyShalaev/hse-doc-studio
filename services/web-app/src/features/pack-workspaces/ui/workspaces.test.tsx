import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { gitRemoteApi } from "@entities/git-remote";
import {
  PackGitSchema,
  PackOfficialSchema,
  PackWorkspaceSchema,
  packStudioApi,
  packStudioKeys,
  type PackGit,
  type PackWorkspace,
} from "@entities/pack-studio";
import { i18n } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { CreateWorkspaceDialog } from "./CreateWorkspaceDialog";
import { WorkspacesView } from "./WorkspacesView";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-studio/fixtures",
);
const read = (dir: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8"));
const fixture = (name: string): PackWorkspace =>
  PackWorkspaceSchema.parse(read("PackWorkspace", name));
const gitOf = (workspace: PackWorkspace, patch: Partial<PackGit> = {}) => ({
  ...PackGitSchema.parse(read("PackGit", "detached_dirty")),
  workspace,
  ...patch,
});
const clean: Partial<PackGit> = { uncommitted: [], changed: [], dirty: false };

let lastClient: QueryClient | null = null;
const wrap = (node: React.ReactNode) => {
  const client = (lastClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  }));
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
};

/** Экран со списком: git каждого пространства подменяется по id. */
const mountView = (
  workspaces: PackWorkspace[],
  opts: {
    git?: Record<string, PackGit>;
    allowFolder?: boolean;
    lastOpenedId?: string | null;
    official?: "available" | "hidden" | "existing";
    onOpen?: (id: string) => void;
  } = {},
) => {
  vi.spyOn(packStudioApi, "workspaces").mockResolvedValue(workspaces);
  vi.spyOn(packStudioApi, "official").mockResolvedValue(
    PackOfficialSchema.parse(read("PackOfficial", opts.official ?? "hidden")),
  );
  vi.spyOn(packStudioApi, "git").mockImplementation((id) => {
    const git = opts.git?.[id];
    return git ? Promise.resolve(git) : Promise.reject(new Error("нет git"));
  });
  return wrap(
    <WorkspacesView
      onOpen={opts.onOpen ?? vi.fn()}
      allowFolder={opts.allowFolder ?? false}
      lastOpenedId={opts.lastOpenedId ?? null}
    />,
  );
};

const filled = () =>
  [...document.querySelectorAll("button.btn.primary")].map(
    (b) => b.textContent,
  );

describe("список пространств", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("пусто в локальной Студии: три пути, залит только самый простой", async () => {
    mountView([], { allowFolder: true, official: "available" });
    const paths = await screen.findByTestId("ws-paths");
    expect(
      within(paths)
        .getAllByRole("heading")
        .map((h) => h.textContent),
    ).toEqual([
      "Официальные шаблоны ВШЭ",
      "Свой репозиторий",
      "Папка на компьютере",
    ]);
    expect(within(paths).getByText("Проще всего")).toBeInTheDocument();
    expect(filled()).toEqual(["Начать"]);
    // Пустому экрану не нужна ещё одна кнопка подключения в шапке.
    expect(screen.queryByTestId("ws-connect")).not.toBeInTheDocument();
    // Пак объяснён одной фразой.
    expect(screen.getByTestId("ws-empty-lead")).toHaveTextContent(
      "Пак это набор шаблонов одной программы",
    );
  });

  it("пусто на сервере: папки нет; без официальных шаблонов остаётся свой репозиторий", async () => {
    mountView([], { allowFolder: false, official: "available" });
    expect(await screen.findByTestId("ws-path-official")).toBeInTheDocument();
    expect(screen.getByTestId("ws-path-git")).toBeInTheDocument();
    expect(screen.queryByTestId("ws-path-folder")).not.toBeInTheDocument();
    cleanup();
    mountView([], { allowFolder: false, official: "hidden" });
    expect(await screen.findByTestId("ws-path-git")).toBeInTheDocument();
    expect(screen.queryByTestId("ws-path-official")).not.toBeInTheDocument();
    expect(filled()).toEqual(["Подключить репозиторий"]);
  });

  it("статусы словами: подключаем, не удалось, папка, запрос открыт, не отправлено, без изменений", async () => {
    const cloning = fixture("git_cloning");
    const failed = { ...fixture("git_failed"), id: "failed" };
    const folder = fixture("folder");
    const request = { ...fixture("git_proposed"), id: "request" };
    const unsent = { ...fixture("git_ready"), id: "unsent" };
    const same = { ...fixture("git_ready"), id: "same" };
    mountView([cloning, failed, folder, request, unsent, same], {
      git: {
        request: gitOf(request, clean),
        unsent: gitOf(unsent),
        same: gitOf(same, clean),
      },
    });
    const card = async (id: string) =>
      within(await screen.findByTestId(`ws-card-${id}`));

    const c = await card(cloning.id);
    expect(c.getByTestId("ws-status-cloning")).toHaveTextContent("Подключаем…");
    expect(c.getByTestId("ws-wait")).toHaveTextContent("обычно до пары минут");
    expect(c.getByTestId("ws-open")).toBeDisabled();
    expect(
      c.queryByRole("button", { name: "Открыть" }),
    ).not.toBeInTheDocument();

    const f = await card("failed");
    expect(f.getByTestId("ws-status-failed")).toHaveTextContent(
      "Не удалось подключить",
    );
    // Причина по словарю ошибок и что делать, а не текст сервера.
    expect(f.getByTestId("ws-error")).toHaveTextContent(
      i18n.t("errors:code.auth_failed"),
    );
    expect(f.getByTestId("ws-failed-hint")).toHaveTextContent(
      "Проверьте адрес и доступ.",
    );

    const d = await card(folder.id);
    expect(d.getByTestId("ws-status-folder")).toHaveTextContent(
      "правки пишутся в папку",
    );
    expect(d.getByText("/Users/anna/hse-doc-studio")).toBeInTheDocument();

    const r = await card("request");
    await waitFor(() => {
      expect(r.getByTestId("ws-status-request")).toHaveTextContent(
        "запрос на слияние #412 открыт",
      );
    });
    expect(r.queryByTestId("ws-status-unsent")).not.toBeInTheDocument();

    const u = await card("unsent");
    await waitFor(() => {
      expect(u.getByTestId("ws-status-unsent")).toHaveTextContent(
        "2 изменения не отправлены",
      );
    });

    const s = await card("same");
    await waitFor(() => {
      expect(s.getByTestId("ws-status-clean")).toHaveTextContent(
        "без изменений",
      );
    });
    // «Готово» у всех одинаково больше нет.
    expect(screen.queryByText("Готово")).not.toBeInTheDocument();
  });

  it("запрос открыт и есть новые правки: обе метки", async () => {
    const request = { ...fixture("git_proposed"), id: "request" };
    mountView([request], { git: { request: gitOf(request) } });
    const card = within(await screen.findByTestId("ws-card-request"));
    expect(await card.findByTestId("ws-status-unsent")).toHaveTextContent(
      "2 новых изменения не отправлены",
    );
    expect(card.getByTestId("ws-status-request")).toBeInTheDocument();
  });

  it("строка источника без имени ветки: ветка только в подсказке", async () => {
    const official = fixture("git_official");
    mountView([official], { git: { [official.id]: gitOf(official, clean) } });
    const card = await screen.findByTestId(`ws-card-${official.id}`);
    const meta = card.querySelector(".sp-ws-meta");
    expect(meta).toHaveTextContent("Официальные шаблоны ВШЭ");
    expect(meta).not.toHaveTextContent(/ветк|master/);
    expect(meta?.getAttribute("title")).toContain(
      `Ветка в git: ${official.base_branch ?? ""}`,
    );
  });

  it("одна залитая кнопка: «Продолжить» у пространства с неотправленными правками", async () => {
    const a = { ...fixture("git_ready"), id: "a", label: "a/packs" };
    const b = { ...fixture("git_ready"), id: "b", label: "b/packs" };
    const onOpen = vi.fn();
    mountView([a, b], {
      git: { a: gitOf(a, clean), b: gitOf(b) },
      lastOpenedId: "a",
      onOpen,
    });
    const card = within(await screen.findByTestId("ws-card-b"));
    expect(await card.findByTestId("ws-continue")).toHaveTextContent(
      "Продолжить",
    );
    expect(filled()).toEqual(["Продолжить"]);
    expect(
      within(screen.getByTestId("ws-card-a")).getByRole("button", {
        name: "Открыть",
      }),
    ).toBeInTheDocument();
    await userEvent.click(card.getByTestId("ws-continue"));
    expect(onOpen).toHaveBeenCalledWith("b");
  });

  it("правок нет, но человек был здесь: «Продолжить» у последнего, в шапке не залито", async () => {
    const a = { ...fixture("git_ready"), id: "a" };
    mountView([a, fixture("folder")], {
      git: { a: gitOf(a, clean) },
      lastOpenedId: "a",
    });
    await screen.findByTestId("ws-continue");
    expect(filled()).toEqual(["Продолжить"]);
    expect(screen.getByTestId("ws-connect")).not.toHaveClass("primary");
  });

  it("никуда не заходили: главная кнопка «Подключить пространство», карточки без заливки", async () => {
    mountView([fixture("folder")]);
    await screen.findByTestId("ws-list");
    expect(filled()).toEqual(["Подключить пространство"]);
  });

  it("подключение репозитория: три клика и одно поле", async () => {
    const created = fixture("git_cloning");
    const create = vi
      .spyOn(packStudioApi, "createWorkspace")
      .mockResolvedValue(created);
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([]);
    const onOpen = vi.fn();
    mountView([fixture("folder")], { allowFolder: true, onOpen });
    // 1. «Подключить пространство».
    await userEvent.click(await screen.findByTestId("ws-connect"));
    // 2. «Свой репозиторий».
    await userEvent.click(await screen.findByTestId("ws-connect-menu-git"));
    // Одно поле на виду: адрес; остальное свёрнуто.
    const url = await screen.findByTestId("ws-create-url");
    expect(
      screen.getAllByRole("textbox").filter((el) => !el.closest("details")),
    ).toHaveLength(1);
    expect(screen.getByTestId("ws-create-more")).not.toHaveAttribute("open");
    // 3. «Подключить».
    await userEvent.click(url);
    await userEvent.paste("https://github.com/university/packs.git");
    await userEvent.click(screen.getByTestId("ws-create-submit"));
    await waitFor(() => {
      expect(create).toHaveBeenCalledWith({
        kind: "git",
        url: "https://github.com/university/packs.git",
        credential_id: null,
        base_branch: null,
        packs_path: "packs",
        label: null,
        insecure_http: false,
      });
    });
    expect(onOpen).toHaveBeenCalledWith(created.id);
  });

  it("в шапке меню путей: официальные шаблоны, свой репозиторий, папка (только локально)", async () => {
    mountView([fixture("folder")], {
      allowFolder: true,
      official: "available",
    });
    await userEvent.click(await screen.findByTestId("ws-connect"));
    expect(
      (await screen.findAllByRole("menuitem")).map((i) => i.textContent),
    ).toEqual([
      "Официальные шаблоны ВШЭ",
      "Свой репозиторий",
      "Папка на компьютере",
    ]);
  });

  it("фоновое обновление не удалось, а список уже есть: список остаётся на экране", async () => {
    const { ApiError } = await import("@shared/api");
    const folder = fixture("folder");
    mountView([folder]);
    await screen.findByTestId("ws-list");
    vi.spyOn(packStudioApi, "workspaces").mockRejectedValue(
      new ApiError("down", "internal_error", 500),
    );
    await lastClient?.refetchQueries({ queryKey: packStudioKeys.workspaces() });
    await waitFor(() => {
      expect(
        lastClient?.getQueryState(packStudioKeys.workspaces())?.status,
      ).toBe("error");
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByTestId(`ws-card-${folder.id}`)).toBeInTheDocument();
    expect(screen.queryByText("Повторить")).not.toBeInTheDocument();
  });

  it("повтор и удаление: у неудавшегося «Проверить доступ», повтор и удаление в меню", async () => {
    const failed = { ...fixture("git_failed"), id: "failed" };
    const refresh = vi
      .spyOn(packStudioApi, "refreshWorkspace")
      .mockResolvedValue({
        ...failed,
        state: "cloning",
        busy: true,
        error: null,
      });
    mountView([failed]);
    const card = within(await screen.findByTestId("ws-card-failed"));
    await userEvent.click(card.getByTestId("ws-check-access"));
    expect(await screen.findByTestId("git-access")).toBeInTheDocument();
    await userEvent.click(
      screen.getByText("Закрыть", { selector: ".modal-foot button" }),
    );
    // После проверки доступа подключение пробуется заново.
    await waitFor(() => {
      expect(refresh).toHaveBeenCalledWith("failed");
    });
    refresh.mockClear();
    await userEvent.click(card.getByTestId("ws-menu"));
    await userEvent.click(await screen.findByTestId("ws-retry"));
    expect(refresh).toHaveBeenCalledWith("failed");
  });
});

describe("удаление пространства", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });

  it("есть неотправленные правки: окно предупреждает, что они пропадут", async () => {
    const unsent = { ...fixture("git_ready"), id: "unsent" };
    mountView([unsent], { git: { unsent: gitOf(unsent) } });
    const card = within(await screen.findByTestId("ws-card-unsent"));
    await waitFor(() => {
      expect(card.getByTestId("ws-status-unsent")).toBeInTheDocument();
    });
    await userEvent.click(card.getByTestId("ws-menu"));
    await userEvent.click(await screen.findByTestId("ws-delete"));
    expect(await screen.findByTestId("ws-delete-unsent")).toHaveTextContent(
      "они пропадут вместе с пространством",
    );
  });

  it("всё отправлено: предупреждения нет", async () => {
    const same = { ...fixture("git_ready"), id: "same" };
    mountView([same], { git: { same: gitOf(same, clean) } });
    const card = within(await screen.findByTestId("ws-card-same"));
    await waitFor(() => {
      expect(card.getByTestId("ws-status-clean")).toBeInTheDocument();
    });
    await userEvent.click(card.getByTestId("ws-menu"));
    await userEvent.click(await screen.findByTestId("ws-delete"));
    await screen.findByRole("dialog");
    expect(screen.queryByTestId("ws-delete-unsent")).toBeNull();
  });
});

const dialog = (
  props: Partial<React.ComponentProps<typeof CreateWorkspaceDialog>> = {},
) => {
  const onCreated = vi.fn();
  wrap(
    <CreateWorkspaceDialog
      isOpen
      kind="git"
      onClose={vi.fn()}
      onCreated={onCreated}
      {...props}
    />,
  );
  return onCreated;
};

const pasteUrl = async (value: string) => {
  // Вставка одним куском: адрес не набирается по букве, окно не пересчитывается на каждой.
  await userEvent.click(screen.getByTestId("ws-create-url"));
  await userEvent.paste(value);
};

const credential = (id: string, host: string, label = `Токен ${id}`) => ({
  id,
  kind: "pat",
  label,
  host,
  status: "ok",
  created_at: "2026-11-15T09:00:00Z",
  used_by: [],
});

describe("окно подключения", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("основная ветка и папка с шаблонами под «Дополнительно», с прежними умолчаниями", async () => {
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([]);
    const created = fixture("git_cloning");
    const create = vi
      .spyOn(packStudioApi, "createWorkspace")
      .mockResolvedValue(created);
    const onCreated = dialog();
    const submit = screen.getByTestId("ws-create-submit");
    expect(submit).toBeDisabled();
    await pasteUrl("https://github.com/AlexeyShalaev/hse-doc-studio");
    await userEvent.click(screen.getByText("Дополнительно"));
    await userEvent.type(screen.getByLabelText("Основная ветка"), "master");
    await userEvent.type(screen.getByLabelText("Название"), "Официальные");
    await userEvent.click(submit);
    await waitFor(() => {
      expect(create).toHaveBeenCalledWith({
        kind: "git",
        url: "https://github.com/AlexeyShalaev/hse-doc-studio",
        credential_id: null,
        base_branch: "master",
        packs_path: "packs",
        label: "Официальные",
        insecure_http: false,
      });
    });
    expect(onCreated).toHaveBeenCalledWith(created);
  });

  it("токена для хоста нет: строка про открытый репозиторий, токен добавляется кнопкой и выбирается", async () => {
    const fresh = credential("fresh", "github.com", "GitHub, github.com");
    vi.spyOn(gitRemoteApi, "listCredentials")
      .mockResolvedValueOnce([])
      .mockResolvedValue([fresh]);
    vi.spyOn(gitRemoteApi, "listHostSettings").mockResolvedValue([]);
    const save = vi
      .spyOn(gitRemoteApi, "createCredential")
      .mockResolvedValue(fresh);
    const check = vi.spyOn(gitRemoteApi, "checkCredential").mockResolvedValue({
      credential: fresh,
      provider_info: { id: "github", detected_by: "host", version: null },
      token_info: {
        login: "anna",
        scopes: ["repo"],
        expires_at: null,
        sufficiency: "sufficient",
        missing: [],
      },
    });
    const create = vi
      .spyOn(packStudioApi, "createWorkspace")
      .mockResolvedValue(fixture("git_cloning"));
    dialog();
    expect(screen.getByTestId("ws-create-access")).toHaveTextContent(
      "Открытый репозиторий подключится без токена. Закрытый: нужен токен.",
    );
    await pasteUrl("https://github.com/anna/packs");
    // Поле токена не мешает, пока его не позвали.
    expect(screen.queryByTestId("ws-create-token")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("ws-create-add-token"));
    const form = await screen.findByTestId("ws-create-token");
    // Пока токен не сохранён, подключить нельзя.
    expect(screen.getByTestId("ws-create-submit")).toBeDisabled();
    const token = within(form).getByLabelText("Токен");
    expect(token).toHaveAttribute("type", "password");
    await userEvent.type(token, "ghp_secret");
    await userEvent.click(within(form).getByTestId("add-token-submit"));
    await waitFor(() => {
      expect(save).toHaveBeenCalledWith(
        expect.objectContaining({ host: "github.com", token: "ghp_secret" }),
      );
    });
    expect(check).toHaveBeenCalledWith("fresh", "packs");
    await waitFor(() => {
      expect(screen.queryByTestId("ws-create-token")).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("ws-create-access")).toHaveTextContent(
      "Подключим с вашим доступом «GitHub, github.com»",
    );
    await userEvent.click(screen.getByTestId("ws-create-submit"));
    await waitFor(() => {
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({ credential_id: "fresh" }),
      );
    });
  });

  it("токен для хоста уже есть: берётся сам, другой хост его не получает", async () => {
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([
      credential("gh", "github.com", "Мой GitHub"),
    ]);
    const create = vi
      .spyOn(packStudioApi, "createWorkspace")
      .mockResolvedValue(fixture("git_cloning"));
    dialog();
    await pasteUrl("https://github.com/anna/packs");
    await waitFor(() => {
      expect(screen.getByTestId("ws-create-access")).toHaveTextContent(
        "Подключим с вашим доступом «Мой GitHub»",
      );
    });
    expect(screen.queryByTestId("ws-create-add-token")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("ws-create-submit"));
    await waitFor(() => {
      expect(create).toHaveBeenLastCalledWith(
        expect.objectContaining({ credential_id: "gh" }),
      );
    });
    create.mockClear();
    await userEvent.clear(screen.getByTestId("ws-create-url"));
    await userEvent.click(screen.getByTestId("ws-create-url"));
    await userEvent.paste("https://gitlab.example.org/fcs/packs");
    expect(screen.getByTestId("ws-create-access")).toHaveTextContent(
      "Открытый репозиторий подключится без токена",
    );
    await userEvent.click(screen.getByTestId("ws-create-submit"));
    await waitFor(() => {
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({ credential_id: null }),
      );
    });
  });

  it("открытый http: без явного согласия не уходит шифрованный запрос", async () => {
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([]);
    const create = vi
      .spyOn(packStudioApi, "createWorkspace")
      .mockResolvedValue(fixture("git_cloning"));
    dialog();
    await pasteUrl("http://git.local/packs");
    await userEvent.click(
      screen.getByLabelText("Разрешить открытый http (без шифрования)"),
    );
    await userEvent.click(screen.getByTestId("ws-create-submit"));
    await waitFor(() => {
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({ insecure_http: true }),
      );
    });
  });

  it("папка: одно поле и «Выбрать папку…», отказ сервера показан словами", async () => {
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([]);
    const { ApiError } = await import("@shared/api");
    vi.spyOn(packStudioApi, "createWorkspace").mockRejectedValue(
      new ApiError("x", "not_a_pack_repo", 400),
    );
    const picked = vi.fn();
    dialog({
      kind: "folder",
      renderFolderPicker: ({ isOpen, onSelect }) =>
        isOpen ? (
          <button
            type="button"
            onClick={() => {
              picked();
              onSelect("/Users/me/packs");
            }}
          >
            выбрать /Users/me/packs
          </button>
        ) : null,
    });
    expect(
      screen.getByRole("heading", { name: "Подключить папку" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("ws-create-url")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("ws-create-pick-folder"));
    await userEvent.click(screen.getByText("выбрать /Users/me/packs"));
    expect(screen.getByTestId("ws-create-folder")).toHaveValue(
      "/Users/me/packs",
    );
    await userEvent.click(screen.getByTestId("ws-create-submit"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "В папке нет шаблонов",
    );
  });

  it("доступ подключённого репозитория на сервере живёт под «Дополнительно»", async () => {
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([]);
    const created = fixture("git_service_access");
    const create = vi
      .spyOn(packStudioApi, "createWorkspace")
      .mockResolvedValue(created);
    dialog({ allowServiceAccess: true });
    await pasteUrl("https://gitlab.hse.ru/fcs/packs.git");
    await userEvent.click(screen.getByText("Дополнительно"));
    await userEvent.click(
      screen.getByRole("button", { name: "Подключённый репозиторий" }),
    );
    expect(screen.getByTestId("ws-create-service-hint")).toBeInTheDocument();
    expect(screen.queryByLabelText("Доступ")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("ws-create-submit"));
    await waitFor(() => {
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: "git",
          url: "https://gitlab.hse.ru/fcs/packs.git",
          credential_id: null,
          service_access: true,
        }),
      );
    });
  });

  it("в локальной Студии доступа подключённого репозитория нет", async () => {
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([]);
    dialog({ allowServiceAccess: false });
    await userEvent.click(screen.getByText("Дополнительно"));
    expect(
      screen.queryByRole("button", { name: "Подключённый репозиторий" }),
    ).not.toBeInTheDocument();
  });
});
