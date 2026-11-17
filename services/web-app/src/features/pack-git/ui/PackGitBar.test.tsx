import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { ZodType } from "zod";
import {
  PackCiStatusSchema,
  PackDiffSchema,
  PackGitSchema,
  PackProposeResponseSchema,
  PackStudioErrorBodySchema,
  packOutcomeApi,
  packStudioApi,
  type PackGit,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { referenceImpact } from "@entities/pack-studio/reference";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { PackGitBar } from "./PackGitBar";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-studio/fixtures",
);
const fixture = <T,>(schema: ZodType<T>, dir: string, name: string): T =>
  schema.parse(
    JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8")),
  );

/** Отказ сервера из эталона тела ошибки: {detail, code, ...поля}. */
const apiError = (name: string, status = 409): ApiError => {
  const body = fixture(PackStudioErrorBodySchema, "PackStudioErrorBody", name);
  const { detail, code, ...data } = body;
  return new ApiError(detail, code, status, data);
};

/** «До и после» считается при открытии диалога: отправка доступна, когда он ответил. */
const submitReady = () =>
  waitFor(() => {
    expect(screen.getByTestId("git-propose-submit")).toBeEnabled();
  });

const DIRTY = fixture(PackGitSchema, "PackGit", "detached_dirty");
const PUSHED = fixture(PackGitSchema, "PackGit", "pushed_without_pr");
const CI = fixture(PackCiStatusSchema, "PackCiStatus", "github_running");
const PR = fixture(
  PackProposeResponseSchema,
  "PackProposeResponse",
  "github_pr",
);

/** Пространство с веткой и правками: можно сохранять, предлагать и сливать. */
const onBranch = (patch: Partial<PackGit> = {}): PackGit => ({
  ...DIRTY,
  branch: "pack-studio/ivanov/hse-cs-sse-coursework-2026.1.7",
  workspace: {
    ...DIRTY.workspace,
    work_branch: "pack-studio/ivanov/hse-cs-sse-coursework-2026.1.7",
  },
  ...patch,
});

