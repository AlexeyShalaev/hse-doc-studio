import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type MockInstance,
} from "vitest";
import type { ZodType } from "zod";
import {
  PackPreviewBuildSchema,
  PackPreviewOptionsSchema,
  notifyPackFilesSaved,
  packStudioApi,
  packStudioKeys,
  type PackPreviewBuild,
  type PackTree,
  type PackVersionRef,
  type PackWorkspace,
} from "@entities/pack-studio";
import {
  installOutcomeReference,
  outcomeReference,
  resetPreviewReference,
} from "@entities/pack-studio/reference";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { installViewport } from "@shared/lib/viewport/testing";
import { resetPreviewSelections } from "@features/pack-preview";
import { OutcomeBody } from "../../OutcomeBody";
import { resetPreviewMemory } from "../../lib/previewStore";
import { AUTO_DEBOUNCE_MS, QuotaCountdown } from "./PreviewPanel";

// pdf.js в jsdom не поднимается: просмотрщик подменён адресом файла.
vi.mock("@shared/ui", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@shared/ui")),
  PdfViewer: ({ url }: { url: string }) => (
    <div data-testid="pdf-viewer" data-url={url} />
  ),
}));

// Предпросмотр PDF на экране «Результат» (срез F12): результат и сценарии идут из эталонов,
// эндпоинты предпросмотра подменены на уровне клиента API (как в тесте вкладки «Файлы»).

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../../contracts/pack-studio/fixtures",
);
const fixture = <T,>(schema: ZodType<T>, dir: string, name: string): T =>
  schema.parse(
    JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8")),
  );
const OPTIONS = fixture(
  PackPreviewOptionsSchema,
  "PackPreviewOptions",
  "with_variants",
);
const build = (name: string, patch: Partial<PackPreviewBuild> = {}) => ({
  ...fixture(PackPreviewBuildSchema, "PackPreviewBuild", name),
  ...patch,
});

const WS = "ws-outcome";
const REF: PackVersionRef = {
  pack: "hse-cs-se",
  template: "vkr",
  version: "2026.1.2",
};
const NOW = "2026-11-16T09:30:00Z";
const AUTO_KEY = "hse-studio.packOutcome.previewAuto";

const workspace: PackWorkspace = {
  id: WS,
  kind: "folder",
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
};

