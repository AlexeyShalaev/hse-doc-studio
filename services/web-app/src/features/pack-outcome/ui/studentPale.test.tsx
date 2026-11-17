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
  setExplainBehavior,
} from "@entities/pack-studio/reference";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { installViewport } from "@shared/lib/viewport/testing";
import { OutcomeBody } from "../OutcomeBody";

// Режим «Как студент» и бледные слоты (срез F13) на эталонах контракта и настоящих ответах
// `explain` (reference/explainReal.json): подмена API отвечает вместо сервера.

const WS = "ws-student";
const VKR: PackVersionRef = {
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

const version = (v: string, dir: string) => ({
  version: v,
  path: `${dir}/${v}`,
  status: "beta" as const,
  released: false,
  modified: false,
});

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
          name: { ru: "ВКР бакалавра" },
          default_version: "2026.1.2",
          versions: [version("2026.1.2", "hse-cs-se/templates/vkr/versions")],
        },
      ],
    },
    {
      id: "hse-cs-sse",
      path: "hse-cs-sse",
      name: { ru: "ФКН, Системная и программная инженерия" },
      templates: [
        {
          id: "coursework",
          path: "hse-cs-sse/templates/coursework",
          name: { ru: "Курсовой проект" },
          default_version: "2026.1.6",
          versions: [
            version("2026.1.6", "hse-cs-sse/templates/coursework/versions"),
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

const pathOf = (ref: PackVersionRef) =>
  `/pack-studio/w/${WS}/result/${ref.pack}/${ref.template}/${ref.version}`;

const mount = (
  search = "",
  ref: PackVersionRef = VKR,
  seed?: (client: QueryClient) => void,
) => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, retryDelay: 0 },
    },
  });
  client.setQueryData(packStudioKeys.tree(WS), tree);
  seed?.(client);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[`${pathOf(ref)}${search ? `?${search}` : ""}`]}
      >
        <OutcomeBody workspace={workspace} version={ref} />
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
};

const location = () => screen.getByTestId("location").textContent;
const inputParams = () =>
  [...new URLSearchParams(location().split("?")[1] ?? "").entries()].filter(
    ([name]) => name.startsWith("i."),
  );

const setup = () => {
  beforeAll(async () => {
    installOutcomeReference();
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    window.localStorage.clear();
    outcomeReference.setSource("reference");
    setExplainBehavior("normal");
  });
  afterEach(async () => {
    cleanup();
    outcomeReference.setSource("reference");
    outcomeReference.setBehavior("normal");
    setExplainBehavior("normal");
    window.localStorage.clear();
    await i18n.changeLanguage("ru");
  });
};

const student = () => screen.findByTestId("outcome-student");
const text = (testId: string) => screen.getByTestId(testId);

