import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import {
  packStudioKeys,
  type PackTree,
  type PackVersionRef,
  type PackWorkspace,
} from "@entities/pack-studio";
import {
  installOutcomeReference,
  outcomeReference,
} from "@entities/pack-studio/reference";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { installViewport } from "@shared/lib/viewport/testing";
import { OutcomeBody } from "../../OutcomeBody";

// Телефон экрана «Результат» (срез F14): две строки сверху, лист «Параметры», нижние вкладки,
// «Назад» браузера. Раскладку включает ширина окна (installViewport), jsdom без вёрстки.

const WS = "ws-phone";
const REF: PackVersionRef = {
  pack: "hse-cs-se",
  template: "vkr",
  version: "2026.1.2",
};
const NOW = "2026-11-17T09:30:00Z";

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
              version: "2026.1.1",
              path: "hse-cs-se/templates/vkr/versions/2026.1.1",
              status: "stable",
              released: true,
              modified: false,
            },
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

const Probe = () => {
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <output data-testid="location">{`${pathname}${search}`}</output>
      <button
        type="button"
        data-testid="browser-back"
        onClick={() => {
          void navigate(-1);
        }}
      />
    </>
  );
};

const PATH = `/pack-studio/w/${WS}/result/${REF.pack}/${REF.template}/${REF.version}`;

/** `before` это запись истории под экраном: «Назад» с экрана должен вести на неё. */
const mount = (search = "") => {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: Infinity,
        staleTime: Infinity,
        retryDelay: 0,
      },
    },
  });
  client.setQueryData(packStudioKeys.tree(WS), tree);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={["/before", `${PATH}${search ? `?${search}` : ""}`]}
        initialIndex={1}
      >
        <OutcomeBody workspace={workspace} version={REF} />
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

const location = () => screen.getByTestId("location").textContent;
const back = () => {
  fireEvent.click(screen.getByTestId("browser-back"));
};

