import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  screen,
  within,
} from "@testing-library/react";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { i18n } from "@shared/lib";
import { packOutcomeKeys, type PackOutcome } from "@entities/pack-studio";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import banned from "../vocabulary.banned.json";
import { SpaceScreen } from "../shell/SpaceScreen";
import { renderSpace, SPACE_BASE } from "../spaceTestKit";
import { seedResult, type ResultSeed } from "./gallery.result";
import { deltaStore } from "../situation/deltaStore";
import { seededClient } from "../situation/testKit";
import { slots } from "./slots";

// Центр «Результата» на фикстурах PackOutcome (coursework_company_cosupervisor,
// vkr_nda_programmer_only): заголовок, оглавление, части, «Не вошло», выбор строки и
// тест-ограничитель на число элементов управления.

const location = () => screen.getByTestId("location").textContent;

const mount = async (
  seed: ResultSeed = {},
  query = "",
  options: {
    phone?: boolean;
    /** Правка кэша до первого кадра (например, документ, который не вошёл в комплект). */
    prepare?: (client: QueryClient) => void;
  } = {},
) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  seedResult(client, { ...seed, search: seed.search ?? query });
  options.prepare?.(client);
  const url = `${SPACE_BASE}/2026.1.3/result${query ? `?${query}` : ""}`;
  const view = renderSpace(
    <QueryClientProvider client={client}>
      <SpaceScreen slots={slots} phone={options.phone ?? false} />
    </QueryClientProvider>,
    url,
  );
  await screen.findByTestId("sp-result", undefined, { timeout: 5000 });
  return { ...view, client };
};

/** Лишний документ, который при этих условиях не входит: его строка живёт в «Не вошло». */
const withMissingDoc = (client: QueryClient): void => {
  for (const query of client
    .getQueryCache()
    .findAll({ queryKey: packOutcomeKeys.all("gallery-ws") })) {
    const data = query.state.data as PackOutcome | undefined;
    if (!data || !Array.isArray(data.documents)) continue;
    const doc = data.documents[0];
    if (!doc) continue;
    client.setQueryData(query.queryKey, {
      ...data,
      documents: [
        ...data.documents,
        { ...doc, id: "extra_doc", state: "inactive" },
      ],
    });
  }
};

const CONTROLS =
  'button, a[href], input, select, textarea, [role="tab"], [role="switch"], [role="combobox"], [role="checkbox"], [role="radio"]';

/** Виден ли элемент: не скрыт атрибутом и не убран стилем у себя или предков. */
const shown = (el: Element): boolean => {
  for (let node: Element | null = el; node; node = node.parentElement) {
    if (node.hasAttribute("hidden")) return false;
    if (getComputedStyle(node).display === "none") return false;
  }
  return true;
};

const controls = (root: ParentNode = document.body): Element[] =>
  [...root.querySelectorAll(CONTROLS)].filter(
    // «Пропустить к содержимому» уходит за край экрана и видна только в фокусе: не на экране.
    (el) =>
      shown(el) &&
      !el.hasAttribute("disabled") &&
      el.getAttribute("data-testid") !== "sp-skip",
  );

