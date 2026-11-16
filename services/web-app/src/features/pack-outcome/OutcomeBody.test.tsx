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
import { MemoryRouter, useLocation } from "react-router";
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
import { OutcomeBody } from "./OutcomeBody";

// Экран «Результат» на эталонах контракта: подмена API отвечает вместо сервера, адрес хранит
// состояние, каркас показывает сводку из ответа. Эндпоинтов результата ещё нет, этот тест
// проходит ту же цепочку (адрес, запрос, отрисовка), что пройдёт с настоящим сервером.

const WS = "ws-outcome";
const REF: PackVersionRef = {
  pack: "hse-cs-se",
  template: "vkr",
  version: "2026.1.2",
};
const NOW = "2026-11-16T09:30:00Z";

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
  return <output data-testid="location">{`${pathname}${search}`}</output>;
};

const mount = (search = "", version: PackVersionRef = REF) => {
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
  const path = `/pack-studio/w/${WS}/result/${version.pack}/${version.template}/${version.version}`;
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`${path}${search ? `?${search}` : ""}`]}>
        <OutcomeBody workspace={workspace} version={version} />
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
};

const location = () => screen.getByTestId("location").textContent;

describe("экран «Результат»: каркас на эталонах", () => {
  beforeAll(async () => {
    installOutcomeReference();
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    window.localStorage.clear();
    // По умолчанию запросы идут настоящему серверу; экран проверяется на эталонах.
    outcomeReference.setSource("reference");
  });
  afterEach(() => {
    cleanup();
    outcomeReference.setSource("reference");
    outcomeReference.setBehavior("normal");
    window.localStorage.clear();
  });

  describe("данные из ответа", () => {
    it("сводка и счётчики секций берутся из эталона", async () => {
      mount();
      expect(
        await screen.findByText("В комплекте 12 документов, 2 подписанта"),
      ).toBeVisible();
      expect(screen.getByTestId("outcome-count-documents")).toHaveTextContent(
        "12 из 18 в комплекте",
      );
      expect(
        screen.getByTestId("outcome-count-participants"),
      ).toHaveTextContent("3 из 4");
      expect(screen.getByTestId("outcome-count-points")).toHaveTextContent("6");
      // Проверки и ветки по запросу: сервер их не считал, экран так и пишет.
      expect(screen.getByTestId("outcome-count-checks")).toHaveTextContent(
        "Загружается при раскрытии",
      );
    });

    it("первая загрузка показывает скелет, не пустое место", () => {
      mount();
      expect(
        screen.getByTestId("outcome-section-documents"),
      ).toBeInTheDocument();
      expect(screen.getByTestId("outcome-inputs-loading")).toBeInTheDocument();
      expect(
        screen.queryByTestId("outcome-count-documents"),
      ).not.toBeInTheDocument();
    });

    it("границы расчёта и «ничего не отправляется» написаны на экране", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      expect(screen.getByTestId("outcome-footer")).toHaveTextContent(
        "Расчёт на тестовых данных, ничего не отправляется.",
      );
      expect(screen.getByTestId("outcome-out-of-scope")).toHaveTextContent(
        "проверки на Python",
      );
    });

    it("aria-live объявляет итог результата", async () => {
      mount();
      await waitFor(() => {
        expect(screen.getByTestId("outcome-live")).toHaveTextContent(
          "Документов в комплекте 12 из 18, подписантов 2",
        );
      });
      expect(screen.getByTestId("outcome-live")).toHaveAttribute(
        "aria-live",
        "polite",
      );
    });
  });

  describe("состояние в адресе", () => {
    it("адрес восстанавливает вводные, выбор и режим", async () => {
      mount("i.kind=research&selected=documents:operator_manual");
      const row = await screen.findByTestId("outcome-input-kind");
      expect(row).toHaveAttribute("data-changed", "true");
      expect(within(row).getByText("research")).toBeInTheDocument();
      expect(screen.getByTestId("outcome-selected")).toHaveTextContent(
        "operator_manual",
      );
      expect(screen.getByTestId("outcome-mode-author")).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    });

    it("режим «Как студент» из адреса прячет правила", async () => {
      mount("mode=student&selected=documents:report");
      await screen.findByTestId("outcome-count-documents");
      expect(screen.getByTestId("outcome-mode-student")).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      expect(
        screen.queryByTestId("outcome-rules-panel"),
      ).not.toBeInTheDocument();
      expect(screen.getByTestId("outcome-screen")).toHaveAttribute(
        "data-mode",
        "student",
      );
    });

    it("переключение режима пишет его в адрес и обратно убирает", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      fireEvent.click(screen.getByTestId("outcome-mode-student"));
      expect(location()).toContain("mode=student");
      expect(
        screen.queryByTestId("outcome-rules-panel"),
      ).not.toBeInTheDocument();
      fireEvent.click(screen.getByTestId("outcome-mode-author"));
      expect(location()).not.toContain("mode");
      expect(screen.getByTestId("outcome-rules-panel")).toBeInTheDocument();
    });

    it("«Сбросить» возвращает вводные к умолчаниям и чистит адрес", async () => {
      mount("i.kind=research&i.staffing=team2&state=head");
      const reset = await screen.findByTestId("outcome-inputs-reset");
      fireEvent.click(reset);
      expect(location()).toBe(
        `/pack-studio/w/${WS}/result/hse-cs-se/vkr/2026.1.2?state=head`,
      );
      expect(
        screen.queryByTestId("outcome-inputs-reset"),
      ).not.toBeInTheDocument();
    });

    it("«Снять выбор» убирает выбранный элемент из адреса", async () => {
      mount("selected=route:final/step/1");
      fireEvent.click(await screen.findByTestId("outcome-selected-clear"));
      expect(location()).not.toContain("selected");
      expect(screen.getByTestId("outcome-rules-empty")).toBeInTheDocument();
    });

    it("вводные уходят в запрос поверх эталона", async () => {
      mount("i.staffing=team2");
      await screen.findByTestId("outcome-count-documents");
      // Запрос с вводными тот же, что у хука: ответ эталона несёт их в `inputs`.
      const input = await screen.findByTestId("outcome-input-staffing");
      expect(within(input).getByText("team2")).toBeInTheDocument();
    });
  });

  describe("панели", () => {
    it("три области с подписями", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      expect(
        screen.getByRole("region", { name: "Вводные" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("region", { name: "Результат" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("region", { name: "Правила и причины" }),
      ).toBeInTheDocument();
    });

    it("левая панель сворачивается в рейку со счётчиком изменённых вводных и запоминается", async () => {
      mount("i.kind=research&i.staffing=team2");
      await screen.findByTestId("outcome-inputs-panel");
      fireEvent.click(screen.getByTestId("outcome-inputs-panel-collapse"));
      expect(
        screen.queryByTestId("outcome-inputs-panel"),
      ).not.toBeInTheDocument();
      expect(screen.getByTestId("outcome-inputs-badge")).toHaveTextContent("2");
      expect(
        window.localStorage.getItem("hse-studio.packOutcome.left.off"),
      ).toBe("1");
      fireEvent.click(screen.getByTestId("outcome-inputs-expand"));
      expect(screen.getByTestId("outcome-inputs-panel")).toBeInTheDocument();
      expect(
        window.localStorage.getItem("hse-studio.packOutcome.left.off"),
      ).toBe("0");
    });

    it("правая панель сворачивается, у выбранного элемента остаётся «Почему?»", async () => {
      mount("selected=documents:report");
      await screen.findByTestId("outcome-rules-panel");
      fireEvent.click(screen.getByTestId("outcome-rules-panel-collapse"));
      expect(
        screen.queryByTestId("outcome-rules-panel"),
      ).not.toBeInTheDocument();
      fireEvent.click(screen.getByTestId("outcome-rail-why"));
      expect(screen.getByTestId("outcome-rules-panel")).toBeInTheDocument();
    });

    it("ширина меняется кнопками и стрелками, пределы держатся", async () => {
      mount();
      await screen.findByTestId("outcome-inputs-panel");
      const splitter = screen.getByTestId("outcome-inputs-splitter");
      expect(splitter).toHaveAttribute("role", "separator");
      expect(splitter).toHaveAttribute("aria-valuenow", "296");
      fireEvent.click(screen.getByTestId("outcome-inputs-panel-wider"));
      expect(splitter).toHaveAttribute("aria-valuenow", "328");
      fireEvent.keyDown(splitter, { key: "ArrowLeft" });
      expect(splitter).toHaveAttribute("aria-valuenow", "312");
      fireEvent.keyDown(splitter, { key: "End" });
      expect(splitter).toHaveAttribute("aria-valuenow", "440");
      fireEvent.keyDown(splitter, { key: "Home" });
      expect(splitter).toHaveAttribute("aria-valuenow", "232");
      fireEvent.click(screen.getByTestId("outcome-inputs-panel-narrower"));
      expect(splitter).toHaveAttribute("aria-valuenow", "232");
    });

    it("у правой панели «шире» двигает границу влево", async () => {
      mount();
      await screen.findByTestId("outcome-rules-panel");
      const splitter = screen.getByTestId("outcome-rules-splitter");
      expect(splitter).toHaveAttribute("aria-valuenow", "344");
      fireEvent.click(screen.getByTestId("outcome-rules-panel-wider"));
      expect(splitter).toHaveAttribute("aria-valuenow", "376");
      fireEvent.keyDown(splitter, { key: "ArrowRight" });
      expect(splitter).toHaveAttribute("aria-valuenow", "360");
    });

    it("F6 и Shift+F6 переводят фокус между областями, Alt+Z прячет правила", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      const screenEl = screen.getByTestId("outcome-screen");
      const inputs = screen.getByTestId("outcome-inputs-panel");
      const result = screen.getByTestId("outcome-center");
      const rules = screen.getByTestId("outcome-rules-panel");
      inputs.focus();
      fireEvent.keyDown(inputs, { key: "F6" });
      expect(result).toHaveFocus();
      fireEvent.keyDown(result, { key: "F6" });
      expect(rules).toHaveFocus();
      fireEvent.keyDown(rules, { key: "F6", shiftKey: true });
      expect(result).toHaveFocus();
      fireEvent.keyDown(screenEl, { key: "z", code: "KeyZ", altKey: true });
      expect(
        screen.queryByTestId("outcome-rules-panel"),
      ).not.toBeInTheDocument();
    });

    it("секция сворачивается и помнит это", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      const toggle = within(
        screen.getByTestId("outcome-section-meta"),
      ).getByRole("button", {
        expanded: true,
      });
      fireEvent.click(toggle);
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(
        window.localStorage.getItem("hse-studio.packOutcome.section.meta"),
      ).toBe("1");
    });

    it("«Файлы» открывает выдвижную панель с деревом", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      fireEvent.click(screen.getByTestId("outcome-files-open"));
      const drawer = await screen.findByTestId("outcome-files-drawer");
      expect(drawer).toHaveTextContent("Файлы");
      expect(screen.getByTestId("outcome-files-mode")).toHaveAttribute(
        "href",
        `/pack-studio/w/${WS}?view=files`,
      );
    });
  });

  describe("версия и верхняя панель", () => {
    it("выпущенная версия: замок и плашка про запрет правки", async () => {
      mount("", { ...REF, version: "2026.1.1" });
      await screen.findByTestId("outcome-count-documents");
      expect(screen.getByTestId("outcome-released-mark")).toBeInTheDocument();
      expect(screen.getByTestId("outcome-released")).toHaveTextContent(
        "править нельзя",
      );
    });

    it("черновик без замка", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      expect(screen.queryByTestId("outcome-released")).not.toBeInTheDocument();
    });

    it("версии нет в дереве: понятное состояние со ссылкой на файлы", () => {
      mount("", { ...REF, version: "1999.1" });
      expect(screen.getByTestId("outcome-version-missing")).toHaveTextContent(
        "1999.1",
      );
    });

    it("состояние расчёта: сохранено, затем пересчёт", async () => {
      mount();
      const status = screen.getByTestId("outcome-status");
      expect(status).toHaveAttribute("role", "status");
      expect(status).toHaveTextContent("Пересчитываю");
      await waitFor(() => {
        expect(status).toHaveTextContent("Сохранено");
      });
    });

    it("«Результат из» и сценарий лежат в панели", async () => {
      mount("state=base");
      await screen.findByTestId("outcome-count-documents");
      expect(
        screen.getByRole("combobox", { name: "Результат из" }),
      ).toHaveTextContent("База");
      expect(
        screen.getByRole("combobox", { name: "Сценарий" }),
      ).toHaveTextContent("Без сценария");
    });
  });

  describe("ошибки и пустые состояния", () => {
    it("версия не читается: причина от лоадера, исходник, повтор", async () => {
      outcomeReference.setBehavior("unreadable");
      mount();
      const error = await screen.findByTestId("outcome-error");
      expect(error).toHaveAttribute("role", "alert");
      expect(error).toHaveTextContent("suported_kinds");
      expect(screen.getByTestId("outcome-open-source")).toHaveTextContent(
        "Открыть исходник",
      );
      expect(
        screen.getByTestId("outcome-open-source").getAttribute("href"),
      ).toContain("version.yaml");
      expect(screen.getByTestId("outcome-status")).toHaveTextContent(
        "Не удалось пересчитать",
      );
      // Повтор после починки: результат появляется.
      outcomeReference.setBehavior("normal");
      fireEvent.click(screen.getByTestId("outcome-retry"));
      expect(
        await screen.findByTestId("outcome-count-documents"),
      ).toBeInTheDocument();
      expect(screen.queryByTestId("outcome-error")).not.toBeInTheDocument();
    });

    it("сбой сервера: баннер вместо секций", async () => {
      outcomeReference.setBehavior("error");
      mount();
      expect(await screen.findByTestId("outcome-error")).toBeInTheDocument();
      expect(screen.queryByTestId("outcome-sections")).not.toBeInTheDocument();
      expect(screen.getByTestId("outcome-open-source")).toHaveTextContent(
        "Открыть файлы",
      );
    });

    it("сбой на другом состоянии даёт вернуться к рабочему дереву", async () => {
      outcomeReference.setBehavior("error");
      mount("state=base");
      await screen.findByTestId("outcome-error");
      fireEvent.click(screen.getByTestId("outcome-to-work-tree"));
      expect(location()).not.toContain("state=");
    });

    it("после неудачного пересчёта остаётся прежний результат серым", async () => {
      const client = mount();
      await screen.findByTestId("outcome-count-documents");
      outcomeReference.setBehavior("error");
      await act(async () => {
        await client.refetchQueries({
          queryKey: ["pack-studio", "workspaces", WS, "outcome"],
          predicate: (q) => q.queryKey.includes("result"),
        });
      });
      expect(
        await screen.findByTestId("outcome-error-stale"),
      ).toHaveTextContent("прежний результат");
      expect(screen.getByTestId("outcome-count-documents")).toBeInTheDocument();
    });

    it("в версии нет документов: подсказка вместо секций", async () => {
      outcomeReference.setBehavior("empty");
      mount();
      const empty = await screen.findByTestId("outcome-empty");
      expect(empty).toHaveTextContent("В версии нет документов");
      expect(
        screen.getByTestId("outcome-empty-action").getAttribute("href"),
      ).toContain("version.yaml");
    });

    it("нет влияющих вводных", async () => {
      outcomeReference.setBehavior("no_inputs");
      mount();
      expect(
        await screen.findByTestId("outcome-inputs-empty"),
      ).toHaveTextContent("Результат не зависит от вводных");
    });

    it("вводные не загрузились: ошибка только в левой панели", async () => {
      outcomeReference.setBehavior("error");
      mount();
      expect(
        await screen.findByTestId("outcome-inputs-error"),
      ).toBeInTheDocument();
    });
  });

  describe("секции F3 на экране", () => {
    it("документы, поля и участники приходят из ответа эталона", async () => {
      mount();
      expect(await screen.findByTestId("outcome-doc-thesis")).toHaveTextContent(
        "Выпускная квалификационная работа.pdf",
      );
      expect(screen.getByTestId("outcome-meta-year")).toHaveTextContent(
        "При создании",
      );
      expect(
        screen.getByTestId("outcome-participant-supervisor"),
      ).toHaveTextContent("Петров Пётр Петрович");
    });

    it("клик по документу пишет selected в адрес и открывает правую панель", async () => {
      mount();
      const card = await screen.findByTestId("outcome-doc-operator_manual");
      fireEvent.click(within(card).getByRole("button"));
      expect(location()).toContain("selected=documents%3Aoperator_manual");
      expect(screen.getByTestId("outcome-selected")).toHaveTextContent(
        "operator_manual",
      );
      fireEvent.click(within(card).getByRole("button"));
      expect(location()).not.toContain("selected");
    });

    it("выбор из адреса подсвечивает карточку", async () => {
      mount("selected=participants:supervisor");
      const card = await screen.findByTestId("outcome-participant-supervisor");
      expect(within(card).getByRole("button")).toHaveAttribute(
        "aria-current",
        "true",
      );
    });

    it("английский интерфейс: подписи и тексты секций", async () => {
      await i18n.changeLanguage("en");
      try {
        mount();
        const card = await screen.findByTestId("outcome-doc-operator_manual");
        expect(card).toHaveTextContent("Switched off");
        expect(screen.getByTestId("outcome-meta-year")).toHaveTextContent(
          "At creation",
        );
      } finally {
        await i18n.changeLanguage("ru");
      }
    });

    it("пустой результат: секции не рисуются, остаётся пояснение", async () => {
      outcomeReference.setBehavior("empty");
      mount();
      expect(await screen.findByTestId("outcome-empty")).toBeInTheDocument();
      expect(screen.queryByTestId("outcome-documents")).not.toBeInTheDocument();
    });

    it("ошибка расчёта: карточек нет, плашка с повтором", async () => {
      outcomeReference.setBehavior("error");
      mount();
      expect(await screen.findByTestId("outcome-error")).toBeInTheDocument();
      expect(screen.queryByTestId("outcome-documents")).not.toBeInTheDocument();
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

    it("результат основной колонкой, внизу вкладки, колонок и разделителей нет", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      expect(screen.getByTestId("outcome-screen")).toHaveAttribute(
        "data-phone",
        "true",
      );
      expect(
        screen.queryByTestId("outcome-inputs-panel"),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByTestId("outcome-rules-panel"),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByTestId("outcome-inputs-splitter"),
      ).not.toBeInTheDocument();
      expect(
        screen.getByRole("navigation", { name: "Разделы экрана" }),
      ).toBeInTheDocument();
      expect(screen.getByTestId("outcome-tab-result")).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    });

    it("«Вводные» открываются листом, вкладка живёт в адресе", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      fireEvent.click(screen.getByTestId("outcome-tab-inputs"));
      expect(location()).toContain("tab=inputs");
      const sheet = await screen.findByRole("dialog");
      expect(within(sheet).getByTestId("outcome-inputs")).toBeInTheDocument();
      fireEvent.keyDown(sheet, { key: "Escape" });
      await waitFor(() => {
        expect(location()).not.toContain("tab=");
      });
    });

    it("ссылка с tab=rules открывает «Почему» сразу, правка недоступна", async () => {
      mount("tab=rules&selected=documents:report");
      const sheet = await screen.findByRole("dialog");
      expect(within(sheet).getByTestId("outcome-selected")).toHaveTextContent(
        "report",
      );
      expect(sheet).toHaveTextContent("Правка доступна на компьютере");
    });

    it("карточки на телефоне: клик выбирает элемент и открывает «Почему»", async () => {
      mount();
      const card = await screen.findByTestId("outcome-doc-thesis");
      fireEvent.click(within(card).getByRole("button"));
      expect(location()).toContain("selected=documents%3Athesis");
      expect(location()).toContain("tab=rules");
    });

    it("в режиме «Как студент» вкладки «Почему» нет", async () => {
      mount("mode=student");
      await screen.findByTestId("outcome-count-documents");
      expect(screen.queryByTestId("outcome-tab-rules")).not.toBeInTheDocument();
    });
  });
});
