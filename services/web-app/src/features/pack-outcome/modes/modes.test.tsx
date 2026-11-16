import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
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
  packStudioKeys,
  type PackTree,
  type PackVersionRef,
  type PackWorkspace,
} from "@entities/pack-studio";
import {
  COURSEWORK_MATRIX,
  installOutcomeReference,
  modesCalls,
  outcomeReference,
  scenarioReference,
  setModesBehavior,
} from "@entities/pack-studio/reference";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { installViewport } from "@shared/lib/viewport/testing";
import { OutcomeBody } from "../OutcomeBody";

// Режимы центра «Матрица», «Атлас», «Сравнить» (F9) на эталонах контракта: сервер подменён,
// запросы идут тем же кодом, что к настоящему серверу.

// Сбой сервера (5xx) hook повторяет один раз через секунду: ошибку ждём дольше.
const SERVER_ERROR_WAIT = { timeout: 3500 };
const WS = "ws-modes";
const COURSEWORK: PackVersionRef = {
  pack: "hse-cs-sse",
  template: "coursework",
  version: "2026.1.6",
};
const VKR: PackVersionRef = {
  pack: "hse-cs-se",
  template: "vkr",
  version: "2026.1.2",
};
const NOW = "2026-11-16T09:30:00Z";

const workspace = (kind: "folder" | "git"): PackWorkspace => ({
  id: WS,
  kind,
  label: "packs",
  state: "ready",
  busy: false,
  packs_path: "packs",
  url: null,
  credential_id: null,
  service_access: false,
  insecure_http: false,
  folder: "/work/packs",
  base_branch: null,
  base_sha: null,
  fetched_at: null,
  work_branch: null,
  pr_url: null,
  pr_number: null,
  ci_status: null,
  fork_url: null,
  pushed_sha: null,
  error: null,
  created_at: NOW,
  updated_at: NOW,
});

const tree: PackTree = {
  workspace_id: WS,
  base_sha: null,
  packs: [
    {
      id: COURSEWORK.pack,
      path: COURSEWORK.pack,
      name: { ru: "ФКН, СПИ" },
      templates: [
        {
          id: COURSEWORK.template,
          path: `${COURSEWORK.pack}/templates/${COURSEWORK.template}`,
          name: { ru: "Курсовой проект" },
          default_version: COURSEWORK.version,
          versions: [
            {
              version: COURSEWORK.version,
              path: `${COURSEWORK.pack}/templates/${COURSEWORK.template}/versions/${COURSEWORK.version}`,
              status: "beta",
              released: false,
              modified: false,
            },
          ],
        },
      ],
    },
    {
      id: VKR.pack,
      path: VKR.pack,
      name: { ru: "ФКН, ПИ" },
      templates: [
        {
          id: VKR.template,
          path: `${VKR.pack}/templates/${VKR.template}`,
          name: { ru: "ВКР" },
          default_version: VKR.version,
          versions: [
            {
              version: VKR.version,
              path: `${VKR.pack}/templates/${VKR.template}/versions/${VKR.version}`,
              status: "beta",
              released: false,
              modified: false,
            },
          ],
        },
      ],
    },
  ],
  files: [],
  truncated: false,
};

const Probe = () => {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{`${pathname}${search}`}</output>;
};
/** Элемент списка по номеру; пустое место это ошибка теста, а не `undefined`. */
const nth = <T,>(list: readonly (T | null | undefined)[], index: number): T => {
  const item = list[index];
  if (item === undefined || item === null) {
    throw new Error(`no element #${String(index)}`);
  }
  return item;
};
const where = () => screen.getByTestId("location").textContent;

type Mount = { ref?: PackVersionRef; kind?: "folder" | "git" };

const mount = (
  search: string,
  { ref = COURSEWORK, kind = "folder" }: Mount = {},
) => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, retryDelay: 0 },
    },
  });
  client.setQueryData(packStudioKeys.tree(WS), tree);
  const path = `/pack-studio/w/${WS}/result/${ref.pack}/${ref.template}/${ref.version}`;
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`${path}?${search}`]}>
        <OutcomeBody workspace={workspace(kind)} version={ref} />
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
};