/** `failure`: состояние git не читается, сервер отвечает этой ошибкой. */
const mount = (git: PackGit, failure?: ApiError) => {
  vi.spyOn(packStudioApi, "tree").mockResolvedValue({
    workspace_id: "w",
    base_sha: null,
    packs: [],
    files: [],
    truncated: false,
  });
  vi.spyOn(packOutcomeApi, "impact").mockResolvedValue({
    data: referenceImpact("impact_same"),
    etag: null,
  });
  const state = vi.spyOn(packStudioApi, "git");
  if (failure) state.mockRejectedValue(failure);
  else state.mockResolvedValue(git);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const props = {
    onOpenFile: vi.fn(),
    onLintFailed: vi.fn(),
    onFilesChanged: vi.fn(),
  };
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PackGitBar workspace={git.workspace} editorDirty={false} {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return props;
};

describe("панель git рабочего пространства", () => {
  beforeAll(async () => {
    await Promise.all([loadPackStudioNamespace(), loadPackOutcomeNamespace()]);
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("состояние: без ветки, правки после версии; «Предложить» включено", async () => {
    mount(DIRTY);
    expect(await screen.findByTestId("git-branch")).toHaveTextContent(
      "без ветки, вершина master",
    );
    expect(screen.getByTestId("git-dirty")).toHaveTextContent(
      "2 правки после версии",
    );
    expect(screen.queryByTestId("git-ahead-behind")).not.toBeInTheDocument();
    expect(screen.queryByTestId("git-ci")).not.toBeInTheDocument();
    expect(screen.getByTestId("git-commit")).toBeEnabled();
    expect(screen.getByTestId("propose-changes")).toBeEnabled();
  });

  it("ветка отправлена без PR: ahead/behind, ссылка compare, статус CI со списком", async () => {
    const checks = vi.spyOn(packStudioApi, "checks").mockResolvedValue(CI);
    mount(PUSHED);
    expect(await screen.findByTestId("git-ahead-behind")).toHaveTextContent(
      "12",
    );
    expect(screen.getByTestId("git-compare-link")).toHaveAttribute(
      "href",
      PUSHED.compare_url,
    );
    expect(screen.getByTestId("git-commit")).toBeDisabled();
    const badge = await screen.findByTestId("git-ci");
    await waitFor(() => {
      expect(badge).toHaveAttribute("data-state", "pending");
    });
    expect(checks).toHaveBeenCalledWith(PUSHED.workspace.id);
    await userEvent.click(badge);
    const list = await screen.findByTestId("git-ci-list");
    expect(within(list).getByText("packs")).toHaveAttribute(
      "href",
      CI.checks[0]?.url,
    );
    expect(list).toHaveTextContent("прошла · Lint passed");
    expect(screen.getByTestId("git-ci-web")).toHaveAttribute(
      "href",
      CI.web_url,
    );
  });

  it("хостинг не отдаёт статус: ссылка на страницу проверок и пояснение", async () => {
    vi.spyOn(packStudioApi, "checks").mockResolvedValue(
      fixture(PackCiStatusSchema, "PackCiStatus", "gitlab_no_read_api"),
    );
    mount(PUSHED);
    const badge = await screen.findByTestId("git-ci");
    await waitFor(() => {
      expect(badge).toHaveAttribute("data-state", "unknown");
    });
    await userEvent.click(badge);
    expect(await screen.findByText(/read_api/)).toBeInTheDocument();
    expect(screen.getByTestId("git-ci-web")).toBeInTheDocument();
  });

  it("«Сохранить версию»: пустое сообщение отдаёт его серверу, своё уходит как есть", async () => {
    const commit = vi.spyOn(packStudioApi, "commit").mockResolvedValue({
      // Правки остались (другой файл): окно можно открыть снова.
      git: DIRTY,
      sha: "0123456789abcdef",
      committed: true,
    });
    mount(DIRTY);
    await userEvent.click(await screen.findByTestId("git-commit"));
    expect(screen.getByTestId("git-commit-files")).toHaveTextContent(
      "version.yaml",
    );
    await userEvent.click(screen.getByTestId("git-commit-submit"));
    await waitFor(() => {
      expect(commit).toHaveBeenCalledWith(DIRTY.workspace.id, null);
    });

    await userEvent.click(await screen.findByTestId("git-commit"));
    await userEvent.type(
      screen.getByTestId("git-commit-message"),
      "fix(packs): поля титула",
    );
    await userEvent.click(screen.getByTestId("git-commit-submit"));
    await waitFor(() => {
      expect(commit).toHaveBeenLastCalledWith(
        DIRTY.workspace.id,
        "fix(packs): поля титула",
      );
    });
  });

  it("ветка: своё имя; отказ workspace_dirty словами", async () => {
    const change = vi
      .spyOn(packStudioApi, "switchBranch")
      .mockRejectedValue(apiError("workspace_dirty"));
    const props = mount(DIRTY);
    await userEvent.click(await screen.findByTestId("git-branch"));
    await userEvent.click(
      screen.getByLabelText(/Своё имя или существующая ветка/),
    );
    await userEvent.type(screen.getByTestId("git-branch-name"), "my/branch");
    await userEvent.click(screen.getByTestId("git-branch-submit"));
    await waitFor(() => {
      expect(change).toHaveBeenCalledWith(DIRTY.workspace.id, "my/branch");
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Есть несохранённые правки",
    );
    expect(props.onFilesChanged).not.toHaveBeenCalled();
  });

  it("ветка с именем по умолчанию: имя придумывает сервер, файлы перечитываются", async () => {
    const change = vi
      .spyOn(packStudioApi, "switchBranch")
      .mockResolvedValue(onBranch());
    const props = mount(DIRTY);
    await userEvent.click(await screen.findByTestId("git-branch"));
    await userEvent.click(screen.getByTestId("git-branch-submit"));
    await waitFor(() => {
      expect(change).toHaveBeenCalledWith(DIRTY.workspace.id, null);
    });
    await waitFor(() => {
      expect(props.onFilesChanged).toHaveBeenCalled();
    });
  });

  it("«Предложить изменения»: PR открыт, ссылка и класс изменения", async () => {
    const propose = vi.spyOn(packStudioApi, "propose").mockResolvedValue(PR);
    mount(onBranch());
    await userEvent.click(await screen.findByTestId("propose-changes"));
    await userEvent.type(
      screen.getByTestId("git-propose-title"),
      "fix(packs): заявка",
    );
    await submitReady();
    await userEvent.click(screen.getByTestId("git-propose-submit"));
    await waitFor(() => {
      expect(propose).toHaveBeenCalledWith(DIRTY.workspace.id, {
        title: "fix(packs): заявка",
        description: null,
        message: null,
      });
    });
    const done = await screen.findByTestId("git-propose-done");
    expect(done).toHaveTextContent("Открыт PR #412");
    expect(screen.getByTestId("git-propose-pr-link")).toHaveAttribute(
      "href",
      PR.pull_request?.url,
    );
    expect(done).toHaveTextContent("Класс patch: только места подписей.");
    expect(done).toHaveTextContent("-shell-escape");
  });

  it("проверки пака не прошли: находки уходят в «Проблемы», окно закрывается", async () => {
    vi.spyOn(packStudioApi, "propose").mockRejectedValue(
      apiError("lint_failed"),
    );
    const props = mount(onBranch());
    await userEvent.click(await screen.findByTestId("propose-changes"));
    await submitReady();
    await userEvent.click(screen.getByTestId("git-propose-submit"));
    await waitFor(() => {
      expect(props.onLintFailed).toHaveBeenCalledWith({
        errors: 1,
        warnings: 0,
        findings: [
          {
            severity: "error",
            check: "lint",
            path: "hse-cs-sse/templates/coursework/versions/2026.1.7",
            message: "documents[0].id: обязательное поле",
          },
        ],
      });
    });
    await waitFor(() => {
      expect(screen.queryByTestId("git-propose")).not.toBeInTheDocument();
    });
  });

  it("нет права push: «Отправить в форк», повтор с созданием форка, затем ссылка compare и pr_error", async () => {
    const propose = vi
      .spyOn(packStudioApi, "propose")
      .mockRejectedValueOnce(apiError("fork_required"))
      .mockResolvedValueOnce(
        fixture(
          PackProposeResponseSchema,
          "PackProposeResponse",
          "fork_compare_link",
        ),
      );
    mount(onBranch());
    await userEvent.click(await screen.findByTestId("propose-changes"));
    await submitReady();
    await userEvent.click(screen.getByTestId("git-propose-submit"));
    expect(await screen.findByTestId("git-fork-step")).toBeInTheDocument();
    // can_create: форк можно создать токеном, вариант выбран сразу.
    expect(screen.getByTestId("git-fork-create")).toBeChecked();
    await userEvent.click(screen.getByTestId("git-fork-submit"));
    await waitFor(() => {
      expect(propose).toHaveBeenLastCalledWith(DIRTY.workspace.id, {
        title: null,
        description: null,
        message: null,
        fork: { create: true },
      });
    });
    const done = await screen.findByTestId("git-propose-done");
    expect(done).toHaveTextContent("Ветка отправлена");
    expect(done).toHaveTextContent("В форк https://github.com/ivanov");
    expect(screen.getByTestId("git-propose-compare")).toBeInTheDocument();
    expect(done).toHaveTextContent("нет права открывать запросы на слияние");
  });

  it("форк без права создания: только адрес, отказ хоста словами", async () => {
    const forkBody = apiError("fork_required");
    const noCreate = new ApiError(forkBody.detail, forkBody.code, 409, {
      can_create: false,
    });
    const mismatch = new ApiError(forkBody.detail, forkBody.code, 409, {
      reason: "fork_host_mismatch",
    });
    const propose = vi
      .spyOn(packStudioApi, "propose")
      .mockRejectedValueOnce(noCreate)
      .mockRejectedValueOnce(mismatch);
    mount(onBranch());
    await userEvent.click(await screen.findByTestId("propose-changes"));
    await submitReady();
    await userEvent.click(screen.getByTestId("git-propose-submit"));
    await screen.findByTestId("git-fork-step");
    expect(screen.queryByTestId("git-fork-create")).not.toBeInTheDocument();
    const submit = screen.getByTestId("git-fork-submit");
    expect(submit).toBeDisabled();
    await userEvent.type(
      screen.getByTestId("git-fork-url"),
      "https://gitlab.com/me/packs.git",
    );
    await userEvent.click(submit);
    await waitFor(() => {
      expect(propose).toHaveBeenLastCalledWith(
        DIRTY.workspace.id,
        expect.objectContaining({
          fork: { url: "https://gitlab.com/me/packs.git" },
        }),
      );
    });
    expect(
      await screen.findByText(/Форк должен быть на том же сервере/),
    ).toBeInTheDocument();
  });

  it("push_denied: текст и переход к доступу к репозиторию", async () => {
    vi.spyOn(packStudioApi, "propose").mockRejectedValue(
      new ApiError("x", "push_denied", 403),
    );
    mount({
      ...onBranch(),
      workspace: { ...onBranch().workspace, credential_id: null },
    });
    await userEvent.click(await screen.findByTestId("propose-changes"));
    await submitReady();
    await userEvent.click(screen.getByTestId("git-propose-submit"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("нет права записи");
    await userEvent.click(
      within(alert).getByRole("button", { name: "Доступ к репозиторию" }),
    );
    expect(await screen.findByTestId("git-access")).toHaveTextContent(
      "У пространства нет токена",
    );
  });

  it("подтянуть основную ветку: конфликт со списком файлов и переходом к файлу", async () => {
    vi.spyOn(packStudioApi, "mergeBase").mockRejectedValue(
      apiError("merge_conflict"),
    );
    const clean = onBranch({ dirty: false, uncommitted: [] });
    const props = mount(clean);
    await userEvent.click(await screen.findByTestId("git-menu"));
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Подтянуть master" }),
    );
    const dialog = await screen.findByTestId("git-merge-conflict");
    expect(dialog).toHaveTextContent("Слияние отменено");
    await userEvent.click(
      within(dialog).getByText(/2026\.1\.7\/version\.yaml/),
    );
    expect(props.onOpenFile).toHaveBeenCalledWith(
      "hse-cs-sse/templates/coursework/versions/2026.1.7/version.yaml",
    );
  });

  it("«Начать заново» с правками: только с явной галочкой «Отбросить»", async () => {
    const startOver = vi
      .spyOn(packStudioApi, "startOver")
      .mockResolvedValue(DIRTY);
    const props = mount(onBranch());
    await userEvent.click(await screen.findByTestId("git-menu"));
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Начать заново" }),
    );
    const submit = await screen.findByTestId("git-start-over-submit");
    expect(submit).toBeDisabled();
    await userEvent.click(screen.getByTestId("git-start-over-discard"));
    await userEvent.click(submit);
    await waitFor(() => {
      expect(startOver).toHaveBeenCalledWith(DIRTY.workspace.id, true);
    });
    await waitFor(() => {
      expect(props.onFilesChanged).toHaveBeenCalled();
    });
  });

  it("изменения от базы по файлам, пометка об обрезке", async () => {
    vi.spyOn(packStudioApi, "diff").mockResolvedValue({
      ...fixture(PackDiffSchema, "PackDiff", "small"),
      truncated: true,
    });
    mount(DIRTY);
    await userEvent.click(await screen.findByTestId("git-diff-open"));
    const diff = await screen.findByTestId("git-diff");
    await waitFor(() => {
      expect(diff).toHaveTextContent("packs/demo/pack.yaml");
    });
    expect(diff).toHaveTextContent("Изменений слишком много");
  });

  it("служебный доступ виден меткой и в окне доступа", async () => {
    const git = {
      ...DIRTY,
      workspace: {
        ...DIRTY.workspace,
        service_access: true,
        credential_id: null,
      },
    };
    mount(git);
    expect(await screen.findByTestId("git-service-access")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("git-menu"));
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Доступ к репозиторию" }),
    );
    expect(await screen.findByTestId("git-access-service")).toHaveTextContent(
      "Работает служебный доступ установки",
    );
  });

  it("сбой локального git: текст и свёрнутая подсказка для поддержки", async () => {
    mount(DIRTY, apiError("workspace_git_failed"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("пришлите администратору подробности");
    const hint = within(alert).getByTestId("git-failure-hint");
    expect(hint).not.toHaveAttribute("open");
    expect(hint).toHaveTextContent("Подробности для поддержки");
    expect(hint).toHaveTextContent(
      "git status: fatal: transport 'https' not allowed",
    );
  });
});