describe("режим «Как студент»", () => {
  setup();

  it("три блока: документы, что заполнить, кто подписывает; секций автора нет", async () => {
    mount("mode=student");
    await student();
    expect(text("outcome-student-documents")).toBeInTheDocument();
    expect(text("outcome-student-fields")).toBeInTheDocument();
    expect(text("outcome-student-route")).toBeInTheDocument();
    for (const id of ["documents", "meta", "participants", "points", "route"]) {
      expect(
        screen.queryByTestId(`outcome-section-${id}`),
      ).not.toBeInTheDocument();
    }
    expect(screen.getByTestId("outcome-screen")).toHaveAttribute(
      "data-mode",
      "student",
    );
  });

  it("документы: названия и имена файлов, без выключенных и отсутствующих", async () => {
    mount("mode=student");
    await student();
    const doc = text("outcome-student-doc-technical_specification");
    expect(doc).toHaveTextContent("Техническое задание");
    expect(doc).toHaveTextContent("Техническое задание.pdf");
    expect(
      screen.queryByTestId("outcome-student-doc-operator_manual"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("outcome-student-doc-annotation"),
    ).not.toBeInTheDocument();
    const block = text("outcome-student-documents");
    expect(block).not.toHaveTextContent("Выключен");
    expect(block).not.toHaveTextContent("Не в этой комбинации");
    expect(block).not.toHaveTextContent("Руководство оператора");
    // Необязательный документ помечен словами.
    expect(text("outcome-student-doc-source_listing")).toHaveTextContent(
      "по желанию",
    );
  });

  it("поля: обязательные при создании и при финализации, скрытые поля анкеты не видны", async () => {
    mount("mode=student");
    await student();
    expect(text("outcome-student-fields-create")).toHaveTextContent(
      "Учебный год (год защиты)",
    );
    expect(text("outcome-student-fields-finalize")).toHaveTextContent(
      "Код УДК",
    );
    const form = text("outcome-student-form-ai_declaration");
    expect(form).toHaveTextContent("Декларация об использовании ИИ");
    expect(form).toHaveTextContent("Использование ИИ");
    expect(form).not.toHaveTextContent("Какие инструменты");
    // Необязательных и технических полей проекта нет, идентификаторов тоже.
    const fields = text("outcome-student-fields");
    expect(fields).not.toHaveTextContent("font_main");
    expect(fields).not.toHaveTextContent("ai_declaration");
  });

  it("маршрут: шаги по порядку, роли человеческими именами, документы подписанта", async () => {
    mount("mode=student");
    await student();
    const step1 = text("outcome-student-step-pdp-application-1");
    expect(step1).toHaveTextContent("Шаг 1");
    expect(step1).toHaveTextContent("Автор");
    expect(step1).toHaveTextContent("Иванов Иван Иванович");
    const step2 = text("outcome-student-step-pdp-application-2");
    expect(step2).toHaveTextContent("Руководитель");
    expect(step2).toHaveTextContent("Петров Пётр Петрович");
    expect(text("outcome-student-point-pdp-application")).toHaveTextContent(
      "Заявление на ПДП",
    );
  });

  it("служебных меток нет: источники, пресеты, may_add, пропущенное, предупреждения, идентификаторы", async () => {
    mount("mode=student");
    await student();
    const view = text("outcome-student");
    for (const label of [
      "из точки",
      "из пресета",
      "пресет",
      "Можно добавить",
      "Пропущены условием",
      "Нет человека",
      "Порядок:",
      "Почему",
      "Добавить во вводных",
    ]) {
      expect(view).not.toHaveTextContent(label);
    }
    expect(view.querySelector(".po-person-warn")).toBeNull();
    expect(view.querySelector("[data-testid^='outcome-pale']")).toBeNull();
    expect(view.querySelector("button")).toBeNull();
    // Идентификаторы документов, слотов и персон не показываются.
    expect(view).not.toHaveTextContent("technical_specification");
    expect(view).not.toHaveTextContent("pdp_assignment");
    expect(view).not.toHaveTextContent("checkpoint");
    expect(screen.queryByTestId("outcome-rules-panel")).not.toBeInTheDocument();
  });

  it("вводные остаются: панель на месте, смена вводной пишется в адрес", async () => {
    mount("mode=student");
    await student();
    const panel = await screen.findByTestId("outcome-inputs-panel");
    const row = await within(panel).findByTestId("outcome-input-kind");
    fireEvent.click(
      within(row).getByRole("radio", { name: "Исследовательская" }),
    );
    await waitFor(
      () => {
        expect(location()).toContain("i.kind=research");
      },
      { timeout: 2000 },
    );
    expect(location()).toContain("mode=student");
    // Эталон отвечает одним результатом на любые вводные: вид студента остаётся и перерисован.
    expect(await student()).toBeInTheDocument();
    expect(screen.getByTestId("outcome-inputs-panel")).toBeInTheDocument();
  });

  it("английский интерфейс: подписи и названия", async () => {
    await i18n.changeLanguage("en");
    mount("mode=student");
    await student();
    expect(text("outcome-student-documents")).toHaveTextContent(
      "The student gets",
    );
    expect(
      text("outcome-student-doc-technical_specification"),
    ).toHaveTextContent("Statement of Work");
    expect(text("outcome-student-fields-create")).toHaveTextContent(
      "When creating the project",
    );
    expect(text("outcome-student-step-pdp-application-1")).toHaveTextContent(
      "Step 1",
    );
    expect(text("outcome-student-step-pdp-application-1")).toHaveTextContent(
      "Author",
    );
  });

  describe("переключатель и Alt", () => {
    it("aria-pressed, подсказка про Alt и переход фокуса в результат", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      expect(screen.queryByTestId("outcome-mode-hint")).not.toBeInTheDocument();
      const toggle = screen.getByTestId("outcome-mode-student");
      toggle.focus();
      fireEvent.click(toggle);
      expect(location()).toContain("mode=student");
      expect(toggle).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByTestId("outcome-mode-author")).toHaveAttribute(
        "aria-pressed",
        "false",
      );
      await student();
      // Фокус уходит в область результата, а не остаётся на переключателе.
      expect(screen.getByTestId("outcome-center")).toHaveFocus();
      // Смена режима объявляется словами.
      expect(screen.getByTestId("outcome-live")).toHaveTextContent(
        "Режим «Как студент»",
      );
      // Подсказка привязана к группе режима для скринридера.
      const hint = screen.getByTestId("outcome-mode-hint");
      expect(hint).toHaveTextContent("Alt");
      expect(screen.getByRole("group", { name: "Режим" })).toHaveAttribute(
        "aria-describedby",
        hint.id,
      );
      fireEvent.click(screen.getByTestId("outcome-mode-author"));
      expect(screen.getByTestId("outcome-live")).toHaveTextContent(
        "Режим «Автор»",
      );
      expect(screen.queryByTestId("outcome-student")).not.toBeInTheDocument();
    });

    it("Alt временно показывает вид автора, режим в адресе не меняется", async () => {
      mount("mode=student");
      await student();
      fireEvent.keyDown(window, { key: "Alt", altKey: true });
      await screen.findByTestId("outcome-section-documents");
      expect(screen.getByTestId("outcome-screen")).toHaveAttribute(
        "data-mode",
        "author",
      );
      expect(screen.getByTestId("outcome-screen")).toHaveAttribute(
        "data-peek",
        "true",
      );
      expect(screen.queryByTestId("outcome-student")).not.toBeInTheDocument();
      expect(screen.getByTestId("outcome-rules-panel")).toBeInTheDocument();
      expect(screen.getByTestId("outcome-mode-hint")).toHaveTextContent(
        "Alt удерживается",
      );
      // Переключатель по-прежнему показывает выбранный режим, адрес не тронут.
      expect(screen.getByTestId("outcome-mode-student")).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      expect(location()).toContain("mode=student");
      fireEvent.keyUp(window, { key: "Alt" });
      await student();
      expect(
        screen.queryByTestId("outcome-section-documents"),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByTestId("outcome-rules-panel"),
      ).not.toBeInTheDocument();
    });

    it("сочетание с Alt и потеря фокуса окном возвращают вид студента", async () => {
      mount("mode=student");
      await student();
      fireEvent.keyDown(window, { key: "Alt", altKey: true });
      await screen.findByTestId("outcome-section-documents");
      fireEvent.keyDown(window, { key: "z", code: "KeyZ", altKey: true });
      await student();
      fireEvent.keyDown(window, { key: "Alt", altKey: true });
      await screen.findByTestId("outcome-section-documents");
      fireEvent.blur(window);
      await student();
    });

    it("в режиме автора Alt ничего не меняет", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      fireEvent.keyDown(window, { key: "Alt", altKey: true });
      expect(screen.getByTestId("outcome-screen")).not.toHaveAttribute(
        "data-peek",
      );
      expect(screen.getByTestId("outcome-rules-panel")).toBeInTheDocument();
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

    it("три блока на месте, вкладки «Почему» нет, подсказки про Alt нет", async () => {
      mount("mode=student");
      await student();
      expect(text("outcome-student-documents")).toBeInTheDocument();
      expect(text("outcome-student-route")).toBeInTheDocument();
      expect(screen.queryByTestId("outcome-tab-rules")).not.toBeInTheDocument();
      // Режим виден в верхней панели меткой, подсказки про Alt на телефоне нет.
      expect(screen.getByTestId("outcome-phone-student")).toBeInTheDocument();
      expect(screen.queryByTestId("outcome-mode-hint")).toBeNull();
      // Вводные студент меняет во вкладке: она на месте.
      expect(screen.getByTestId("outcome-tab-inputs")).toBeInTheDocument();
    });
  });
});