describe("телефон экрана «Результат»", () => {
  let viewport: ReturnType<typeof installViewport>;
  beforeAll(async () => {
    installOutcomeReference();
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
  });
  beforeEach(async () => {
    window.localStorage.clear();
    outcomeReference.setSource("reference");
    await i18n.changeLanguage("ru");
    viewport = installViewport(360);
  });
  afterEach(() => {
    cleanup();
    viewport.restore();
    outcomeReference.setBehavior("normal");
    window.localStorage.clear();
  });

  describe("верхняя панель", () => {
    it("две строки: название с «Параметры» и сценарий, остальное в листе", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      const bar = screen.getByTestId("outcome-phone-bar");
      expect(within(bar).getByTestId("outcome-phone-title")).toHaveTextContent(
        "ВКР бакалавра",
      );
      expect(within(bar).getByTestId("outcome-phone-title")).toHaveTextContent(
        "2026.1.2",
      );
      expect(within(bar).getByTestId("scenario-trigger")).toBeInTheDocument();
      // Пак, версия, режим, «Результат из», «Файлы» в панели не рисуются.
      expect(within(bar).queryByTestId("outcome-mode-author")).toBeNull();
      expect(screen.queryByTestId("outcome-files-open")).toBeNull();
      expect(screen.queryByTestId("outcome-released")).toBeNull();
      expect(screen.queryByTestId("outcome-footer")).toBeInTheDocument();
    });

    it("«Параметры» открывают лист: шаблон, версия, режим, «Результат из», «Файлы»", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      const open = screen.getByTestId("outcome-options-open");
      expect(open).toHaveAttribute("aria-haspopup", "dialog");
      fireEvent.click(open);
      const sheet = await screen.findByRole("dialog", { name: "Параметры" });
      expect(sheet).toHaveAttribute("data-form", "sheet");
      expect(sheet).toHaveClass("po-sheet");
      const options = within(sheet).getByTestId("outcome-options");
      expect(
        within(options).getByRole("combobox", { name: "Шаблон" }),
      ).toBeInTheDocument();
      expect(
        within(options).getByRole("combobox", { name: "Версия" }),
      ).toBeInTheDocument();
      expect(within(options).getByTestId("outcome-mode-author")).toBeVisible();
      expect(
        within(options).getByRole("combobox", { name: "Результат из" }),
      ).toBeInTheDocument();
      expect(within(options).getByTestId("outcome-files-open")).toBeVisible();
      expect(within(options).getByTestId("outcome-files-mode")).toBeVisible();
      // Выпущенной версии здесь нет, у беты плашки нет.
      expect(within(options).queryByTestId("outcome-released")).toBeNull();
    });

    it("фокус уходит в лист, Esc закрывает его и «Назад» не остаётся мёртвой записью", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      fireEvent.click(screen.getByTestId("outcome-options-open"));
      const sheet = await screen.findByRole("dialog");
      await waitFor(() => {
        expect(sheet.contains(document.activeElement)).toBe(true);
      });
      fireEvent.keyDown(sheet, { key: "Escape" });
      await waitFor(() => {
        expect(screen.queryByRole("dialog")).toBeNull();
      });
      // Лист добавил запись и снял её: следующий «Назад» уходит с экрана.
      await waitFor(() => {
        expect(location()).toBe(PATH);
      });
      back();
      await waitFor(() => {
        expect(location()).toBe("/before");
      });
    });

    it("«Назад» браузера закрывает лист, экран остаётся", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      fireEvent.click(screen.getByTestId("outcome-options-open"));
      await screen.findByRole("dialog");
      back();
      await waitFor(() => {
        expect(screen.queryByRole("dialog")).toBeNull();
      });
      expect(location()).toBe(PATH);
      expect(screen.getByTestId("outcome-screen")).toBeInTheDocument();
    });

    it("режим «Как студент» виден меткой в панели", async () => {
      mount("mode=student");
      await screen.findByTestId("outcome-student");
      expect(screen.getByTestId("outcome-phone-student")).toHaveTextContent(
        "Как студент",
      );
      expect(screen.getByTestId("outcome-options-dot")).toBeInTheDocument();
    });

    it("«Файлы» из листа открывают панель файлов нижним листом", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      fireEvent.click(screen.getByTestId("outcome-options-open"));
      fireEvent.click(await screen.findByTestId("outcome-files-open"));
      expect(await screen.findByTestId("outcome-files-drawer")).toBeVisible();
    });
  });

  describe("вкладки", () => {
    it("три вкладки с подписями, «Результат» текущая", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      const nav = screen.getByRole("navigation", { name: "Разделы экрана" });
      expect(
        within(nav)
          .getAllByRole("button")
          .map((b) => b.textContent),
      ).toEqual(["Вводные", "Результат", "Почему?"]);
      expect(screen.getByTestId("outcome-tab-result")).toHaveAttribute(
        "aria-current",
        "page",
      );
    });

    it("счётчик вводных и метка выбранного элемента", async () => {
      mount(
        "i.kind=research&i.meta.nda=yes&selected=documents:operator_manual",
      );
      await screen.findByTestId("outcome-count-documents");
      expect(screen.getByTestId("outcome-tab-inputs-badge")).toHaveTextContent(
        "2",
      );
      expect(screen.getByTestId("outcome-tab-inputs")).toHaveAccessibleName(
        "Вводные, изменено 2 вводные",
      );
      expect(screen.getByTestId("outcome-tab-rules")).toHaveAccessibleName(
        "Почему?, выбран элемент",
      );
      expect(screen.getByTestId("outcome-tab-rules-badge")).toBeInTheDocument();
    });

    it("без изменений и выбора счётчиков нет", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      expect(screen.queryByTestId("outcome-tab-inputs-badge")).toBeNull();
      expect(screen.queryByTestId("outcome-tab-rules-badge")).toBeNull();
    });

    it("«Почему?» это страница: вкладка в адресе, фокус и объявление, «Назад» возвращает результат", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      fireEvent.click(screen.getByTestId("outcome-tab-rules"));
      expect(location()).toContain("tab=rules");
      const page = await screen.findByTestId("outcome-rules-page");
      expect(screen.queryByTestId("outcome-center")).toBeNull();
      expect(screen.getByTestId("outcome-tab-rules")).toHaveAttribute(
        "aria-current",
        "page",
      );
      await waitFor(() => {
        expect(document.activeElement).toBe(page);
      });
      expect(screen.getByTestId("outcome-live")).toHaveTextContent(
        "Открыта вкладка «Почему?»",
      );
      back();
      await screen.findByTestId("outcome-center");
      expect(location()).toBe(PATH);
      expect(screen.getByTestId("outcome-live")).toHaveTextContent(
        "Открыта вкладка «Результат»",
      );
    });

    it("вкладка «Результат» с «Почему?» не добавляет записи и сохраняет выбор", async () => {
      mount("tab=rules&selected=documents:operator_manual");
      await screen.findByTestId("outcome-rules-page");
      fireEvent.click(screen.getByTestId("outcome-tab-result"));
      await screen.findByTestId("outcome-center");
      expect(location()).toContain("selected=documents%3Aoperator_manual");
      expect(location()).not.toContain("tab=");
    });

    it("выбор элемента открывает «Почему?», «Назад» возвращает результат без выбора", async () => {
      mount();
      const card = await screen.findByTestId("outcome-doc-thesis");
      const [pick] = within(card).getAllByRole("button");
      if (!pick) throw new Error("the pick button is missing");
      fireEvent.click(pick);
      await screen.findByTestId("outcome-rules-page");
      expect(location()).toContain("tab=rules");
      back();
      await screen.findByTestId("outcome-center");
      expect(location()).toBe(PATH);
    });

    it("в режиме «Как студент» две вкладки, tab=rules из адреса открывает результат", async () => {
      mount("mode=student&tab=rules");
      await screen.findByTestId("outcome-student");
      expect(screen.queryByTestId("outcome-tab-rules")).toBeNull();
      expect(screen.queryByTestId("outcome-rules-page")).toBeNull();
      expect(screen.getByTestId("outcome-tab-result")).toHaveAttribute(
        "aria-current",
        "page",
      );
    });

    it("Alt+Z переключает «Почему?» и результат", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      fireEvent.keyDown(screen.getByTestId("outcome-screen"), {
        key: "z",
        code: "KeyZ",
        altKey: true,
      });
      await screen.findByTestId("outcome-rules-page");
      fireEvent.keyDown(screen.getByTestId("outcome-screen"), {
        key: "z",
        code: "KeyZ",
        altKey: true,
      });
      await screen.findByTestId("outcome-center");
    });
  });

  describe("лист «Вводные»", () => {
    it("открывается вкладкой и закрывается: без изменений запись снимается", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      fireEvent.click(screen.getByTestId("outcome-tab-inputs"));
      expect(location()).toContain("tab=inputs");
      const sheet = await screen.findByRole("dialog", { name: "Вводные" });
      expect(sheet).toHaveClass("po-sheet");
      expect(within(sheet).getByTestId("outcome-inputs")).toBeInTheDocument();
      expect(screen.getByTestId("outcome-tab-inputs")).toHaveAttribute(
        "aria-expanded",
        "true",
      );
      await waitFor(() => {
        expect(sheet.contains(document.activeElement)).toBe(true);
      });
      fireEvent.keyDown(sheet, { key: "Escape" });
      await waitFor(() => {
        expect(screen.queryByRole("dialog")).toBeNull();
      });
      await waitFor(() => {
        expect(location()).toBe(PATH);
      });
      back();
      await waitFor(() => {
        expect(location()).toBe("/before");
      });
    });

    it("«Назад» браузера закрывает лист и возвращает вкладку под ним", async () => {
      mount("tab=rules&selected=documents:operator_manual");
      await screen.findByTestId("outcome-rules-page");
      fireEvent.click(screen.getByTestId("outcome-tab-inputs"));
      await screen.findByRole("dialog", { name: "Вводные" });
      // Под листом остаётся «Почему?», а не результат.
      expect(screen.getByTestId("outcome-rules-page")).toBeInTheDocument();
      back();
      await waitFor(() => {
        expect(screen.queryByRole("dialog")).toBeNull();
      });
      expect(location()).toContain("tab=rules");
      expect(screen.getByTestId("outcome-rules-page")).toBeInTheDocument();
    });

    it("«Показать» применяет вводные и закрывает лист, выбор не пропадает", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      fireEvent.click(screen.getByTestId("outcome-tab-inputs"));
      const sheet = await screen.findByRole("dialog");
      fireEvent.click(
        await within(sheet).findByRole("radio", { name: "Исследовательская" }),
      );
      // До «Показать» адрес не меняется.
      expect(location()).not.toContain("i.kind");
      fireEvent.click(within(sheet).getByTestId("outcome-inputs-apply"));
      await waitFor(() => {
        expect(screen.queryByRole("dialog")).toBeNull();
      });
      expect(location()).toContain("i.kind=research");
      expect(location()).not.toContain("tab=");
      expect(screen.getByTestId("outcome-tab-inputs-badge")).toHaveTextContent(
        "1",
      );
    });
  });

  describe("нет наведения", () => {
    it("причина отключённого предпросмотра написана рядом, а не в title", async () => {
      mount("state=head");
      await screen.findByTestId("outcome-count-documents");
      const why = await screen.findAllByTestId(/-preview-why$/);
      expect(why[0]).toHaveTextContent(/рабочего дерева|рабочее дерево/i);
    });
  });

  describe("«К документу»", () => {
    it("открывает «Почему?» и тогда, когда документ уже выбран", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      // Точки сдачи: раскрыть секцию, если она свёрнута.
      const link = await screen.findAllByTestId(/^outcome-doc-link-/);
      const first = link[0];
      if (!first) throw new Error("no document link");
      fireEvent.click(first);
      await screen.findByTestId("outcome-rules-page");
      // Вернулись на результат вкладкой: выбор остался.
      fireEvent.click(screen.getByTestId("outcome-tab-result"));
      await screen.findByTestId("outcome-center");
      expect(location()).toContain("selected=documents");
      const again = (await screen.findAllByTestId(/^outcome-doc-link-/))[0];
      if (!again) throw new Error("no document link");
      fireEvent.click(again);
      await screen.findByTestId("outcome-rules-page");
      expect(location()).toContain("tab=rules");
    });
  });

  describe("английский", () => {
    it("подписи вкладок, листа и объявления на английском", async () => {
      await i18n.changeLanguage("en");
      try {
        mount("i.kind=research");
        await screen.findByTestId("outcome-count-documents");
        const nav = screen.getByRole("navigation", { name: "Screen sections" });
        expect(
          within(nav)
            .getAllByRole("button")
            .map((b) => b.textContent),
        ).toEqual(["Inputs1", "Outcome", "Why?"]);
        expect(screen.getByTestId("outcome-tab-inputs")).toHaveAccessibleName(
          "Inputs, 1 input changed",
        );
        expect(screen.getByTestId("outcome-options-open")).toHaveTextContent(
          "Options",
        );
        fireEvent.click(screen.getByTestId("outcome-tab-rules"));
        await screen.findByTestId("outcome-rules-page");
        expect(screen.getByTestId("outcome-live")).toHaveTextContent(
          "The Why? tab is open.",
        );
      } finally {
        await i18n.changeLanguage("ru");
      }
    });
  });
});
