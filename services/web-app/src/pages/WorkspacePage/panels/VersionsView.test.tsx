import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  gitSyncApi,
  useSyncUiStore,
  type SyncStatusView,
} from "@entities/git-sync";
import { profileApi } from "@entities/profile";
import { vcsApi, type VcsCommit, type VcsHistoryParams } from "@entities/vcs";
import { i18n } from "@shared/lib/i18n";
import {
  commit as brief,
  connected,
  noRemote,
} from "@features/git-sync/testing/statusFactory";
import type { ProjectResponseSchema } from "@entities/project";
import type { z } from "zod";

const projectAccess = { access: { mode: "full", reasons: [] } };
vi.mock("@entities/project", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/project")),
  useProject: () => ({ data: projectAccess }),
}));

import { VersionsView } from "./VersionsView";

const PROJECT_ID = "11111111-1111-4111-8111-111111111111";
const project = { id: PROJECT_ID } as z.infer<typeof ProjectResponseSchema>;

const ME = {
  name: "Иван Смирнов",
  email: "ivan@edu.hse.ru",
};

const vcs = (id: string, overrides: Partial<VcsCommit> = {}): VcsCommit => ({
  id,
  short_id: id.slice(0, 7),
  kind: "edit",
  message: `Версия ${id}`,
  author: ME.name,
  author_email: ME.email,
  created_at: "2026-10-26T10:00:00Z",
  parents: [],
  refs: [],
  sync: null,
  is_merge: false,
  ...overrides,
});

const ALL: VcsCommit[] = [
  vcs("named1", { kind: "manual", message: "Глава 3 готова" }),
  vcs("e1", { message: "Правка введения" }),
  vcs("e2", {
    message: "Правка от Анны",
    author: "Анна Петрова",
    author_email: "anna@edu.hse.ru",
  }),
  vcs("c1", { kind: "compile", message: "Сборка" }),
  vcs("s1", {
    kind: "sync",
    is_merge: true,
    message: "Слияние",
    stats: { files: 3, insertions: 8, deletions: 2 },
  }),
];

const FACETS = {
  kinds: { manual: 1, edit: 2, compile: 1, sync: 1, future_kind: 1 },
  authors: [
    { name: "Иван Смирнов", email: ME.email, count: 4 },
    { name: "Анна Петрова", email: "anna@edu.hse.ru", count: 1 },
  ],
};

// Сервер фильтрует по тем же правилам, что и демо: проверяем, что страница
// просит нужное, а не что фильтрует сама.
const serve = (params: VcsHistoryParams): VcsCommit[] =>
  ALL.filter((c) => {
    if (params.kind && !params.kind.includes(c.kind)) return false;
    if (params.authorEmail && c.author_email !== params.authorEmail)
      return false;
    if (params.q && !c.message.toLowerCase().includes(params.q.toLowerCase()))
      return false;
    if (params.sync && c.sync !== params.sync) return false;
    return true;
  });