describe("центр «Результата»", () => {
  beforeAll(async () => {
    vi.setConfig({ testTimeout: 20_000 });
    await loadPackSpaceNamespace();
  });
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("заголовок говорит на языке студента, режимов «Автор» и «Как студент» нет", async () => {
    await mount();
    expect(screen.getByTestId("sp-result-title")).toHaveTextContent(
      "Студент получит 4 документа",
    );
    expect(screen.getByTestId("sp-result")).toHaveTextContent(
      "Подписывают 4 человека, сдача в 4 точках.",
    );
    expect(screen.queryByText(/как студент/i)).toBeNull();
    expect(screen.queryByRole("tab")).toBeNull();
    expect(screen.queryByText(/автор\s*\/\s*студент/i)).toBeNull();
  });

  it("части идут по порядку, раскрыты «Документы», у свёрнутых виден итог", async () => {
    await mount();
    const parts = ["documents", "data", "people", "deadlines", "signatures"];
    for (const id of parts) {
      const toggle = screen.getByTestId(`sp-part-${id}-toggle`);
      expect(toggle).toHaveAttribute(
        "aria-expanded",
        id === "documents" ? "true" : "false",
      );
    }
    expect(screen.getByTestId("sp-part-data-toggle")).toHaveTextContent(
      "20 полей, 2 нужно при создании, 1 анкета",
    );
    expect(screen.getByTestId("sp-part-people-toggle")).toHaveTextContent(
      "автор, руководитель из компании, соруководитель из ВШЭ, академический руководитель из ВШЭ",
    );
    expect(screen.getByTestId("sp-part-deadlines-toggle")).toHaveTextContent(
      "4 точки:",
    );
    expect(screen.getByTestId("sp-part-signatures-toggle")).toHaveTextContent(
      "6 подписей в 2 точках",
    );
  });

  it("строка документа: название, файл и языки, кнопка PDF", async () => {
    await mount();
    const row = screen.getByTestId("sp-doc-report");
    expect(row).toHaveTextContent("ru, en");
    expect(row.querySelector(".sp-row-title")?.textContent).not.toBe("");
    expect(
      within(row).getByRole("button", { name: /PDF/ }),
    ).toBeInTheDocument();
  });

  it("нажатие на строку выбирает элемент в адресе, повторное снимает выбор", async () => {
    await mount();
    const pick = within(screen.getByTestId("sp-doc-report")).getAllByRole(
      "button",
    )[0]!;
    fireEvent.click(pick);
    expect(location()).toContain("sel=documents%3Areport");
    expect(pick).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(pick);
    expect(location()).not.toContain("sel=");
  });

  it("PDF выбирает документ и просит открыть предпросмотр", async () => {
    await mount();
    fireEvent.click(screen.getByTestId("sp-doc-report-pdf"));
    expect(location()).toContain("sel=documents%3Areport");
    expect(location()).toContain("preview=1");
  });

  it("вариант документа выбирается условием variant.<документ>", async () => {
    await mount();
    const select = screen.getByTestId("sp-doc-presentation-variant");
    fireEvent.change(select, { target: { value: "reveal" } });
    expect(location()).toContain("i.variant.presentation=reveal");
  });

  it("поиск и фильтр документов появляются, только когда документов больше десяти", async () => {
    await mount();
    expect(screen.queryByTestId("sp-docs-search")).toBeNull();
    cleanup();
    await mount({ work: "vkr" });
    expect(screen.getByTestId("sp-docs-search")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("sp-docs-search"), {
      target: { value: "презентация" },
    });
    expect(screen.getByTestId("sp-doc-presentation")).toBeInTheDocument();
    expect(screen.queryByTestId("sp-doc-thesis")).toBeNull();
    fireEvent.change(screen.getByTestId("sp-docs-search"), {
      target: { value: "нет такого документа" },
    });
    expect(screen.getByTestId("sp-docs-noresults")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("sp-docs-search"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByTestId("sp-docs-scope"), {
      target: { value: "shared" },
    });
    // Общие документы в комплекте этой работы не входят: остаётся только «Не вошло».
    expect(screen.queryByTestId("sp-doc-thesis")).toBeNull();
    expect(screen.getByTestId("sp-docs-missing-toggle")).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  describe("«Не вошло в комплект»", () => {
    it("свёрнуто, пока не раскрыли, с числом", async () => {
      await mount({ work: "vkr" });
      const toggle = screen.getByTestId("sp-docs-missing-toggle");
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(toggle).toHaveTextContent("Не вошло в комплект");
      expect(toggle).toHaveTextContent("6");
      expect(screen.queryByTestId("sp-doc-missing-annotation")).toBeNull();
    });

    it("у каждой строки причина простыми словами и кнопка, которая ставит условие", async () => {
      await mount({ work: "vkr" });
      fireEvent.click(screen.getByTestId("sp-docs-missing-toggle"));
      const row = screen.getByTestId(
        "sp-doc-missing-shared_technical_specification",
      );
      expect(row).toHaveTextContent(
        "Состав: нужно «команда из двух, команда из трёх», сейчас «один автор».",
      );
      const show = within(row).getByRole("button", { name: /Показать при/ });
      fireEvent.click(show);
      expect(location()).toContain("i.staffing=team2");
    });

    it("причина встроенного правила про руководства тоже словами, без служебных id", async () => {
      await mount({ work: "vkr" });
      fireEvent.click(screen.getByTestId("sp-docs-missing-toggle"));
      const row = screen.getByTestId("sp-doc-missing-operator_manual");
      expect(row.textContent).not.toMatch(
        /builtin|manifest|\.yaml|\/supported/,
      );
      expect(row.textContent ?? "").toMatch(/Руководства|руководства/);
    });

    it("раскрытость запоминается", async () => {
      await mount({ work: "vkr" });
      fireEvent.click(screen.getByTestId("sp-docs-missing-toggle"));
      cleanup();
      // Новая вкладка: память браузера та же, хранилище экрана новое.
      await mount({ work: "vkr", open: null });
      expect(screen.getByTestId("sp-docs-missing-toggle")).toHaveAttribute(
        "aria-expanded",
        "true",
      );
    });

    it("участник, которого нет, объяснён условием и возвращается кнопкой", async () => {
      await mount({
        work: "vkr",
        open: ["people"],
        missing: true,
      });
      const row = screen.getByTestId("sp-person-missing-co_supervisor");
      expect(row).toHaveTextContent(
        "Нет, пока условие «Соруководитель» стоит «нет».",
      );
      fireEvent.click(
        within(row).getByRole("button", { name: /Показать при/ }),
      );
      expect(location()).toContain("i.co_supervisor=yes");
    });

    it("в раскрытых «Не вошло» всех частей нет слов из списка «жаргон»", async () => {
      await mount({
        work: "vkr",
        open: ["documents", "data", "people", "deadlines", "signatures"],
        missing: true,
      });
      const text = screen.getByTestId("sp-result").textContent ?? "";
      for (const rule of banned.ru) {
        expect(text, rule.id).not.toMatch(new RegExp(rule.pattern, "i"));
      }
    });
  });

  describe("остальные части", () => {
    it("данные проекта: поля по группам, бейджи, анкеты", async () => {
      await mount({ open: ["data"] });
      expect(screen.getByTestId("sp-field-year")).toHaveTextContent(
        "при создании",
      );
      expect(screen.getByTestId("sp-form-code_link")).toHaveTextContent(
        "у каждого автора",
      );
      fireEvent.click(
        within(screen.getByTestId("sp-field-year")).getAllByRole("button")[0]!,
      );
      expect(location()).toContain("sel=meta%3Ayear");
    });

    it("участники: роль, имя и организация", async () => {
      await mount({ open: ["people"] });
      const row = screen.getByTestId("sp-person-supervisor");
      expect(row).toHaveTextContent("Руководитель");
      expect(row).toHaveTextContent("Компания");
      expect(row).toHaveTextContent("Смирнов Олег Игоревич");
    });

    it("сроки и сдача: срок словами и что сдаётся", async () => {
      await mount({ open: ["deadlines"] });
      const row = screen.getByTestId("sp-point-topic-approval");
      expect(row).toHaveTextContent("Обычно в середине ноября");
      expect(row).toHaveTextContent("2 документа");
      fireEvent.click(within(row).getAllByRole("button")[0]!);
      expect(location()).toContain("sel=points%3Atopic-approval");
    });

    it("подписи: порядок словами и число подписей", async () => {
      await mount({ open: ["signatures"] });
      const row = screen.getByTestId("sp-sign-topic-approval");
      expect(row).toHaveTextContent(
        "Автор, затем руководитель и соруководитель, затем академический руководитель",
      );
      expect(row).toHaveTextContent("5 подписей");
      // Точки без подписей в список не попадают.
      expect(screen.queryByTestId("sp-sign-pre-defence")).toBeNull();
      fireEvent.click(within(row).getAllByRole("button")[0]!);
      expect(location()).toContain("sel=route%3Atopic-approval");
    });
  });

  describe("оглавление", () => {
    it("части с числами, текущая отмечена", async () => {
      await mount();
      const toc = await screen.findByTestId("sp-toc");
      expect(within(toc).getByTestId("sp-toc-documents")).toHaveTextContent(
        "Документы4",
      );
      expect(within(toc).getByTestId("sp-toc-people")).toHaveTextContent("4");
      expect(within(toc).getByTestId("sp-toc-documents")).toHaveAttribute(
        "aria-current",
        "location",
      );
    });

    it("нажатие раскрывает часть, делает её текущей и прокручивает к ней", async () => {
      const scroll = vi.fn();
      Element.prototype.scrollIntoView = scroll;
      vi.stubGlobal("requestAnimationFrame", (run: () => void) => {
        run();
        return 0;
      });
      await mount();
      const toggle = screen.getByTestId("sp-part-signatures-toggle");
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      fireEvent.click(await screen.findByTestId("sp-toc-signatures"));
      expect(toggle).toHaveAttribute("aria-expanded", "true");
      expect(screen.getByTestId("sp-toc-signatures")).toHaveAttribute(
        "aria-current",
        "location",
      );
      expect(screen.getByTestId("sp-toc-documents")).not.toHaveAttribute(
        "aria-current",
      );
      expect(scroll).toHaveBeenCalledTimes(1);
      expect(scroll.mock.contexts[0]).toBe(
        document.getElementById("sp-part-signatures"),
      );
    });

    it("текущая часть следует за прокруткой", async () => {
      let notify: IntersectionObserverCallback = () => undefined;
      vi.stubGlobal(
        "IntersectionObserver",
        class {
          constructor(callback: IntersectionObserverCallback) {
            notify = callback;
          }
          observe = vi.fn();
          disconnect = vi.fn();
          unobserve = vi.fn();
        },
      );
      await mount();
      const toc = await screen.findByTestId("sp-toc");
      act(() => {
        notify(
          [
            {
              isIntersecting: true,
              target: document.getElementById("sp-part-deadlines"),
            } as unknown as IntersectionObserverEntry,
          ],
          {} as IntersectionObserver,
        );
      });
      expect(within(toc).getByTestId("sp-toc-deadlines")).toHaveAttribute(
        "aria-current",
        "location",
      );
    });

    it("две ссылки в «Проверку»: что на что влияет и типовые случаи", async () => {
      await mount();
      expect(await screen.findByTestId("sp-toc-map")).toHaveAttribute(
        "href",
        expect.stringContaining("/check?part=map"),
      );
      expect(screen.getByTestId("sp-toc-cases")).toHaveAttribute(
        "href",
        expect.stringContaining("/check?part=cases"),
      );
    });
  });

  describe("состояния", () => {
    it("считаю: каркас без пустого экрана", async () => {
      await mount({ kind: "loading" });
      expect(screen.getByTestId("sp-result-loading")).toBeInTheDocument();
    });

    it("не удалось посчитать: причина и «Повторить»", async () => {
      await mount({ kind: "error" });
      expect(screen.getByTestId("sp-result-error")).toHaveTextContent(
        "Не удалось посчитать результат",
      );
    });

    it("в версии нет документов: пустое состояние объясняет, что будет", async () => {
      await mount({ kind: "empty" });
      expect(screen.getByTestId("sp-result-empty")).toHaveTextContent(
        "В этой версии нет документов",
      );
      expect(screen.getByTestId("sp-result-title")).toHaveTextContent(
        "Студент не получит ни одного документа",
      );
    });

    it("английский язык: заголовок и части", async () => {
      await i18n.changeLanguage("en");
      try {
        await mount();
        expect(screen.getByTestId("sp-result-title")).toHaveTextContent(
          "The student will get 4 documents",
        );
        expect(screen.getByTestId("sp-part-data-toggle")).toHaveTextContent(
          "Project data",
        );
      } finally {
        await i18n.changeLanguage("ru");
      }
    });
  });

  describe("тест-ограничитель: элементов управления на экране", () => {
    // Считаем всё, что видно в разметке экрана (без свёрнутого и скрытого стилем): это верхняя
    // граница того, что видно без прокрутки. Макет: 36 на 1440 на 900 и 13 на 390 на 844.
    // Экран: запасные части каркаса (назад, три вкладки или четыре нижние) и наша область.
    it("1440 на 900: не больше 40 при открытых «Документах»", async () => {
      await mount({}, "sel=documents%3Areport");
      const all = controls();
      expect(all.length).toBeLessThanOrEqual(40);
      // Область «Результата» занимает меньше, чем остаётся каркасу и соседним срезам.
      expect(
        controls(screen.getByTestId("sp-toc")).length +
          controls(screen.getByTestId("sp-result")).length,
      ).toBeLessThanOrEqual(28);
    });

    it("390 на 844: не больше 16 при открытых «Документах»", async () => {
      await mount({}, "", { phone: true });
      expect(screen.queryByTestId("sp-toc")).toBeNull();
      expect(controls().length).toBeLessThanOrEqual(16);
    });

    it("390 на 844: не больше 16 и при раскрытом «Не вошло»", async () => {
      await mount({ missing: true }, "", {
        phone: true,
        prepare: withMissingDoc,
      });
      expect(screen.getByTestId("sp-docs-missing-toggle")).toHaveAttribute(
        "aria-expanded",
        "true",
      );
      expect(controls().length).toBeLessThanOrEqual(16);
    });

    it("на телефоне у строки «Не вошло» одна кнопка: «Показать при» живёт в подробностях", async () => {
      await mount({ work: "vkr", missing: true }, "", { phone: true });
      const list = screen.getByTestId("sp-docs-missing");
      const rows = [...list.querySelectorAll("li.sp-row")];
      expect(rows.length).toBe(6);
      for (const row of rows) expect(controls(row)).toHaveLength(1);
      expect(
        within(list).queryByRole("button", { name: /Показать при/ }),
      ).toBeNull();
    });

    it("на телефоне в строке документа одна кнопка, PDF живёт в подробностях", async () => {
      await mount({}, "", { phone: true });
      const row = screen.getByTestId("sp-doc-report");
      expect(controls(row)).toHaveLength(1);
    });

    it("ВКР с 18 документами: у строки не больше трёх элементов (выбор, вариант, PDF)", async () => {
      await mount({ work: "vkr" });
      const rows = [
        ...screen.getByTestId("sp-documents").querySelectorAll("li.sp-row"),
      ];
      expect(rows.length).toBe(12);
      for (const row of rows)
        expect(controls(row).length).toBeLessThanOrEqual(3);
    });
  });
});

describe("подсветка после смены условия (useSituationDelta)", () => {
  const SCOPE = "gallery-ws/hse-cs-sse/coursework/2026.1.3";
  const QUERY = "i.supervisor=company";
  const COMPARE = {
    left: { state: "work_tree" as const, inputs: {} },
    right: { state: "work_tree" as const, inputs: { supervisor: "company" } },
  };

  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  beforeEach(() => {
    window.localStorage.clear();
    deltaStore.reset();
  });
  afterEach(cleanup);

  const mountDelta = async (extra = "") => {
    const client = seededClient({ compare: COMPARE });
    seedResult(client, { open: ["people", "signatures"], search: QUERY });
    deltaStore.record({
      scope: SCOPE,
      before: { inputs: {}, caseId: null },
      after: { inputs: { supervisor: "company" }, caseId: null },
      label: "Научный руководитель: Из компании",
    });
    renderSpace(
      <QueryClientProvider client={client}>
        <SpaceScreen slots={slots} phone={false} />
      </QueryClientProvider>,
      `${SPACE_BASE}/2026.1.3/result?${QUERY}${extra}`,
    );
    await screen.findByTestId("sp-result", undefined, { timeout: 5000 });
  };

  it("изменившиеся строки подсвечены, новое помечено, остальные нет", async () => {
    await mountDelta();
    const added = screen.getByTestId("sp-person-co_supervisor");
    expect(added).toHaveAttribute("data-flash", "true");
    expect(added).toHaveTextContent("новое");
    // Точка сдачи изменилась по шагам маршрута: строка подсвечена целиком.
    expect(screen.getByTestId("sp-sign-topic-approval")).toHaveAttribute(
      "data-flash",
      "true",
    );
    expect(screen.getByTestId("sp-person-author")).not.toHaveAttribute(
      "data-flash",
    );
  });

  it("«только изменившееся»: остальные строки и части скрыты", async () => {
    await mountDelta("&delta=1");
    expect(screen.getByTestId("sp-person-co_supervisor")).toBeInTheDocument();
    expect(screen.queryByTestId("sp-person-author")).toBeNull();
    expect(screen.queryByTestId("sp-doc-report")).toBeNull();
    expect(screen.queryByTestId("sp-part-documents")).toBeNull();
    expect(screen.getByTestId("sp-part-people")).toBeInTheDocument();
  });
});