describe("режимы центра: Матрица, Атлас, Сравнить (F9)", () => {
  beforeAll(async () => {
    installOutcomeReference();
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    window.localStorage.clear();
    outcomeReference.setSource("reference");
    scenarioReference.reset();
    setModesBehavior("normal");
    modesCalls.reset();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    outcomeReference.setBehavior("normal");
    setModesBehavior("normal");
    scenarioReference.reset();
    window.localStorage.clear();
  });

  describe("вкладки", () => {
    it("tablist: четыре режима, выбран «Результат», клик пишет view в адрес", async () => {
      const user = userEvent.setup();
      mount("");
      const list = await screen.findByRole("tablist", {
        name: "Режимы экрана",
      });
      const tabs = within(list).getAllByRole("tab");
      expect(tabs.map((tab) => tab.textContent)).toEqual([
        "Результат",
        "Матрица",
        "Атлас",
        "Сравнить",
      ]);
      expect(tabs[0]).toHaveAttribute("aria-selected", "true");
      expect(tabs[0]).toHaveAttribute("tabindex", "0");
      expect(tabs[1]).toHaveAttribute("tabindex", "-1");
      await user.click(nth(tabs, 1));
      await waitFor(() => {
        expect(where()).toContain("view=matrix");
      });
      expect(await screen.findByTestId("outcome-matrix")).toBeInTheDocument();
      expect(screen.getByRole("tabpanel")).toHaveAttribute(
        "aria-labelledby",
        "po-view-tab-matrix",
      );
      await user.click(screen.getByTestId("outcome-view-result"));
      await waitFor(() => {
        expect(where()).not.toContain("view=");
      });
    });

    it("стрелки двигают фокус и не открывают режим, Enter открывает, Home и End в края", async () => {
      const user = userEvent.setup();
      mount("");
      const result = await screen.findByTestId("outcome-view-result");
      result.focus();
      await user.keyboard("{ArrowRight}");
      expect(screen.getByTestId("outcome-view-matrix")).toHaveFocus();
      expect(where()).not.toContain("view=");
      await user.keyboard("{End}");
      expect(screen.getByTestId("outcome-view-compare")).toHaveFocus();
      await user.keyboard("{ArrowRight}");
      expect(screen.getByTestId("outcome-view-result")).toHaveFocus();
      await user.keyboard("{ArrowLeft}");
      expect(screen.getByTestId("outcome-view-compare")).toHaveFocus();
      await user.keyboard("{Home}{ArrowRight}{Enter}");
      await waitFor(() => {
        expect(where()).toContain("view=matrix");
      });
    });

    it("в режиме «Как студент» вкладок нет, режим из адреса не действует", async () => {
      mount("mode=student&view=atlas");
      await screen.findByTestId("outcome-summary");
      expect(screen.queryByRole("tablist")).toBeNull();
      expect(screen.queryByTestId("outcome-atlas")).toBeNull();
    });
  });

  describe("матрица", () => {
    it("строки сценарии, столбцы разделы, в клетке значок, слово и число; итог прогона", async () => {
      mount("view=matrix");
      const grid = await screen.findByRole("grid");
      await waitFor(() => {
        expect(screen.getByTestId("outcome-matrix-summary")).toHaveTextContent(
          "2 совпало, 1 изменилось",
        );
      });
      const headers = within(grid)
        .getAllByRole("columnheader")
        .map((h) => h.textContent);
      expect(headers).toEqual([
        "Сценарий",
        "Документы",
        "Метаданные проекта",
        "Анкеты",
        "Участники",
        "Точки сдачи",
        "Маршрут подписания",
        "Проверки",
      ]);
      expect(within(grid).getAllByRole("row")).toHaveLength(4);
      const cell = screen.getByTestId(
        "outcome-matrix-cell-university-supervisor-route",
      );
      expect(cell).toHaveTextContent("Изменилось");
      expect(cell).toHaveTextContent("5");
      expect(cell).toHaveAccessibleName(
        "Магистрант один, научрук из ВШЭ, Маршрут подписания. Изменилось. 5 элементов",
      );
      expect(
        screen.getByTestId("outcome-matrix-cell-company-supervisor-checks"),
      ).toHaveTextContent("Не проверено");
      expect(
        screen.getByTestId("outcome-matrix-cell-company-supervisor-documents"),
      ).toHaveTextContent("Совпало");
      expect(
        screen.getByTestId("outcome-matrix-summary").closest("[role=status]"),
      ).not.toBeNull();
    });

    it("одинаковые клетки столбца помечены одной буквой", async () => {
      mount("view=matrix");
      const cell = await screen.findByTestId(
        "outcome-matrix-cell-no-supervisor-documents",
      );
      expect(cell.querySelector(".mx-group")).toHaveTextContent("A");
      expect(cell.getAttribute("aria-label")).toContain("группа A");
      // Маршрут у сценариев разный: букв нет.
      expect(
        screen
          .getByTestId("outcome-matrix-cell-no-supervisor-route")
          .querySelector(".mx-group"),
      ).toBeNull();
    });

    it("клик по клетке выбирает сценарий и раздел и показывает расхождение", async () => {
      const user = userEvent.setup();
      mount("view=matrix");
      await user.click(
        await screen.findByTestId(
          "outcome-matrix-cell-university-supervisor-route",
        ),
      );
      await waitFor(() => {
        expect(where()).toContain("scenario=university-supervisor");
      });
      const detail = await screen.findByTestId("outcome-matrix-detail");
      expect(detail).toHaveTextContent("Маршрут подписания");
      expect(detail).toHaveTextContent("Изменилось");
      // Расхождение из прогона сценариев (F8): изменения только этого раздела.
      await waitFor(() => {
        expect(
          within(detail).getByTestId("outcome-matrix-changes"),
        ).toBeInTheDocument();
      });
      expect(
        screen.getByTestId("outcome-matrix-cell-university-supervisor-route"),
      ).toHaveAttribute("aria-pressed", "true");
      await user.click(screen.getByTestId("outcome-matrix-show"));
      await waitFor(() => {
        expect(where()).toContain("scenario=university-supervisor");
        expect(where()).not.toContain("view=matrix");
      });
    });

    it("стрелки ходят по клеткам, в Tab одна точка входа", async () => {
      const user = userEvent.setup();
      mount("view=matrix");
      const first = await screen.findByTestId(
        "outcome-matrix-cell-company-supervisor-documents",
      );
      expect(first).toHaveAttribute("tabindex", "0");
      expect(
        screen.getByTestId("outcome-matrix-cell-company-supervisor-meta"),
      ).toHaveAttribute("tabindex", "-1");
      first.focus();
      await user.keyboard("{ArrowRight}");
      expect(
        screen.getByTestId("outcome-matrix-cell-company-supervisor-meta"),
      ).toHaveFocus();
      await user.keyboard("{ArrowDown}");
      expect(
        screen.getByTestId("outcome-matrix-cell-no-supervisor-meta"),
      ).toHaveFocus();
      await user.keyboard("{End}");
      expect(
        screen.getByTestId("outcome-matrix-cell-no-supervisor-checks"),
      ).toHaveFocus();
      await user.keyboard("{Home}");
      expect(
        screen.getByTestId("outcome-matrix-cell-no-supervisor-documents"),
      ).toHaveFocus();
    });

    it("«Прогнать заново» перечитывает матрицу и прогон", async () => {
      const user = userEvent.setup();
      mount("view=matrix");
      await screen.findByRole("grid");
      const run = vi.spyOn(packOutcomeApi, "runScenarios");
      const matrix = vi.spyOn(packOutcomeApi, "matrix");
      await user.click(screen.getByTestId("outcome-matrix-rerun"));
      await waitFor(() => {
        expect(run).toHaveBeenCalled();
        expect(matrix).toHaveBeenCalled();
      });
    });

    it("«Относительно базы»: у папки без git недоступно, в git-пространстве запрос с against и метка ~", async () => {
      const user = userEvent.setup();
      const { unmount } = render(<span />);
      unmount();
      mount("view=matrix");
      await screen.findByRole("grid");
      expect(screen.getByTestId("outcome-matrix-against-base")).toBeDisabled();
      cleanup();

      const matrix = vi.spyOn(packOutcomeApi, "matrix");
      mount("view=matrix&against=base", { kind: "git" });
      const cell = await screen.findByTestId(
        "outcome-matrix-cell-university-supervisor-route",
      );
      expect(matrix.mock.calls[0]?.[2]).toMatchObject({ against: "base" });
      await waitFor(() => {
        expect(cell.querySelector(".mx-base")).toHaveTextContent("~");
      });
      expect(cell.getAttribute("aria-label")).toContain(
        "изменилось против базы",
      );
      expect(screen.getByTestId("outcome-matrix-against-base")).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      await user.click(screen.getByTestId("outcome-matrix-against-expected"));
      await waitFor(() => {
        expect(where()).not.toContain("against=");
      });
    });

    it("нет сценариев: подсказка и кнопка создать", async () => {
      outcomeReference.setBehavior("no_scenarios");
      mount("view=matrix");
      const empty = await screen.findByTestId("outcome-matrix-empty");
      expect(empty).toHaveTextContent("Сценариев пока нет");
      expect(empty).toHaveTextContent("Студия покажет, что изменилось");
      await userEvent
        .setup()
        .click(await screen.findByTestId("outcome-matrix-create"));
      expect(await screen.findByRole("dialog")).toBeInTheDocument();
    });

    it("строка с ошибкой показывает причину, клетки без результата", async () => {
      const broken = structuredClone(COURSEWORK_MATRIX);
      const row = broken.rows[0];
      if (!row) throw new Error("no row");
      row.status = "error";
      row.message = "Вводная «supervisor» не подходит к версии";
      row.cells = row.cells.map((cell) => ({
        ...cell,
        status: "error" as const,
        count: 0,
        fingerprint: "",
        changed: null,
      }));
      vi.spyOn(packOutcomeApi, "matrix").mockResolvedValue({
        data: broken,
        etag: null,
      });
      mount("view=matrix");
      expect(
        await screen.findByTestId("outcome-matrix-message-company-supervisor"),
      ).toHaveTextContent("не подходит к версии");
      const cell = screen.getByTestId(
        "outcome-matrix-cell-company-supervisor-route",
      );
      expect(cell).toHaveTextContent("Ошибка");
      expect(cell).toHaveTextContent("–");
      expect(screen.getByTestId("outcome-matrix-summary")).toHaveTextContent(
        "1 ошибка",
      );
    });

    it("outcome_too_large: пояснение с числами и кнопка «Показать первые 20»", async () => {
      const user = userEvent.setup();
      setModesBehavior("too_large");
      mount("view=matrix");
      const notice = await screen.findByTestId("outcome-mode-too-large");
      expect(notice).toHaveTextContent("Ответ слишком большой");
      expect(notice).toHaveTextContent("11");
      expect(notice).toHaveTextContent("8");
      setModesBehavior("normal");
      const matrix = vi.spyOn(packOutcomeApi, "matrix");
      await user.click(screen.getByTestId("outcome-matrix-subset"));
      await screen.findByRole("grid");
      expect(matrix.mock.calls.at(-1)?.[2]).toMatchObject({
        scenarios: expect.arrayContaining(["company-supervisor"]) as unknown,
      });
      expect(
        screen.getByTestId("outcome-matrix-subset-note"),
      ).toBeInTheDocument();
    });

    it("занятый сервер: повтор сам, затем таблица", async () => {
      setModesBehavior("busy");
      mount("view=matrix");
      expect(
        await screen.findByRole("grid", undefined, { timeout: 4000 }),
      ).toBeInTheDocument();
      expect(modesCalls.count("matrix")).toBe(2);
    });

    it("сбой сервера: ошибка с повтором", async () => {
      const user = userEvent.setup();
      setModesBehavior("fail");
      mount("view=matrix");
      expect(
        await screen.findByTestId(
          "outcome-mode-error",
          undefined,
          SERVER_ERROR_WAIT,
        ),
      ).toHaveTextContent("Не удалось построить матрицу");
      setModesBehavior("normal");
      await user.click(screen.getByTestId("outcome-mode-retry"));
      expect(await screen.findByRole("grid")).toBeInTheDocument();
    });

    it("загрузка: скелет", async () => {
      vi.spyOn(packOutcomeApi, "matrix").mockImplementation(
        () => new Promise(() => undefined),
      );
      mount("view=matrix");
      expect(
        await screen.findByTestId("outcome-matrix-loading"),
      ).toBeInTheDocument();
    });
  });

  describe("атлас", () => {
    it("курсовой: сводка, измерения, игнорируемые с причиной, строки с исходами", async () => {
      mount("view=atlas");
      const summary = await screen.findByTestId("outcome-atlas-summary");
      expect(summary).toHaveTextContent(
        "12 различных исходов в 12 строках (из 576 комбинаций)",
      );
      expect(
        screen.getByRole("heading", { name: "Измерения: 3" }),
      ).toBeInTheDocument();
      const ignored = screen.getByTestId("outcome-atlas-ignored");
      expect(ignored).toHaveTextContent("Не влияют: 6");
      expect(ignored).toHaveTextContent("ничего не меняет");
      expect(ignored).toHaveTextContent("меняет только имена файлов");
      expect(screen.getAllByTestId("outcome-atlas-row")).toHaveLength(12);
      expect(screen.getByTestId("outcome-atlas-count")).toHaveTextContent(
        "Показано строк: 12 из 12",
      );
      expect(modesCalls.count("atlas")).toBe(1);
    });

    it("текущая строка отмечена по вводным адреса, с исходом из атласа без запроса", async () => {
      mount("view=atlas&i.supervisor=company&i.co_supervisor=yes");
      const detail = await screen.findByTestId("outcome-atlas-detail");
      expect(detail).toHaveTextContent("Исход");
      expect(detail).toHaveTextContent("В комплекте");
      expect(
        screen
          .getAllByTestId("outcome-atlas-row")
          .filter((row) => row.getAttribute("data-current") === "true"),
      ).toHaveLength(1);
      expect(modesCalls.count("atlas")).toBe(1);
    });

    it("выбор строки применяет её вводные без нового запроса атласа", async () => {
      const user = userEvent.setup();
      mount("view=atlas");
      await screen.findByTestId("outcome-atlas-summary");
      const row = screen
        .getAllByTestId("outcome-atlas-row")
        .find((item) => item.getAttribute("data-key") === "company|yes|yes");
      if (!row) throw new Error("row not found");
      const outcome = vi.spyOn(packOutcomeApi, "outcome");
      await user.click(row);
      await waitFor(() => {
        expect(where()).toContain("i.supervisor=company");
        expect(where()).toContain("i.co_supervisor=yes");
      });
      // Умолчание измерения (academic_supervisor=yes) в адрес не пишется.
      expect(where()).not.toContain("i.academic_supervisor");
      expect(modesCalls.count("atlas")).toBe(1);
      await waitFor(() => {
        expect(outcome).toHaveBeenCalled();
      });
      expect(outcome.mock.calls.at(-1)?.[2]).toMatchObject({
        inputs: { supervisor: "company", co_supervisor: "yes" },
      });
      await waitFor(() => {
        expect(
          screen
            .getAllByTestId("outcome-atlas-row")
            .find((item) => item.getAttribute("data-current") === "true"),
        ).toHaveAttribute("data-key", "company|yes|yes");
      });
      expect(screen.getByTestId("outcome-atlas-live")).toHaveTextContent(
        "Применены вводные исхода",
      );
    });

    it("поверх сценария значения измерений пишутся все", async () => {
      const user = userEvent.setup();
      mount("view=atlas&scenario=company-supervisor");
      await screen.findByTestId("outcome-atlas-summary");
      await user.click(nth(screen.getAllByTestId("outcome-atlas-row"), 0));
      await waitFor(() => {
        expect(where()).toContain("scenario=company-supervisor");
        expect(where()).toContain("i.supervisor=university");
        expect(where()).toContain("i.academic_supervisor=yes");
      });
    });

    it("ВКР: 864 строки листаются по 60, поиск и фильтр режут таблицу", async () => {
      const user = userEvent.setup();
      mount("view=atlas", { ref: VKR });
      const summary = await screen.findByTestId("outcome-atlas-summary");
      expect(summary).toHaveTextContent("в 864 строках (из 5184 комбинаций)");
      expect(screen.getAllByTestId("outcome-atlas-row")).toHaveLength(60);
      expect(screen.getByTestId("outcome-atlas-count")).toHaveTextContent(
        "Показано строк: 60 из 864",
      );
      await user.click(screen.getByTestId("outcome-atlas-more"));
      expect(screen.getAllByTestId("outcome-atlas-row")).toHaveLength(120);
      fireEvent.change(screen.getByTestId("outcome-atlas-search"), {
        target: { value: "company" },
      });
      await waitFor(() => {
        expect(screen.getByTestId("outcome-atlas-count")).toHaveTextContent(
          /из 288/,
        );
      });
      expect(screen.queryByTestId("outcome-atlas-more")).not.toBeNull();
      fireEvent.change(screen.getByTestId("outcome-atlas-search"), {
        target: { value: "company nda" },
      });
      await waitFor(() => {
        expect(screen.getByTestId("outcome-atlas-count")).toHaveTextContent(
          /из \d+/,
        );
      });
      fireEvent.change(screen.getByTestId("outcome-atlas-search"), {
        target: { value: "нет такого значения" },
      });
      expect(
        await screen.findByTestId("outcome-atlas-noresults"),
      ).toBeInTheDocument();
      await user.click(screen.getByTestId("outcome-atlas-reset"));
      await waitFor(() => {
        expect(screen.getAllByTestId("outcome-atlas-row")).toHaveLength(60);
      });
    });

    it("фильтр по измерению и порядок «по числу строк исхода»", async () => {
      mount("view=atlas");
      await screen.findByTestId("outcome-atlas-summary");
      fireEvent.change(screen.getByTestId("outcome-atlas-filter-supervisor"), {
        target: { value: "none" },
      });
      await waitFor(() => {
        const rows = screen.getAllByTestId("outcome-atlas-row");
        expect(
          rows.every((row) => row.getAttribute("data-key")?.startsWith("none")),
        ).toBe(true);
      });
      fireEvent.change(screen.getByTestId("outcome-atlas-sort"), {
        target: { value: "rows" },
      });
      expect(screen.getByTestId("outcome-atlas-sort")).toHaveValue("rows");
    });

    it("группы одинаковых исходов: список исходов и переход к их строкам", async () => {
      const user = userEvent.setup();
      mount("view=atlas", { ref: VKR });
      await screen.findByTestId("outcome-atlas-summary");
      await user.click(screen.getByTestId("outcome-atlas-group-outcomes"));
      const list = screen.getByTestId("outcome-atlas-outcomes");
      expect(within(list).getAllByRole("listitem").length).toBeGreaterThan(0);
      await user.click(screen.getByTestId("outcome-atlas-show-o1"));
      expect(
        screen.getByTestId("outcome-atlas-outcome-filter"),
      ).toHaveTextContent("o1");
      const rows = screen.getAllByTestId("outcome-atlas-row");
      expect(rows.length).toBeGreaterThan(0);
      for (const row of rows) {
        expect(
          within(nth([row.closest("li")], 0)).getByTestId(
            "outcome-atlas-outcome",
          ),
        ).toHaveTextContent("o1");
      }
    });

    it("закрепить вводную: адрес, запрос с pin, чип и снятие", async () => {
      const user = userEvent.setup();
      mount("view=atlas");
      await screen.findByTestId("outcome-atlas-summary");
      const atlas = vi.spyOn(packOutcomeApi, "atlas");
      fireEvent.change(screen.getByTestId("outcome-atlas-pin-supervisor"), {
        target: { value: "company" },
      });
      await waitFor(() => {
        expect(where()).toContain("p.supervisor=company");
      });
      await waitFor(() => {
        expect(atlas).toHaveBeenCalled();
      });
      expect(atlas.mock.calls.at(-1)?.[2]).toMatchObject({
        pin: { supervisor: "company" },
      });
      await waitFor(() => {
        expect(screen.getAllByTestId("outcome-atlas-row")).toHaveLength(4);
      });
      const pins = screen.getByTestId("outcome-atlas-pins");
      expect(pins).toHaveTextContent("Закреплено");
      await user.click(within(pins).getByRole("button"));
      await waitFor(() => {
        expect(where()).not.toContain("p.supervisor");
      });
    });

    it("atlas_too_large: числа и выбор вводных для закрепления, затем таблица", async () => {
      setModesBehavior("atlas_too_large");
      mount("view=atlas");
      const notice = await screen.findByTestId("outcome-mode-atlas-too-large");
      expect(notice).toHaveTextContent("Слишком много комбинаций");
      expect(notice).toHaveTextContent("6912");
      expect(notice).toHaveTextContent("2000");
      expect(notice).toHaveTextContent("Зафиксируйте часть вводных");
      expect(screen.queryByTestId("outcome-mode-retry")).toBeNull();
      expect(
        await screen.findByTestId("outcome-atlas-pinchoose"),
      ).toBeInTheDocument();
      setModesBehavior("normal");
      fireEvent.change(screen.getByTestId("outcome-atlas-pin-supervisor"), {
        target: { value: "university" },
      });
      await waitFor(() => {
        expect(where()).toContain("p.supervisor=university");
      });
      expect(
        await screen.findByTestId("outcome-atlas-summary"),
      ).toBeInTheDocument();
    });

    it("занятый сервер: сам повторяет, затем атлас", async () => {
      setModesBehavior("busy");
      mount("view=atlas");
      expect(
        await screen.findByTestId("outcome-atlas-summary", undefined, {
          timeout: 4000,
        }),
      ).toBeInTheDocument();
      expect(modesCalls.count("atlas")).toBe(2);
    });

    it("загрузка: скелет и «Отмена», после отмены «Посчитать снова»", async () => {
      const user = userEvent.setup();
      const atlas = vi.spyOn(packOutcomeApi, "atlas").mockImplementation(
        (_id, _ref, _request, _known, signal) =>
          new Promise((_resolve, reject) => {
            signal?.addEventListener("abort", () => {
              reject(new DOMException("aborted", "AbortError"));
            });
          }),
      );
      mount("view=atlas");
      expect(
        await screen.findByTestId("outcome-atlas-loading"),
      ).toBeInTheDocument();
      expect(screen.getByText(/Считаю атлас/)).toBeInTheDocument();
      await user.click(screen.getByTestId("outcome-atlas-cancel"));
      expect(
        await screen.findByTestId("outcome-atlas-cancelled"),
      ).toHaveTextContent("Расчёт отменён");
      atlas.mockRestore();
      await user.click(screen.getByTestId("outcome-atlas-again"));
      expect(
        await screen.findByTestId("outcome-atlas-summary"),
      ).toBeInTheDocument();
    });

    it("сбой: ошибка с повтором", async () => {
      const user = userEvent.setup();
      setModesBehavior("fail");
      mount("view=atlas");
      expect(
        await screen.findByTestId(
          "outcome-mode-error",
          undefined,
          SERVER_ERROR_WAIT,
        ),
      ).toHaveTextContent("Не удалось построить атлас");
      setModesBehavior("normal");
      await user.click(screen.getByTestId("outcome-mode-retry"));
      expect(
        await screen.findByTestId("outcome-atlas-summary"),
      ).toBeInTheDocument();
    });

    it("клавиша / ставит курсор в поиск", async () => {
      const user = userEvent.setup();
      mount("view=atlas");
      await screen.findByTestId("outcome-atlas-summary");
      screen.getAllByTestId("outcome-atlas-row")[0]?.focus();
      await user.keyboard("/");
      expect(screen.getByTestId("outcome-atlas-search")).toHaveFocus();
      // В самом поле символ вводится как обычно.
      await user.keyboard("/");
      expect(screen.getByTestId("outcome-atlas-search")).toHaveValue("/");
    });

    it("«Открыть результат» возвращает в режим результата с теми же вводными", async () => {
      const user = userEvent.setup();
      mount("view=atlas&i.supervisor=company");
      await user.click(await screen.findByTestId("outcome-atlas-open-result"));
      await waitFor(() => {
        expect(where()).not.toContain("view=");
        expect(where()).toContain("i.supervisor=company");
      });
    });
  });

  describe("сравнить", () => {
    it("два сценария по умолчанию: изменения по разделам со знаком, словом и «было» и «стало»", async () => {
      const compare = vi.spyOn(packOutcomeApi, "compare");
      mount("view=compare");
      const summary = await screen.findByTestId("outcome-compare-summary");
      expect(summary).toHaveTextContent("Различий: 7");
      expect(compare.mock.calls[0]?.[2]).toMatchObject({
        left: { scenario: "company-supervisor" },
        right: { scenario: "university-supervisor" },
      });
      const route = screen.getByTestId("outcome-compare-section-route");
      expect(route).toHaveTextContent("+3 добавлено");
      expect(route).toHaveTextContent("~1 изменено");
      expect(route).toHaveTextContent("2 убрано");
      const items = within(route).getAllByTestId(/outcome-change-/);
      const step = items.find(
        (item) =>
          item.getAttribute("data-testid") === "outcome-change-route_step" &&
          item.getAttribute("data-symbol") === "changed",
      );
      expect(step).toHaveTextContent("~");
      expect(step).toHaveTextContent("Изменено");
      expect(step).toHaveTextContent("было: supervisor");
      expect(step).toHaveTextContent("стало: supervisor, co_supervisor");
      expect(
        within(
          screen.getByTestId("outcome-compare-section-participants"),
        ).getByText("Добавлено"),
      ).toBeInTheDocument();
      // Разделы без изменений не показаны, пока включено «только отличия».
      expect(
        screen.queryByTestId("outcome-compare-section-documents"),
      ).toBeNull();
    });

    it("«Показывать только отличия» выключен: видны и разделы без изменений", async () => {
      const user = userEvent.setup();
      mount("view=compare");
      await screen.findByTestId("outcome-compare-summary");
      await user.click(screen.getByTestId("outcome-compare-only"));
      const docs = screen.getByTestId("outcome-compare-section-documents");
      expect(docs).toHaveTextContent("Без изменений");
    });

    it("причины: правило с файлом, исходы слева и справа, факты и «Открыть правило»", async () => {
      const user = userEvent.setup();
      mount("view=compare");
      const route = await screen.findByTestId("outcome-compare-section-route");
      const toggle = nth(within(route).getAllByTestId("outcome-change-why"), 0);
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      await user.click(toggle);
      expect(toggle).toHaveAttribute("aria-expanded", "true");
      const reasons = nth(
        within(route).getAllByTestId("outcome-change-reasons"),
        0,
      );
      expect(reasons).toHaveTextContent("version.yaml");
      expect(reasons).toHaveTextContent(
        "/pack_submission/profiles/0/signing_slots/0/when",
      );
      expect(reasons).toHaveTextContent("Слева");
      expect(reasons).toHaveTextContent("Справа");
      expect(reasons).toHaveTextContent("Выполнено");
      await user.click(within(reasons).getByTestId("outcome-change-open-rule"));
      await waitFor(() => {
        expect(where()).toContain("version.yaml");
      });
      expect(where()).toContain("at=");
    });

    it("одинаковые стороны: «Различий нет»", async () => {
      mount(
        "view=compare&left=scenario:company-supervisor&right=scenario:company-supervisor",
      );
      expect(
        await screen.findByTestId("outcome-compare-identical"),
      ).toHaveTextContent("Различий нет");
    });

    it("нет базы: «Сравнивать не с чем», причина и переход к двум сценариям", async () => {
      const user = userEvent.setup();
      setModesBehavior("no_base");
      mount("view=compare&left=screen@base&right=screen@work_tree", {
        kind: "git",
      });
      const notice = await screen.findByTestId("outcome-mode-no-base");
      expect(notice).toHaveTextContent("Сравнивать не с чем");
      expect(notice).toHaveTextContent("нет базовой ветки");
      setModesBehavior("normal");
      await user.click(screen.getByTestId("outcome-compare-fallback"));
      await waitFor(() => {
        expect(where()).toContain("left=scenario");
      });
      expect(
        await screen.findByTestId("outcome-compare-summary"),
      ).toBeInTheDocument();
    });

    it("быстрый выбор: база и рабочее дерево только в git, «Поменять местами» меняет стороны", async () => {
      const user = userEvent.setup();
      mount("view=compare");
      await screen.findByTestId("outcome-compare-summary");
      expect(screen.getByTestId("outcome-compare-preset-base")).toBeDisabled();
      expect(screen.getByTestId("outcome-compare-preset-head")).toBeDisabled();
      await user.click(screen.getByTestId("outcome-compare-preset-swap"));
      await waitFor(() => {
        expect(where()).toContain("left=scenario%3Auniversity-supervisor");
        expect(where()).toContain("right=scenario%3Acompany-supervisor");
      });
      cleanup();
      mount("view=compare", { kind: "git" });
      await screen.findByTestId("outcome-compare-summary");
      await user.click(screen.getByTestId("outcome-compare-preset-base"));
      await waitFor(() => {
        expect(where()).toContain("left=screen%40base");
        expect(where()).toContain("right=screen%40work_tree");
      });
    });

    it("выбор стороны: сценарий и состояние пишутся в адрес и уходят в запрос", async () => {
      const compare = vi.spyOn(packOutcomeApi, "compare");
      mount("view=compare", { kind: "git" });
      await screen.findByTestId("outcome-compare-summary");
      fireEvent.change(screen.getByTestId("outcome-compare-right-source"), {
        target: { value: "scenario:university-supervisor" },
      });
      fireEvent.change(screen.getByTestId("outcome-compare-right-state"), {
        target: { value: "head" },
      });
      await waitFor(() => {
        expect(where()).toContain(
          "right=scenario%3Auniversity-supervisor%40head",
        );
      });
      await waitFor(() => {
        expect(compare.mock.calls.at(-1)?.[2]).toMatchObject({
          right: { scenario: "university-supervisor", state: "head" },
        });
      });
    });

    it("«Зафиксировать вводные экрана»: сторона со своими вводными", async () => {
      const user = userEvent.setup();
      mount("view=compare&i.kind=research&scenario=company-supervisor");
      await screen.findByTestId("outcome-compare-summary");
      await user.click(screen.getByTestId("outcome-compare-right-freeze"));
      await waitFor(() => {
        const value = new URLSearchParams((where() ?? "").split("?")[1]).get(
          "right",
        );
        expect(value).toMatch(/^inputs:/);
        expect(value).toContain("kind=research");
        expect(value).toContain("supervisor=company");
      });
      expect(screen.getByTestId("outcome-compare-right")).toHaveTextContent(
        "Зафиксировано вводных",
      );
    });

    it("загрузка и сбой: скелет, ошибка с повтором", async () => {
      const user = userEvent.setup();
      setModesBehavior("fail");
      mount("view=compare");
      expect(
        await screen.findByTestId(
          "outcome-mode-error",
          undefined,
          SERVER_ERROR_WAIT,
        ),
      ).toHaveTextContent("Не удалось сравнить");
      setModesBehavior("normal");
      await user.click(screen.getByTestId("outcome-mode-retry"));
      expect(
        await screen.findByTestId("outcome-compare-summary"),
      ).toBeInTheDocument();
    });

    it("сторона без сценария к выбранной: из матрицы «Сравнить с другим»", async () => {
      const compare = vi.spyOn(packOutcomeApi, "compare");
      mount("view=compare&left=scenario:no-supervisor");
      await screen.findByTestId("outcome-compare-summary");
      expect(compare.mock.calls[0]?.[2]).toMatchObject({
        left: { scenario: "no-supervisor" },
        right: { scenario: "company-supervisor" },
      });
    });
  });

  describe("языки и телефон", () => {
    it("английский: вкладки, слова клеток и сводка атласа", async () => {
      await i18n.changeLanguage("en");
      try {
        const user = userEvent.setup();
        mount("view=matrix");
        const tabs = await screen.findAllByRole("tab");
        expect(tabs.map((tab) => tab.textContent)).toEqual([
          "Result",
          "Matrix",
          "Atlas",
          "Compare",
        ]);
        expect(
          await screen.findByTestId(
            "outcome-matrix-cell-university-supervisor-route",
          ),
        ).toHaveTextContent("Changed");
        await user.click(screen.getByTestId("outcome-view-atlas"));
        expect(
          await screen.findByTestId("outcome-atlas-summary"),
        ).toHaveTextContent(
          "12 distinct outcomes in 12 rows (from 576 combinations)",
        );
        await user.click(screen.getByTestId("outcome-view-compare"));
        expect(
          await screen.findByTestId("outcome-compare-summary"),
        ).toHaveTextContent("Differences: 7");
      } finally {
        await i18n.changeLanguage("ru");
      }
    });

    it("телефон: режимы на месте, матрица остаётся таблицей с подписью раздела в клетке", async () => {
      const viewport = installViewport(360);
      try {
        const user = userEvent.setup();
        mount("view=matrix");
        const cell = await screen.findByTestId(
          "outcome-matrix-cell-company-supervisor-route",
        );
        // Подпись раздела в клетке нужна на телефоне, где шапка скрыта; в DOM она есть всегда.
        expect(cell.querySelector(".mx-cell-section")).toHaveTextContent(
          "Маршрут подписания",
        );
        expect(screen.getByTestId("outcome-modes")).toBeInTheDocument();
        await user.click(screen.getByTestId("outcome-view-atlas"));
        expect(
          await screen.findByTestId("outcome-atlas-summary"),
        ).toBeInTheDocument();
        await user.click(screen.getByTestId("outcome-view-compare"));
        expect(
          await screen.findByTestId("outcome-compare-summary"),
        ).toBeInTheDocument();
        // Правила открываются только на компьютере: кнопки «Открыть правило» нет.
        const toggle = nth(screen.getAllByTestId("outcome-change-why"), 0);
        await user.click(toggle);
        expect(screen.queryByTestId("outcome-change-open-rule")).toBeNull();
      } finally {
        viewport.restore();
      }
    });
  });
});