const mount = async (options: {
  remote: boolean;
  profile?: boolean;
  history?: VcsCommit[];
  status?: SyncStatusView;
}) => {
  const history = vi
    .spyOn(vcsApi, "getHistoryPage")
    .mockImplementation((_id, params) =>
      Promise.resolve(
        options.history
          ? params.kind?.length === 1 && params.kind[0] === "manual"
            ? ALL.slice(0, 1)
            : options.history
          : serve(params),
      ),
    );
  vi.spyOn(vcsApi, "getStatus").mockResolvedValue({
    available: true,
    initialized: true,
    current_branch: "main",
    head: "e1",
    dirty: false,
    modified: 0,
    untracked: 0,
    staged: 0,
    last_snapshot_at: "2026-10-26T10:00:00Z",
    store_path: "/p/.hse-studio/git",
    tracking_enabled: true,
  });
  vi.spyOn(vcsApi, "getHistoryFacets").mockResolvedValue(FACETS);
  vi.spyOn(vcsApi, "getSettings").mockResolvedValue({
    tracking_enabled: true,
    auto_commit_on_compile: true,
    track_pdf: false,
  });
  vi.spyOn(vcsApi, "getDiff").mockResolvedValue({
    from_id: null,
    to_id: "x",
    files: [],
    truncated: false,
  });
  vi.spyOn(profileApi, "get").mockResolvedValue(
    options.profile === false
      ? {
          name: null,
          email: null,
          effective_name: "HSE Doc Studio",
          effective_email: "studio@localhost",
          is_default: true,
          commit_preview: "HSE Doc Studio <studio@localhost>",
        }
      : {
          name: ME.name,
          email: ME.email,
          effective_name: ME.name,
          effective_email: ME.email,
          is_default: false,
          commit_preview: `${ME.name} <${ME.email}>`,
        },
  );
  vi.spyOn(gitSyncApi, "getStatus").mockResolvedValue(
    options.status ?? (options.remote ? connected() : noRemote()),
  );
  vi.spyOn(gitSyncApi, "fetchRemote").mockResolvedValue(connected());

  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <VersionsView project={project} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByText("Глава 3 готова");
  return { history };
};

type HistorySpy = { mock: { calls: unknown[][] } };

const lastParams = (history: HistorySpy): VcsHistoryParams => {
  const calls = history.mock.calls as unknown as [string, VcsHistoryParams][];
  const forRecent = calls.filter(
    ([, p]) => !(p.kind?.length === 1 && p.kind[0] === "manual"),
  );
  return forRecent[forRecent.length - 1]?.[1] ?? {};
};