const tree: PackTree = {
  workspace_id: WS,
  base_sha: null,
  packs: [
    {
      id: "hse-cs-se",
      path: "hse-cs-se",
      name: { ru: "ФКН, Программная инженерия" },
      templates: [
        {
          id: "vkr",
          path: "hse-cs-se/templates/vkr",
          name: { ru: "ВКР бакалавра", en: "Bachelor thesis" },
          default_version: "2026.1.1",
          versions: [
            {
              version: "2026.1.2",
              path: "hse-cs-se/templates/vkr/versions/2026.1.2",
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

const client = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: Infinity,
        staleTime: Infinity,
        retryDelay: 0,
      },
      mutations: { retry: false },
    },
  });

const screenOf = (qc: QueryClient, search: string) => (
  <QueryClientProvider client={qc}>
    <MemoryRouter
      initialEntries={[
        `/pack-studio/w/${WS}/result/hse-cs-se/vkr/2026.1.2${search ? `?${search}` : ""}`,
      ]}
    >
      <OutcomeBody workspace={workspace} version={REF} />
    </MemoryRouter>
  </QueryClientProvider>
);

const mount = (search = "") => {
  const qc = client();
  qc.setQueryData(packStudioKeys.tree(WS), tree);
  const view = render(screenOf(qc, search));
  return { qc, ...view };
};

const QUEUED = build("queued", { document: "technical_specification" });
const DONE = (patch: Partial<PackPreviewBuild> = {}) =>
  build("succeeded", {
    id: QUEUED.id,
    document: "technical_specification",
    variant: "espd",
    file_name: "ТЗ — Иванов.pdf",
    ...patch,
  });

type Api = {
  start: MockInstance<(typeof packStudioApi)["startPreview"]>;
  poll: MockInstance<(typeof packStudioApi)["previewBuild"]>;
  cancel: MockInstance<(typeof packStudioApi)["cancelPreview"]>;
};
const stubApi = (done: PackPreviewBuild = DONE()): Api => {
  vi.spyOn(packStudioApi, "previewOptions").mockResolvedValue(OPTIONS);
  return {
    start: vi.spyOn(packStudioApi, "startPreview").mockResolvedValue([done]),
    poll: vi.spyOn(packStudioApi, "previewBuild").mockResolvedValue(done),
    cancel: vi
      .spyOn(packStudioApi, "cancelPreview")
      .mockResolvedValue(build("queued", { status: "cancelled" })),
  };
};

const openPreview = async (doc = "technical_specification") => {
  const button = await screen.findByTestId(`outcome-doc-${doc}-preview`);
  await waitFor(() => {
    expect(button).toBeEnabled();
  });
  fireEvent.click(button);
  return screen.findByRole("dialog");
};

/** Radix Select: открыть список и выбрать пункт по названию. */
const choose = async (label: string | RegExp, option: string | RegExp) => {
  await userEvent.click(screen.getByRole("combobox", { name: label }));
  await userEvent.click(await screen.findByRole("option", { name: option }));
};

describe("предпросмотр PDF на экране «Результат»", () => {
  beforeAll(async () => {
    installOutcomeReference();
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
    await i18n.changeLanguage("ru");
    // Radix Select ловит указатель; в jsdom этих методов нет.
    const proto = Element.prototype as Partial<Element> & {
      hasPointerCapture?: (id: number) => boolean;
      releasePointerCapture?: (id: number) => void;
      scrollIntoView?: () => void;
    };
    proto.hasPointerCapture ??= () => false;
    proto.releasePointerCapture ??= () => undefined;
    proto.scrollIntoView ??= () => undefined;
  });
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    outcomeReference.setSource("reference");
  });
  afterEach(async () => {
    cleanup();
    vi.restoreAllMocks();
    resetPreviewMemory();
    resetPreviewSelections();
    resetPreviewReference();
    window.sessionStorage.clear();
    outcomeReference.setSource("reference");
    outcomeReference.setBehavior("normal");
    await i18n.changeLanguage("ru");
  });

  describe("открытие из секции «Документы»", () => {
    it("клик по документу открывает панель и собирает его с текущими вводными", async () => {
      const api = stubApi();
      mount();
      const panel = await openPreview();
      expect(screen.getByTestId("outcome-preview-drawer")).toBe(panel);
      expect(
        screen.getByRole("dialog", { name: /Предпросмотр PDF:/ }),
      ).toBeInTheDocument();
      await waitFor(() => {
        expect(api.start).toHaveBeenCalledTimes(1);
      });
      expect(api.start).toHaveBeenCalledWith(WS, REF, {
        documents: ["technical_specification"],
        example: "auto:normal",
        combination: {
          lang: "ru",
          kind: "project",
          staffing: "solo",
          supervisor: "university",
          co_supervisor: "no",
          academic_supervisor: "yes",
        },
        variant: "espd",
      });
      // Результат остаётся рядом: сам экран не ушёл в «Файлы».
      expect(screen.getByTestId("outcome-documents")).toBeInTheDocument();
      expect(await within(panel).findByTestId("pdf-viewer")).toHaveAttribute(
        "data-url",
        expect.stringContaining(QUEUED.id),
      );
    });

    it("данные сборки: вариант, итоговое имя файла, набор данных", async () => {
      stubApi();
      mount();
      await openPreview();
      expect(
        await screen.findByTestId("outcome-preview-info-variant"),
      ).toHaveTextContent("ГОСТ 19 ЕСПД");
      expect(screen.getByTestId("outcome-preview-info-file")).toHaveTextContent(
        "ТЗ — Иванов.pdf",
      );
      expect(
        screen.getByTestId("outcome-preview-info-example"),
      ).toHaveTextContent("approval-gate");
      expect(
        screen.queryByTestId("outcome-preview-info-scenario"),
      ).not.toBeInTheDocument();
    });

    it("второй клик и крестик закрывают панель, повторный клик собирает снова", async () => {
      const api = stubApi();
      mount();
      await openPreview();
      await waitFor(() => {
        expect(api.start).toHaveBeenCalledTimes(1);
      });
      fireEvent.click(screen.getByTestId("outcome-preview-close"));
      await waitFor(() => {
        expect(screen.queryByTestId("outcome-preview")).not.toBeInTheDocument();
      });
      await openPreview();
      await waitFor(() => {
        expect(api.start).toHaveBeenCalledTimes(2);
      });
    });

    it("выключенный документ кнопки не имеет, режим «Как студент» кнопки прячет", async () => {
      stubApi();
      const { unmount } = mount();
      await screen.findByTestId("outcome-doc-technical_specification-preview");
      expect(
        screen.queryByTestId("outcome-doc-operator_manual-preview"),
      ).not.toBeInTheDocument();
      unmount();
      mount("mode=student");
      // В виде студента карточек документов с действиями автора нет.
      await screen.findByTestId("outcome-student-documents");
      expect(
        screen.queryByTestId("outcome-doc-technical_specification-preview"),
      ).not.toBeInTheDocument();
    });

    it("результат из коммита: кнопка отключена с подсказкой", async () => {
      stubApi();
      mount("state=head");
      const button = await screen.findByTestId(
        "outcome-doc-technical_specification-preview",
      );
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute(
        "title",
        expect.stringContaining("Рабочее дерево"),
      );
    });

    it("кнопка открывает предпросмотр с клавиатуры (Enter)", async () => {
      const api = stubApi();
      mount();
      const button = await screen.findByTestId(
        "outcome-doc-technical_specification-preview",
      );
      await waitFor(() => {
        expect(button).toBeEnabled();
      });
      button.focus();
      await userEvent.keyboard("{Enter}");
      expect(await screen.findByTestId("outcome-preview")).toBeInTheDocument();
      await waitFor(() => {
        expect(api.start).toHaveBeenCalled();
      });
    });
  });

  describe("вариант, источник вводных, набор данных", () => {
    it("недоступный при языке вариант неактивен с подсказкой, при en доступен", async () => {
      stubApi();
      const { unmount } = mount();
      await openPreview();
      await userEvent.click(
        await screen.findByRole("combobox", { name: "Вариант документа" }),
      );
      const srs = await screen.findByRole("option", {
        name: /29148.*только en/,
      });
      expect(srs).toHaveAttribute("aria-disabled", "true");
      expect(screen.getByText(/язык проекта ru/)).toBeInTheDocument();
      await userEvent.keyboard("{Escape}");
      unmount();
      cleanup();
      resetPreviewMemory();
      mount("i.lang=en");
      await openPreview();
      await userEvent.click(
        await screen.findByRole("combobox", { name: "Вариант документа" }),
      );
      expect(
        await screen.findByRole("option", { name: /29148/ }),
      ).not.toHaveAttribute("aria-disabled", "true");
    });

    it("выбранный вариант уходит в сборку; вариант без PDF предупреждает", async () => {
      const api = stubApi();
      mount();
      await openPreview("presentation");
      await waitFor(() => {
        expect(api.start).toHaveBeenCalledTimes(1);
      });
      // Из вводных `variant.presentation`: pptx.
      expect(api.start.mock.calls[0]?.[2]).toMatchObject({
        documents: ["presentation"],
        variant: "pptx",
      });
      await choose("Вариант документа", /Reveal/i);
      expect(screen.getByTestId("outcome-preview-nopdf")).toBeInTheDocument();
      fireEvent.click(screen.getByTestId("outcome-preview-build"));
      await waitFor(() => {
        expect(api.start).toHaveBeenCalledTimes(2);
      });
      expect(api.start.mock.calls[1]?.[2]).toMatchObject({ variant: "reveal" });
    });

    it("источник «сценарий»: запрос с id сценария, без комбинации; в ответе сценарий и его вводные", async () => {
      const api = stubApi(
        build("with_variant_and_scenario", {
          id: QUEUED.id,
          document: "technical_specification",
          scenario: "company-supervisor",
          scenario_inputs: { supervisor: "company", co_supervisor: "yes" },
        }),
      );
      mount();
      await openPreview();
      await waitFor(() => {
        expect(api.start).toHaveBeenCalledTimes(1);
      });
      await choose("Вводные для сборки", /Научрук из компании/);
      fireEvent.click(screen.getByTestId("outcome-preview-build"));
      await waitFor(() => {
        expect(api.start).toHaveBeenCalledTimes(2);
      });
      expect(api.start.mock.calls[1]?.[2]).toEqual({
        documents: ["technical_specification"],
        scenario: "company-supervisor",
      });
      expect(
        await screen.findByTestId("outcome-preview-info-scenario"),
      ).toHaveTextContent("Научрук из компании, есть консультант");
      expect(
        screen.getByTestId("outcome-preview-info-inputs"),
      ).toHaveTextContent("supervisor: company");
    });

    it("набор данных меняется в панели и в адресе экрана", async () => {
      const api = stubApi();
      mount();
      await openPreview();
      await waitFor(() => {
        expect(api.start).toHaveBeenCalledTimes(1);
      });
      await userEvent.click(
        within(screen.getByTestId("outcome-preview")).getByRole("combobox", {
          name: "Набор данных",
        }),
      );
      await userEvent.click(
        await screen.findByRole("option", { name: "Длинные значения" }),
      );
      fireEvent.click(screen.getByTestId("outcome-preview-build"));
      await waitFor(() => {
        expect(api.start).toHaveBeenCalledTimes(2);
      });
      expect(api.start.mock.calls[1]?.[2]).toMatchObject({
        example: "auto:long",
      });
    });
  });

  describe("автосборка", () => {
    const controlKind = (value: string) =>
      screen.getByTestId(`outcome-control-kind-${value}`);

    it("выключена по умолчанию: смена вводных не собирает, а помечает PDF устаревшим", async () => {
      const api = stubApi();
      mount();
      expect(window.sessionStorage.getItem(AUTO_KEY)).toBeNull();
      await openPreview();
      await waitFor(() => {
        expect(api.start).toHaveBeenCalledTimes(1);
      });
      await screen.findByTestId("pdf-viewer");
      expect(screen.getByTestId("outcome-preview-auto")).toHaveAttribute(
        "aria-checked",
        "false",
      );
      fireEvent.click(controlKind("research"));
      // Вводные уходят в адрес по паузе, затем приходит новый результат: ждём дольше обычного.
      expect(
        await screen.findByTestId(
          "outcome-preview-stale",
          {},
          { timeout: 5000 },
        ),
      ).toHaveTextContent("Вводные, сценарий или вариант изменились");
      await new Promise((resolve) =>
        setTimeout(resolve, AUTO_DEBOUNCE_MS + 200),
      );
      expect(api.start).toHaveBeenCalledTimes(1);
      // Явная кнопка собирает с новыми вводными.
      fireEvent.click(screen.getByTestId("outcome-preview-build"));
      await waitFor(() => {
        expect(api.start).toHaveBeenCalledTimes(2);
      });
      expect(api.start.mock.calls[1]?.[2]).toMatchObject({
        combination: { kind: "research" },
      });
      await waitFor(() => {
        expect(
          screen.queryByTestId("outcome-preview-stale"),
        ).not.toBeInTheDocument();
      });
    });

    it("переключатель хранится в sessionStorage", async () => {
      stubApi();
      mount();
      await openPreview();
      fireEvent.click(await screen.findByTestId("outcome-preview-auto"));
      expect(window.sessionStorage.getItem(AUTO_KEY)).toBe("1");
      expect(screen.getByTestId("outcome-preview-auto")).toHaveAttribute(
        "aria-checked",
        "true",
      );
    });

    it("не падает без sessionStorage (частное окно)", async () => {
      stubApi();
      // eslint-disable-next-line @typescript-eslint/unbound-method
      const getItem = Storage.prototype.getItem;
      // eslint-disable-next-line @typescript-eslint/unbound-method
      const setItem = Storage.prototype.setItem;
      vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (
        this: Storage,
        key: string,
      ) {
        if (key === AUTO_KEY) throw new Error("denied");
        return getItem.call(this, key);
      });
      vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
        this: Storage,
        key: string,
        value: string,
      ) {
        if (key === AUTO_KEY) throw new Error("denied");
        setItem.call(this, key, value);
      });
      mount();
      await openPreview();
      fireEvent.click(await screen.findByTestId("outcome-preview-auto"));
      expect(screen.getByTestId("outcome-preview-auto")).toHaveAttribute(
        "aria-checked",
        "true",
      );
    });

    it("включена: правки вводных по паузе собирают один раз, без паузы не собирают", async () => {
      window.sessionStorage.setItem(AUTO_KEY, "1");
      const api = stubApi();
      mount();
      await openPreview();
      await waitFor(() => {
        expect(api.start).toHaveBeenCalledTimes(1);
      });
      await screen.findByTestId("pdf-viewer");
      fireEvent.click(controlKind("research"));
      fireEvent.click(screen.getByTestId("outcome-control-staffing-team2"));
      // Сразу после правки новой сборки ещё нет: пауза не прошла.
      expect(api.start).toHaveBeenCalledTimes(1);
      await waitFor(
        () => {
          expect(api.start).toHaveBeenCalledTimes(2);
        },
        { timeout: 4000 },
      );
      expect(api.start.mock.calls[1]?.[2]).toMatchObject({
        combination: { kind: "research", staffing: "team2" },
      });
      await new Promise((resolve) =>
        setTimeout(resolve, AUTO_DEBOUNCE_MS + 200),
      );
      expect(api.start).toHaveBeenCalledTimes(2);
    });

    it("возврат к собранному запросу не пересобирает", async () => {
      window.sessionStorage.setItem(AUTO_KEY, "1");
      const api = stubApi();
      mount();
      await openPreview();
      await waitFor(() => {
        expect(api.start).toHaveBeenCalledTimes(1);
      });
      fireEvent.click(controlKind("research"));
      fireEvent.click(controlKind("project"));
      await new Promise((resolve) =>
        setTimeout(resolve, AUTO_DEBOUNCE_MS + 300),
      );
      expect(api.start).toHaveBeenCalledTimes(1);
    });

    it("смена варианта и источника при автосборке собирает заново", async () => {
      window.sessionStorage.setItem(AUTO_KEY, "1");
      const api = stubApi();
      mount();
      await openPreview("presentation");
      await waitFor(() => {
        expect(api.start).toHaveBeenCalledTimes(1);
      });
      await choose("Вариант документа", /Beamer/i);
      await waitFor(
        () => {
          expect(api.start).toHaveBeenCalledTimes(2);
        },
        { timeout: 4000 },
      );
      expect(api.start.mock.calls[1]?.[2]).toMatchObject({ variant: "beamer" });
    });

    it("запись файла версии: без автосборки PDF помечается устаревшим", async () => {
      const api = stubApi();
      mount();
      await openPreview();
      await screen.findByTestId("pdf-viewer");
      act(() => {
        notifyPackFilesSaved(WS);
      });
      expect(
        await screen.findByTestId("outcome-preview-stale"),
      ).toHaveTextContent("Файлы менялись после сборки");
      expect(api.start).toHaveBeenCalledTimes(1);
    });

    it("запись файла версии при автосборке собирает заново", async () => {
      window.sessionStorage.setItem(AUTO_KEY, "1");
      const api = stubApi();
      mount();
      await openPreview();
      await screen.findByTestId("pdf-viewer");
      act(() => {
        notifyPackFilesSaved(WS);
      });
      await waitFor(
        () => {
          expect(api.start).toHaveBeenCalledTimes(2);
        },
        { timeout: 4000 },
      );
    });

    it("отмена не запускает сборку снова, пока запрос тот же", async () => {
      window.sessionStorage.setItem(AUTO_KEY, "1");
      const api = stubApi(build("running", { id: QUEUED.id }));
      mount();
      await openPreview();
      fireEvent.click(await screen.findByTestId("preview-cancel"));
      await waitFor(() => {
        expect(api.cancel).toHaveBeenCalledWith(WS, QUEUED.id);
      });
      await new Promise((resolve) =>
        setTimeout(resolve, AUTO_DEBOUNCE_MS + 200),
      );
      expect(api.start).toHaveBeenCalledTimes(1);
    });
  });

  describe("состояния сборки", () => {
    it("идёт сборка: статус и «Отменить», кнопка «Собрать» отключена", async () => {
      stubApi(build("running", { id: QUEUED.id }));
      mount();
      await openPreview();
      expect(await screen.findByTestId("preview-running")).toBeInTheDocument();
      expect(screen.getByTestId("outcome-preview-build")).toBeDisabled();
    });

    it("сборка из кэша помечена", async () => {
      stubApi(build("cached", { id: QUEUED.id }));
      mount();
      await openPreview();
      expect(
        await screen.findByTestId("outcome-preview-cached"),
      ).toBeInTheDocument();
      expect(screen.getByTestId("preview-pdf")).toHaveTextContent("из кэша");
    });

    it("неудачная сборка: код, причина и «Журнал»", async () => {
      stubApi(build("build_failed", { id: QUEUED.id }));
      vi.spyOn(packStudioApi, "previewLog").mockResolvedValue("! Undefined");
      mount();
      await openPreview();
      expect(await screen.findByTestId("preview-failed")).toHaveTextContent(
        "Undefined control sequence",
      );
      fireEvent.click(screen.getByTestId("preview-failed-log"));
      expect(await screen.findByTestId("preview-log")).toHaveTextContent(
        "! Undefined",
      );
    });

    it("preview_invalid: поле и значение из ответа", async () => {
      stubApi();
      vi.spyOn(packStudioApi, "startPreview").mockRejectedValue(
        new ApiError("bad", "preview_invalid", 400, {
          field: "variant",
          value: "srs-29148",
          reason: "not available for this language",
        }),
      );
      mount();
      await openPreview();
      expect(
        await screen.findByTestId("outcome-preview-start-error"),
      ).toHaveTextContent(
        "variant = srs-29148 (not available for this language)",
      );
    });

    it("scenario_not_found: перевод кода, кнопка «Собрать» остаётся", async () => {
      stubApi();
      vi.spyOn(packStudioApi, "startPreview").mockRejectedValue(
        new ApiError("no", "scenario_not_found", 404, { scenario: "gone" }),
      );
      mount();
      await openPreview();
      expect(
        await screen.findByTestId("outcome-preview-start-error"),
      ).toHaveTextContent("Сценарий не найден");
      expect(screen.getByTestId("outcome-preview-build")).toBeEnabled();
    });

    it("preview_quota: мягкое сообщение без обратного отсчёта при выключенной автосборке", async () => {
      stubApi();
      vi.spyOn(packStudioApi, "startPreview").mockRejectedValue(
        new ApiError("quota", "preview_quota", 429, { limit: 2 }),
      );
      mount();
      await openPreview();
      const note = await screen.findByTestId("outcome-preview-start-error");
      expect(note).toHaveTextContent("Одновременно идут 2 сборки");
      expect(
        screen.queryByTestId("outcome-preview-countdown"),
      ).not.toBeInTheDocument();
      expect(screen.getByTestId("outcome-preview-retry")).toBeEnabled();
    });

    it("preview_quota при автосборке: обратный отсчёт и «Собрать сейчас»", async () => {
      window.sessionStorage.setItem(AUTO_KEY, "1");
      const api = stubApi();
      api.start.mockRejectedValueOnce(
        new ApiError("quota", "preview_quota", 429, { limit: 2 }),
      );
      mount();
      await openPreview();
      expect(
        await screen.findByTestId("outcome-preview-countdown"),
      ).toHaveTextContent("Повторю через 10 с");
      fireEvent.click(screen.getByTestId("outcome-preview-retry"));
      await waitFor(() => {
        expect(api.start).toHaveBeenCalledTimes(2);
      });
      expect(
        screen.queryByTestId("outcome-preview-countdown"),
      ).not.toBeInTheDocument();
    });

    it("документа нет в опциях предпросмотра: сообщение без запросов сборки", async () => {
      const api = stubApi();
      vi.spyOn(packStudioApi, "previewOptions").mockResolvedValue({
        ...OPTIONS,
        documents: OPTIONS.documents.filter(
          (d) => d.id !== "technical_specification",
        ),
      });
      mount();
      await openPreview();
      expect(
        await screen.findByTestId("outcome-preview-no-document"),
      ).toBeInTheDocument();
      expect(api.start).not.toHaveBeenCalled();
    });

    it("опции не загрузились: ошибка с повтором", async () => {
      stubApi();
      vi.spyOn(packStudioApi, "previewOptions").mockRejectedValue(
        new ApiError("boom", "internal_error", 500),
      );
      mount();
      await openPreview();
      expect(
        await screen.findByTestId("outcome-preview-options-error"),
      ).toBeInTheDocument();
    });
  });

  describe("на эталонах без подмены клиента", () => {
    it("сборка проходит очередь и идёт до PDF через подмену API", async () => {
      mount();
      await openPreview();
      expect(await screen.findByTestId("preview-running")).toBeInTheDocument();
      expect(
        await screen.findByTestId("pdf-viewer", {}, { timeout: 8000 }),
      ).toHaveAttribute("data-url", expect.stringContaining("ref-build-1"));
      expect(screen.getByTestId("outcome-preview-info-file")).toHaveTextContent(
        "technical_specification-espd.pdf",
      );
    }, 15000);
  });

  describe("возврат из «Файлов»", () => {
    it("панель открыта снова без новой сборки; запись файла делает PDF устаревшим", async () => {
      const api = stubApi();
      const first = mount();
      await openPreview();
      await screen.findByTestId("pdf-viewer");
      first.unmount();
      cleanup();
      // Файл записали в «Файлах», пока экрана не было.
      act(() => {
        notifyPackFilesSaved(WS);
      });
      mount();
      expect(await screen.findByTestId("outcome-preview")).toBeInTheDocument();
      expect(await screen.findByTestId("pdf-viewer")).toBeInTheDocument();
      expect(api.start).toHaveBeenCalledTimes(1);
      expect(
        await screen.findByTestId("outcome-preview-stale"),
      ).toHaveTextContent("Файлы менялись после сборки");
    });
  });

  describe("языки", () => {
    it("английский словарь: кнопка, панель, статусы", async () => {
      await i18n.changeLanguage("en");
      stubApi();
      mount();
      const button = await screen.findByTestId(
        "outcome-doc-technical_specification-preview",
      );
      expect(button).toHaveTextContent("PDF preview");
      await waitFor(() => {
        expect(button).toBeEnabled();
      });
      fireEvent.click(button);
      const panel = await screen.findByTestId("outcome-preview");
      expect(panel).toHaveTextContent("Built on test data, nothing is sent");
      expect(
        screen.getByRole("combobox", { name: "Inputs for the build" }),
      ).toBeInTheDocument();
      expect(screen.getByTestId("outcome-preview-build")).toHaveTextContent(
        /Build|Rebuild/,
      );
      expect(
        await screen.findByTestId("outcome-preview-info"),
      ).toHaveTextContent("File name");
    });
  });

  describe("телефон 360 px", () => {
    let viewport: ReturnType<typeof installViewport>;
    beforeEach(() => {
      viewport = installViewport(360);
    });
    afterEach(() => {
      viewport.restore();
    });

    it("предпросмотр открывается нижним листом, а не боковой панелью", async () => {
      const api = stubApi();
      mount();
      await openPreview();
      const sheet = await screen.findByRole("dialog");
      expect(sheet).toHaveAttribute("data-form", "sheet");
      expect(sheet).toHaveTextContent("Предпросмотр PDF:");
      expect(
        screen.queryByTestId("outcome-preview-drawer"),
      ).not.toBeInTheDocument();
      await waitFor(() => {
        expect(api.start).toHaveBeenCalledTimes(1);
      });
      fireEvent.keyDown(sheet, { key: "Escape" });
      await waitFor(() => {
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      });
    });

    it("на телефоне панель не открывается сама после возврата", async () => {
      stubApi();
      const first = mount();
      await openPreview();
      first.unmount();
      cleanup();
      mount();
      await screen.findByTestId("outcome-doc-technical_specification-preview");
      expect(screen.queryByTestId("outcome-preview")).not.toBeInTheDocument();
    });
  });

  describe("обратный отсчёт квоты", () => {
    it("через десять секунд повторяет запуск один раз", () => {
      vi.useFakeTimers();
      try {
        const done = vi.fn();
        render(<QuotaCountdown onDone={done} />);
        expect(
          screen.getByTestId("outcome-preview-countdown"),
        ).toHaveTextContent("Повторю через 10 с");
        act(() => {
          vi.advanceTimersByTime(9000);
        });
        expect(done).not.toHaveBeenCalled();
        act(() => {
          vi.advanceTimersByTime(3000);
        });
        expect(done).toHaveBeenCalledTimes(1);
      } finally {
        vi.useRealTimers();
      }
    });
  });
});
