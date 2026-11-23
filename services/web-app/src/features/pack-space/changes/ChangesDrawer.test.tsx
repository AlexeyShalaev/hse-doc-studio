import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";
import userEvent from "@testing-library/user-event";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import {
  packOutcomeApi,
  packStudioApi,
  type PackCiStatus,
  type PackFileChange,
  type PackGit,
  type PackLint,
  type PackVersionModel,
} from "@entities/pack-studio";
import {
  COURSEWORK_INPUTS,
  referenceImpact,
} from "@entities/pack-studio/reference";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { GALLERY_TREE, GALLERY_WORKSPACE } from "../galleryKit";
import { SpaceScreen } from "../shell/SpaceScreen";
import { renderSpace, SPACE_BASE } from "../spaceTestKit";
import { ChangesPanel } from "./ChangesPanel";
import { deriveChangesStatus } from "./deriveChangesStatus";
import { versionStateOf } from "../next-step/fixtures";
import { slots } from "./slots";

// Первая панель грузит отдельный чанк и модули диалогов: на нагруженной машине это секунды.
vi.setConfig({ testTimeout: 30_000 });

const V = "hse-cs-sse/templates/coursework/versions/2026.1.3";
const BRANCH = "pack-studio/anna/hse-cs-sse-coursework-2026.1.3";
const FILES: PackFileChange[] = [
  { path: `${V}/version.yaml`, status: "modified" },
  { path: `${V}/files/technical_specification/doc.yaml`, status: "modified" },
  {
    path: `${V}/files/source_listing/source_listing.ru.tex`,
    status: "modified",
  },
];

const gitOf = (patch: Partial<PackGit> = {}): PackGit => ({
  workspace: { ...GALLERY_WORKSPACE, work_branch: BRANCH },
  provider: "github",
  head_sha: "aaa",
  branch: BRANCH,
  base_branch: "master",
  uncommitted: FILES,
  dirty: true,
  changed: FILES,
  ahead: 1,
  behind: 0,
  compare_url: null,
  ...patch,
});

const SENT: Partial<PackGit> = {
  workspace: {
    ...GALLERY_WORKSPACE,
    work_branch: BRANCH,
    pr_number: 412,
    pr_url: "https://github.com/o/r/pull/412",
    pushed_sha: "aaa",
  },
  uncommitted: [],
  dirty: false,
};

const lintOf = (findings: PackLint["findings"]): PackLint => ({
  scope: "version",
  target: V,
  released: false,
  errors: findings.filter((f) => f.severity === "error").length,
  warnings: findings.filter((f) => f.severity === "warning").length,
  findings,
});

const modelOf = (notes: boolean): PackVersionModel => ({
  workspace_id: GALLERY_WORKSPACE.id,
  pack: "hse-cs-sse",
  template: "coursework",
  version: "2026.1.3",
  read_only: null,
  manifest: {
    path: `${V}/version.yaml`,
    etag: "e",
    data: notes ? { changes: { ru: ["Раз"], en: ["One"] } } : {},
  },
  documents: [
    {
      id: "technical_specification",
      manifest: null,
      data: { name: { ru: "Техническое задание", en: "Statement of Work" } },
      files: [],
      references: [],
    },
    {
      id: "source_listing",
      manifest: null,
      data: { name: { ru: "Текст программы", en: "Source listing" } },
      files: [],
      references: [],
    },
  ],
  usage: [],
  checks: [],
  problems: [],
  changed: [],
});

const ci = (patch: Partial<PackCiStatus> = {}): PackCiStatus => ({
  state: "pending",
  sha: "aaa",
  checks: [
    { name: "a", state: "success", url: null, summary: null },
    { name: "b", state: "success", url: null, summary: null },
    { name: "c", state: "success", url: null, summary: null },
    { name: "d", state: "running", url: null, summary: null },
    { name: "e", state: "queued", url: null, summary: null },
  ],
  available: true,
  reason: null,
  web_url: null,
  pr_state: "open",
  ...patch,
});

type Setup = {
  git?: PackGit;
  lint?: PackLint;
  notes?: boolean;
  ci?: PackCiStatus;
  url?: string;
};