describe("бледные слоты", () => {
  setup();

  it("участник: бледная карточка с причиной, «Добавить во вводных» применяет одну вводную", async () => {
    mount();
    const slot = await screen.findByTestId("outcome-participant-co_supervisor");
    expect(slot).toHaveAttribute("data-pale", "true");
    expect(slot).toHaveTextContent("нет:");
    const add = within(slot).getByRole("button", {
      name: "Добавить во вводных: Второй руководитель",
    });
    expect(add).toHaveTextContent("Добавить во вводных");
    fireEvent.click(add);
    await waitFor(() => {
      expect(inputParams()).toEqual([["i.co_supervisor", "yes"]]);
    });
  });

  it("присутствующие элементы не бледные и действия не имеют", async () => {
    mount();
    const slot = await screen.findByTestId("outcome-participant-supervisor");
    expect(slot).not.toHaveAttribute("data-pale");
    expect(within(slot).queryByText("Добавить во вводных")).toBeNull();
    const doc = screen.getByTestId("outcome-doc-technical_specification");
    expect(doc).not.toHaveAttribute("data-pale");
  });

  it("выключенный документ: вводная из «что если» сервера, умолчание не пишется в адрес", async () => {
    // Эталон ответа посчитан на «Только программиста»: вводная стоит в адресе явно.
    mount("i.meta.manuals=Только программиста&i.meta.nda=yes");
    const card = await screen.findByTestId("outcome-doc-operator_manual");
    expect(card).toHaveAttribute("data-pale", "true");
    fireEvent.click(
      within(card).getByRole("button", {
        name: /^Добавить во вводных: Руководство оператора/,
      }),
    );
    // Сервер предложил «Программиста и оператора»: это умолчание версии, запись вводной снимается.
    await waitFor(() => {
      expect(inputParams()).toEqual([["i.meta.nda", "yes"]]);
    });
  });

  it("документ, которого нет в комплекте, лежит в блоке «Не в этой комбинации» бледным", async () => {
    mount();
    await screen.findByTestId("outcome-count-documents");
    fireEvent.click(screen.getByTestId("outcome-documents-absent-toggle"));
    const card = screen.getByTestId(
      "outcome-doc-shared_technical_specification",
    );
    expect(card).toHaveAttribute("data-pale", "true");
    fireEvent.click(
      within(card).getByTestId(
        "outcome-pale-add-documents-shared_technical_specification",
      ),
    );
    await waitFor(() => {
      expect(inputParams()).toEqual([["i.staffing", "team2"]]);
    });
  });

  it("пункт точки, выключенный документом: если сервер не предложил вводной, слот пишет об этом", async () => {
    mount();
    await screen.findByTestId("outcome-count-points");
    fireEvent.click(screen.getByTestId("outcome-point-final-off-toggle"));
    const row = screen.getByTestId("outcome-item-final-operator_manual");
    expect(row).toHaveAttribute("data-pale", "true");
    fireEvent.click(
      screen.getByTestId("outcome-pale-add-points-final/operator_manual"),
    );
    await waitFor(() => {
      expect(
        screen.getByTestId("outcome-pale-note-points-final/operator_manual"),
      ).toHaveTextContent("Одной вводной это не включить");
    });
    expect(inputParams()).toEqual([]);
  });

  it("запрос не удался: слот пишет об этом и позволяет повторить", async () => {
    mount();
    const slot = await screen.findByTestId("outcome-participant-co_supervisor");
    setExplainBehavior("fail");
    fireEvent.click(within(slot).getByRole("button", { name: /Добавить/ }));
    await waitFor(
      () => {
        expect(
          screen.getByTestId("outcome-pale-note-participants-co_supervisor"),
        ).toHaveTextContent("Не удалось найти вводную");
      },
      { timeout: 4000 },
    );
    expect(inputParams()).toEqual([]);
    setExplainBehavior("normal");
    fireEvent.click(within(slot).getByRole("button", { name: /Добавить/ }));
    await waitFor(() => {
      expect(inputParams()).toEqual([["i.co_supervisor", "yes"]]);
    });
  }, 10_000);

  it("английский интерфейс и клавиатура: Enter на кнопке применяет вводную", async () => {
    await i18n.changeLanguage("en");
    mount();
    const slot = await screen.findByTestId("outcome-participant-co_supervisor");
    const add = within(slot).getByRole("button", {
      name: /^Add in inputs: /,
    });
    expect(add).toHaveTextContent("Add in inputs");
    const user = userEvent.setup();
    add.focus();
    await user.keyboard("{Enter}");
    await waitFor(() => {
      expect(inputParams()).toEqual([["i.co_supervisor", "yes"]]);
    });
  });

  it("в режиме «Как студент» бледных слотов нет", async () => {
    mount("mode=student");
    await student();
    expect(document.querySelector("[data-pale]")).toBeNull();
  });
});