describe("VersionsView", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    useSyncUiStore.setState({
      connectDialog: null,
      bundleDialogOpen: false,
      command: null,
    });
    Element.prototype.scrollIntoView = vi.fn();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  describe("without a remote", () => {
    it("shows the sync card as an invitation and no sync filters or markers", async () => {
      await mount({ remote: false });
      expect(await screen.findByTestId("sync-panel-empty")).toBeInTheDocument();
      expect(screen.queryByRole("group", { name: "Отправка" })).toBeNull();
      expect(screen.queryAllByTestId("sync-mark")).toHaveLength(0);
    });

    it("opens the connect and bundle dialogs through the shared store", async () => {
      const user = userEvent.setup();
      await mount({ remote: false });
      await user.click(
        await screen.findByRole("button", { name: "Подключить репозиторий" }),
      );
      expect(useSyncUiStore.getState().connectDialog).toEqual({
        mode: "connect",
      });
      await user.click(screen.getByRole("button", { name: "Обмен файлом" }));
      expect(useSyncUiStore.getState().bundleDialogOpen).toBe(true);
    });

    it("keeps named versions on the left and the recent changes on the right", async () => {
      await mount({ remote: false });
      expect(await screen.findByText("Правка введения")).toBeInTheDocument();
      expect(screen.getByText("Сборка")).toBeInTheDocument();
      // Именная версия показана один раз, в своём списке.
      expect(screen.getAllByText("Глава 3 готова")).toHaveLength(1);
    });
  });

  describe("with a remote", () => {
    it("shows the connected panel and the sync segment", async () => {
      await mount({ remote: true });
      expect(await screen.findByTestId("sync-panel")).toBeInTheDocument();
      expect(
        screen.getByRole("group", { name: "Отправка" }),
      ).toBeInTheDocument();
    });

    it("asks the server for every kind except named ones by default", async () => {
      const { history } = await mount({ remote: true });
      await waitFor(() => {
        expect(lastParams(history).kind).toEqual([
          "edit",
          "compile",
          "sync",
          "future_kind",
        ]);
      });
    });

    it("sends the kind chip, the author and the unpushed filter to the server", async () => {
      const user = userEvent.setup();
      const { history } = await mount({ remote: true });
      const kinds = await screen.findByRole("group", { name: "Вид изменения" });
      await user.click(within(kinds).getByRole("button", { name: /Слияния/ }));
      await waitFor(() => {
        expect(lastParams(history).kind).toEqual(["sync"]);
      });
      await user.selectOptions(
        screen.getByRole("combobox", { name: "Автор" }),
        "Только мои",
      );
      await waitFor(() => {
        expect(lastParams(history).authorEmail).toBe(ME.email);
      });
      await user.click(screen.getByRole("button", { name: "Не отправлены" }));
      await waitFor(() => {
        expect(lastParams(history).sync).toBe("unpushed");
      });
    });

    it("folds unknown kinds into the Other chip", async () => {
      const user = userEvent.setup();
      const { history } = await mount({ remote: true });
      const kinds = await screen.findByRole("group", { name: "Вид изменения" });
      await user.click(within(kinds).getByRole("button", { name: /Другое/ }));
      await waitFor(() => {
        expect(lastParams(history).kind).toEqual(["future_kind"]);
      });
    });

    it("debounces the search before it reaches the server", async () => {
      const user = userEvent.setup();
      const { history } = await mount({ remote: true });
      await user.type(
        await screen.findByRole("searchbox", { name: "Поиск по изменениям" }),
        "сборка",
      );
      expect(
        (history.mock.calls as unknown as [string, VcsHistoryParams][]).some(
          ([, p]) => p.q === "с",
        ),
      ).toBe(false);
      await waitFor(() => {
        expect(lastParams(history).q).toBe("сборка");
      });
    });

    it("marks versions and gives teammates an avatar", async () => {
      await mount({
        remote: true,
        history: [
          vcs("p", { message: "Уже ушла", sync: "pushed" }),
          vcs("u", { message: "Ждёт", sync: "unpushed" }),
          vcs("i", {
            message: "Пришла",
            sync: "incoming",
            author: "Анна Петрова",
            author_email: "anna@edu.hse.ru",
          }),
        ],
      });
      expect(
        await screen.findAllByRole("img", { name: "Уже в репозитории" }),
      ).not.toHaveLength(0);
      expect(
        screen.getAllByRole("img", { name: "Ждёт отправки" }).length,
      ).toBeGreaterThan(0);
      expect(
        screen.getAllByRole("img", { name: "Получено от Анна Петрова" }).length,
      ).toBeGreaterThan(0);
      expect(
        screen.getAllByRole("img", { name: "Анна Петрова" }).length,
      ).toBeGreaterThan(0);
    });

    it("jumps to the feed with the incoming filter from the panel", async () => {
      const user = userEvent.setup();
      const { history } = await mount({
        remote: true,
        status: connected({
          ui_state: "behind",
          relation: "behind",
          behind: 1,
          incoming: [brief("i1")],
        }),
      });
      await user.click(
        await screen.findByRole("button", { name: "Показать в ленте ниже" }),
      );
      await waitFor(() => {
        expect(lastParams(history).sync).toBe("incoming");
      });
      expect(
        screen.getByRole("button", { name: "Пришли от коллег" }),
      ).toHaveAttribute("aria-pressed", "true");
    });

    it("offers Show more when a full page came back", async () => {
      const page = Array.from({ length: 100 }, (_, i) => vcs(`p${String(i)}`));
      await mount({ remote: true, history: page });
      expect(
        await screen.findByRole("button", { name: "Показать ещё" }),
      ).toBeInTheDocument();
    });
  });

  it("does not offer Only mine without an author profile", async () => {
    await mount({ remote: true, profile: false });
    const select = await screen.findByRole("combobox", { name: "Автор" });
    expect(
      within(select).queryByRole("option", { name: "Только мои" }),
    ).toBeNull();
  });

  it("tells that nothing matches when the server returns no rows for the filters", async () => {
    const user = userEvent.setup();
    await mount({ remote: true });
    await user.type(
      await screen.findByRole("searchbox", { name: "Поиск по изменениям" }),
      "нет такого",
    );
    expect(
      await screen.findByText("Под выбранные фильтры ничего не нашлось."),
    ).toBeInTheDocument();
  });
});