/** Весь экран пространства (кнопка в полосе и панель) на подменённом API; шаблон, версия 2026.1.3. */
const mount = (setup: Setup = {}) => {
  const spies = {
    git: vi.spyOn(packStudioApi, "git").mockResolvedValue(setup.git ?? gitOf()),
    lint: vi
      .spyOn(packStudioApi, "lint")
      .mockResolvedValue(setup.lint ?? lintOf([])),
    model: vi
      .spyOn(packStudioApi, "versionModel")
      .mockResolvedValue(modelOf(setup.notes ?? true)),
    // Отчёт версии нужен разделу отправки (класс, номера, что записано в заметках).
    state: vi
      .spyOn(packStudioApi, "versionState")
      .mockResolvedValue(
        versionStateOf(
          setup.notes === false
            ? {}
            : { changes: { ru: ["Раз"], en: ["One"] } },
        ),
      ),
    checks: vi
      .spyOn(packStudioApi, "checks")
      .mockResolvedValue(setup.ci ?? ci()),
    tree: vi.spyOn(packStudioApi, "tree").mockResolvedValue(GALLERY_TREE),
    impact: vi.spyOn(packOutcomeApi, "impact").mockResolvedValue({
      data: referenceImpact("normal"),
      etag: null,
    }),
    inputs: vi.spyOn(packOutcomeApi, "inputs").mockResolvedValue({
      data: COURSEWORK_INPUTS,
      etag: null,
    } as never),
  };
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = renderSpace(
    <QueryClientProvider client={client}>
      <SpaceScreen slots={slots} phone={false} />
    </QueryClientProvider>,
    setup.url ?? `${SPACE_BASE}/2026.1.3/result?changes=1`,
  );
  return { spies, ...view };
};

const location = () => screen.getByTestId("location").textContent;
// Панель грузится отдельным чанком: первый разбор модулей в тесте занимает секунды.
const panel = () =>
  screen.findByTestId("sp-changes-panel", undefined, { timeout: 15000 });

describe("панель «Изменения»", () => {
  beforeAll(async () => {
    await Promise.all([
      loadPackSpaceNamespace(),
      loadPackStudioNamespace(),
      loadPackOutcomeNamespace(),
    ]);
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("готово: число на кнопке, что изменено человеческими словами, проверки чистые", async () => {
    mount({
      lint: lintOf([
        {
          severity: "warning",
          check: "lint",
          message: "длинный заголовок",
          path: `${V}/files/technical_specification/doc.yaml`,
          line: 14,
          pointer: null,
        },
      ]),
    });
    const root = await panel();
    await waitFor(() => {
      expect(screen.getByTestId("sp-changes-count")).toHaveTextContent("3");
    });
    expect(screen.getByTestId("sp-changes-button")).toHaveAccessibleName(
      "Изменения: 3 файла",
    );
    const what = await within(root).findByTestId("sp-ch-what");
    expect(
      within(what)
        .getAllByTestId("sp-ch-item")
        .map((item) => item.textContent),
    ).toEqual([
      "Описание версии",
      "Техническое задание: условия",
      "Текст программы: текст",
    ]);
    expect(what).toHaveTextContent("Курсовой проект · версия 2026.1.3");
    expect(what).toHaveTextContent("3 файла");
    expect(await within(root).findByTestId("sp-ch-ok")).toHaveTextContent(
      "Ошибок нет",
    );
    expect(within(root).getByTestId("sp-ch-warnings")).toHaveTextContent(
      "1 замечание к оформлению. Отправке не мешает.",
    );
    expect(within(root).queryByTestId("sp-ch-notes")).not.toBeInTheDocument();
    // Простыми словами: никаких «коммитов» и «PR» в основной части панели.
    expect(root.textContent).not.toMatch(/коммит|\bPR\b|push/i);
    expect(within(root).getByTestId("sp-ch-intro")).toHaveTextContent(
      "видите только вы",
    );
  });

  it("правки в другой версии: её документы тоже названы словами, а не идентификаторами", async () => {
    const OTHER = "hse-cs-sse/templates/coursework/versions/2026.1.2";
    const changed: PackFileChange[] = [
      ...FILES,
      {
        path: `${OTHER}/files/technical_specification/doc.yaml`,
        status: "modified",
      },
    ];
    const { spies } = mount({ git: gitOf({ changed, uncommitted: changed }) });
    const root = await panel();
    const what = await within(root).findByTestId("sp-ch-what");
    await waitFor(() => {
      expect(
        within(what)
          .getAllByTestId("sp-ch-item")
          .map((item) => item.textContent),
      ).toEqual([
        "Описание версии",
        "Техническое задание: условия",
        "Текст программы: текст",
        "Техническое задание: условия",
      ]);
    });
    expect(what).not.toHaveTextContent("technical_specification");
    // Модель другой версии читается отдельно, по её адресу.
    expect(spies.model).toHaveBeenCalledWith(
      GALLERY_WORKSPACE.id,
      expect.objectContaining({ version: "2026.1.2" }),
    );
  });

  it("ошибка ведёт к файлу, заметки это шаг, а не ошибка", async () => {
    mount({
      lint: lintOf([
        {
          severity: "error",
          check: "schema",
          message: "нет поля «name_shrt»",
          path: `${V}/files/technical_specification/doc.yaml`,
          line: 6,
          pointer: null,
        },
      ]),
      notes: false,
    });
    const root = await panel();
    const error = await within(root).findByTestId("sp-ch-error");
    expect(error).toHaveTextContent(
      "Техническое задание: условия, строка 6: нет поля «name_shrt»",
    );
    expect(within(root).queryByTestId("sp-ch-ok")).not.toBeInTheDocument();
    expect(await within(root).findByTestId("sp-ch-notes")).toHaveTextContent(
      "Это обычный шаг, ошибки здесь нет",
    );
    await userEvent.click(
      within(error).getByRole("button", { name: "Перейти" }),
    );
    expect(location()).toContain("/content");
    expect(location()).toContain("file=");
    expect(location()).toContain("technical_specification%2Fdoc.yaml");
  });

  it("запрос открыт: проверки на хостинге, ссылка, можно продолжать править", async () => {
    mount({ git: gitOf(SENT) });
    const root = await panel();
    expect(await within(root).findByTestId("sp-ch-open")).toHaveTextContent(
      "Запрос на слияние #412 открыт.",
    );
    expect(await within(root).findByTestId("sp-ch-host")).toHaveTextContent(
      "Идут: 3 из 5 завершились",
    );
    expect(
      within(root).getByRole("link", { name: /Открыть запрос #412/ }),
    ).toHaveAttribute("href", "https://github.com/o/r/pull/412");
    expect(root).toHaveTextContent("попадут в тот же запрос");
    expect(screen.getByTestId("sp-changes-button")).toBeInTheDocument();
  });

  it("запрос принят: «Начать новую правку»", async () => {
    mount({
      git: gitOf(SENT),
      ci: ci({ state: "success", pr_state: "merged" }),
    });
    const root = await panel();
    expect(await within(root).findByTestId("sp-ch-merged")).toHaveTextContent(
      "Запрос #412 принят.",
    );
    expect(
      within(root).getByRole("button", { name: "Начать новую правку" }),
    ).toBeEnabled();
  });

  it("основная ветка ушла вперёд: плашка и «Забрать новое»", async () => {
    mount({ git: gitOf({ behind: 3 }) });
    const root = await panel();
    const banner = await within(root).findByTestId("sp-ch-behind");
    expect(banner).toHaveTextContent("В основной ветке есть новое.");
    const merge = vi
      .spyOn(packStudioApi, "mergeBase")
      .mockResolvedValue(gitOf({ behind: 0 }));
    await userEvent.click(
      within(banner).getByRole("button", { name: "Забрать новое" }),
    );
    await waitFor(() => {
      expect(merge).toHaveBeenCalledTimes(1);
    });
  });

  it("изменений нет: объяснение и ничего лишнего", async () => {
    mount({ git: gitOf({ changed: [], uncommitted: [], dirty: false }) });
    const root = await panel();
    expect(await within(root).findByText("Изменений пока нет")).toBeVisible();
    expect(within(root).queryByTestId("sp-ch-what")).not.toBeInTheDocument();
    expect(screen.queryByTestId("sp-changes-count")).not.toBeInTheDocument();
    // «Правки пока только у вас» рядом с «Изменений пока нет» противоречило бы друг другу.
    expect(within(root).queryByTestId("sp-ch-where")).not.toBeInTheDocument();
  });

  it("свежая копия версии: 87 файлов новые для git, а изменений две, и они названы по документам", async () => {
    const OLD = "hse-cs-sse/templates/coursework/versions/2026.1.2";
    const docs = Array.from({ length: 28 }, (_, i) => `doc_${String(i)}`);
    const names = [
      "technical_specification",
      "source_listing",
      ...docs.slice(2),
    ];
    const copy: PackFileChange[] = [
      { path: `${V}/version.yaml`, status: "added" },
      ...names.flatMap((doc) => [
        { path: `${V}/files/${doc}/doc.yaml`, status: "added" as const },
        { path: `${V}/files/${doc}/${doc}.ru.tex`, status: "added" as const },
      ]),
    ];
    expect(copy.length).toBeGreaterThan(50);
    // Правка человека: условия ТЗ и текст программы. Остальное совпадает с версией 2026.1.2.
    const mine = new Set([
      `${V}/files/technical_specification/doc.yaml`,
      `${V}/files/source_listing/source_listing.ru.tex`,
    ]);
    const { spies } = mount({
      git: gitOf({ changed: copy, uncommitted: copy, branch: null }),
    });
    const reads = vi
      .spyOn(packStudioApi, "readFile")
      .mockImplementation((_id, path) =>
        Promise.resolve({
          path,
          content: "",
          etag: mine.has(path)
            ? `"mine-${path}"`
            : `"same-${path.split("/").slice(-2).join("/")}"`,
          readOnly: null,
        }),
      );
    // Манифест версии отличается только полями, которые пишет Студия.
    spies.model.mockImplementation((_id, ref) =>
      Promise.resolve({
        ...modelOf(true),
        manifest: {
          path: `${ref.version === "2026.1.2" ? OLD : V}/version.yaml`,
          etag: "e",
          data:
            ref.version === "2026.1.2"
              ? { id: "2026.1.2", kinds: [1] }
              : { id: "2026.1.3", status: "beta", kinds: [1] },
        },
      }),
    );
    const root = await panel();
    await waitFor(() => {
      expect(screen.getByTestId("sp-changes-count")).toHaveTextContent("2");
    });
    expect(reads).toHaveBeenCalled();
    const what = await within(root).findByTestId("sp-ch-what");
    expect(what).toHaveTextContent("Новая версия 2026.1.3 и мои правки");
    expect(what).toHaveTextContent("2 файла");
    expect(
      within(what)
        .getAllByTestId("sp-ch-item")
        .map((item) => item.textContent),
    ).toEqual(["Техническое задание: условия", "Текст программы: текст"]);
    // Внутренних имён и «новое» у каждой строки нет.
    expect(what.textContent).not.toMatch(/doc_\d|новое/);
  });

  it("«Сбросить все мои изменения»: окно с теми же словами, без «свежей main без ветки»", async () => {
    mount();
    const root = await panel();
    await userEvent.click(await within(root).findByTestId("sp-ch-menu"));
    await userEvent.click(await screen.findByTestId("sp-ch-menu-reset"));
    const dialog = await screen.findByRole("dialog", undefined, {
      timeout: 15000,
    });
    expect(dialog).toHaveTextContent("Сбросить все мои изменения");
    expect(dialog.textContent).not.toMatch(/main|без ветки|Начать заново/);
  });

  it("меню «Ещё» панели: сохранить точку, ветка, доступ; построчное сравнение с основной веткой", async () => {
    vi.spyOn(packStudioApi, "diff").mockResolvedValue({
      diff: "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n",
      truncated: false,
    });
    mount();
    const root = await panel();
    const open = async (item: string) => {
      await userEvent.click(await within(root).findByTestId("sp-ch-menu"));
      await userEvent.click(await screen.findByTestId(item));
      return screen.findByRole("dialog", undefined, { timeout: 15000 });
    };
    expect(await open("sp-ch-menu-save")).toHaveTextContent("Сохранить");
    await userEvent.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(await open("sp-ch-menu-branch")).toHaveTextContent("Ветка");
    await userEvent.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    await open("sp-ch-menu-access");
    await userEvent.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    await userEvent.click(within(root).getByTestId("sp-ch-diff"));
    expect(await screen.findByTestId("git-diff")).toHaveTextContent("+new");
  });

  it("выпущенная версия без изменений: подсказка про копию", async () => {
    mount({
      git: gitOf({ changed: [], uncommitted: [], dirty: false }),
      url: `${SPACE_BASE}/2026.1.2/result?changes=1`,
    });
    const root = await panel();
    expect(
      await within(root).findByText(/правки пойдут в копию версии 2026\.1\.2/),
    ).toBeVisible();
    expect(root).toHaveTextContent("Править копию");
  });

  it("выпущенную версию правили мимо Студии: «Перенести правки» в копию и переход к ней", async () => {
    const released = "hse-cs-sse/templates/coursework/versions/2026.1.2";
    const edited: PackFileChange[] = [
      { path: `${released}/version.yaml`, status: "modified" },
    ];
    const { spies } = mount({
      git: gitOf({ changed: edited, uncommitted: edited }),
      url: `${SPACE_BASE}/2026.1.2/result?changes=1`,
    });
    spies.state.mockResolvedValue(
      versionStateOf({
        version: {
          pack: "hse-cs-sse",
          template: "coursework",
          version: "2026.1.2",
          path: released,
        },
        released: true,
        modified: true,
        move_to: "2026.1.3",
      }),
    );
    const move = vi.spyOn(packStudioApi, "moveVersionEdits").mockResolvedValue({
      version: {
        pack: "hse-cs-sse",
        template: "coursework",
        version: "2026.1.3",
        path: V,
      },
      previous: "2026.1.2",
      unreleased: false,
      restored: true,
    });
    const root = await panel();
    const notice = await within(root).findByTestId("sp-ch-move");
    expect(notice).toHaveTextContent(
      "Выпущенную версию 2026.1.2 правили мимо Студии",
    );
    expect(notice).toHaveTextContent("вернутся к основной ветке");
    await userEvent.click(within(notice).getByTestId("sp-ch-move-submit"));
    await waitFor(() => {
      expect(move).toHaveBeenCalledWith(
        GALLERY_WORKSPACE.id,
        expect.objectContaining({ version: "2026.1.2" }),
        "2026.1.3",
      );
    });
    await waitFor(() => {
      expect(location()).toContain("/2026.1.3/result");
    });
  });

  it("Esc закрывает панель и возвращает фокус на кнопку", async () => {
    mount();
    const root = await panel();
    await waitFor(() => {
      expect(root.querySelector("h2")).toHaveFocus();
    });
    await userEvent.keyboard("{Escape}");
    await waitFor(() => {
      expect(location()).not.toContain("changes=1");
    });
    expect(screen.queryByTestId("sp-changes-panel")).not.toBeInTheDocument();
    expect(screen.getByTestId("sp-changes-button")).toHaveFocus();
  });

  it("кнопка «Изменения» открывает и закрывает панель", async () => {
    mount({ url: `${SPACE_BASE}/2026.1.3/result` });
    const button = await screen.findByTestId("sp-changes-button");
    expect(button).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(button);
    expect(location()).toContain("changes=1");
    expect(await panel()).toBeVisible();
    await userEvent.click(screen.getByTestId("sp-changes-button"));
    expect(location()).not.toContain("changes=1");
  });

  it("запросов при открытии панели не больше семи (шесть панели и отчёт версии для отправки)", async () => {
    const { spies } = mount({ lint: lintOf([]) });
    const root = await panel();
    await within(root).findByTestId("sp-ch-ok");
    await screen.findByTestId("impact-block");
    await waitFor(() => {
      expect(spies.inputs).toHaveBeenCalled();
    });
    const calls = Object.fromEntries(
      Object.entries(spies).map(([name, spy]) => [name, spy.mock.calls.length]),
    );
    // Дерево читает страница (`WithSpaceData`), в этом тесте оно уже в провайдере.
    const total = Object.entries(calls)
      .filter(([name]) => name !== "tree")
      .reduce((sum, [, count]) => sum + count, 0);
    expect(calls).toMatchObject({
      git: 1,
      lint: 1,
      model: 1,
      state: 1,
      impact: 1,
      inputs: 1,
      checks: 0,
    });
    expect(total).toBeLessThanOrEqual(7);
  });
});

describe("панель «Изменения»: папка на диске", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("«Записано в папку», путь, отправки нет, предлагается подключить репозиторий", () => {
    const workspace = {
      ...GALLERY_WORKSPACE,
      kind: "folder" as const,
      folder: "/Users/anna/hse-doc-studio/packs",
    };
    const raw = {
      workspace,
      tree: GALLERY_TREE,
      open: { pack: "hse-cs-sse", template: "coursework", version: "2026.1.3" },
      git: null,
      gitLoad: "ready" as const,
      ci: null,
      lint: [],
      notes: null,
    };
    render(
      <MemoryRouter>
        <ChangesPanel
          data={{
            status: deriveChangesStatus(raw),
            raw,
            error: null,
            retry: () => undefined,
          }}
          docNames={{}}
          templateName={() => "Курсовой проект"}
          busy={false}
          onClose={() => undefined}
          onOpenFile={() => undefined}
          onGoCheck={() => undefined}
          onAction={() => undefined}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("sp-ch-folder")).toHaveTextContent(
      "Правки уже записаны в папку.",
    );
    expect(screen.getByTestId("sp-ch-folder")).toHaveTextContent(
      "/Users/anna/hse-doc-studio/packs",
    );
    expect(
      screen.getByRole("link", { name: "Подключить репозиторий" }),
    ).toHaveAttribute("href", "/pack-studio");
    // Папка: ни меню git, ни разделов отправки.
    expect(screen.queryByTestId("sp-ch-menu")).not.toBeInTheDocument();
    expect(screen.queryByTestId("sp-ch-what")).not.toBeInTheDocument();
  });
});
