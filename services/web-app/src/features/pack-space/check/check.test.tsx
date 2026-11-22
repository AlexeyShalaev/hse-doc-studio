import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  configure,
  fireEvent,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { SpaceScreen } from "../shell/SpaceScreen";
import { renderSpace, SPACE_BASE } from "../spaceTestKit";
import {
  COMPARE_SEARCH,
  seedCases,
  seedCompare,
  seedLint,
  seedMap,
  type Lint,
} from "./seeds";
import { slots } from "./slots";

const CHECK = `${SPACE_BASE}/2026.1.3/check`;
const location = () => screen.getByTestId("location").textContent ?? "";

const open = (seed: (client: QueryClient) => void, search = "") => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  seed(client);
  return renderSpace(
    <QueryClientProvider client={client}>
      <SpaceScreen slots={slots} phone={false} />
    </QueryClientProvider>,
    `${CHECK}${search}`,
  );
};
const openLint = (kind: Lint = "normal") =>
  open((client) => {
    seedLint(client, kind);
  });

describe("вкладка «Проверка»", { timeout: 30_000 }, () => {
  beforeAll(async () => {
    configure({ asyncUtilTimeout: 8000 });
    await loadPackSpaceNamespace();
    await i18n.changeLanguage("ru");
    // Части грузятся отдельным чанком: прогреваем, чтобы тесты не ждали первую трансформацию.
    await Promise.all([import("./CheckMain"), import("./CheckNav")]);
  }, 60_000);
  afterEach(cleanup);

  describe("левая колонка", () => {
    it("три части и сравнение, открытая отмечена, у «Замечаний» число", async () => {
      openLint();
      const nav = await screen.findByRole("navigation", {
        name: "Что проверяем",
      });
      const links = within(nav).getAllByRole("link");
      expect(links.map((link) => link.textContent)).toEqual([
        expect.stringContaining("Замечания"),
        "Типовые случаи",
        "Что на что влияет",
        "Сравнить с другой ситуацией",
      ]);
      expect(links[0]).toHaveAttribute("aria-current", "page");
      expect(links[1]).toHaveAttribute(
        "href",
        expect.stringContaining("part=cases"),
      );
      expect(links[3]).toHaveAttribute(
        "href",
        expect.stringContaining("compare=1"),
      );
      // Ошибка и два замечания: у подсказок отдельной строки, в число они не входят.
      expect(
        await within(nav).findByLabelText("Нужно посмотреть: 3"),
      ).toBeInTheDocument();
    });
  });

  describe("Замечания", () => {
    it("итог одной фразой, находки по уровням, как исправить", async () => {
      openLint();
      expect(
        await screen.findByText("Проверка шаблона. Ошибок: 1, замечаний: 2"),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("heading", { name: /^Ошибки/ }),
      ).toBeInTheDocument();
      expect(screen.getAllByText("Как исправить:").length).toBeGreaterThan(0);
      expect(
        screen.getByRole("button", { name: "Перепроверить" }),
      ).toBeEnabled();
      expect(
        screen.getByRole("button", { name: "Проверить тексты шаблонов" }),
      ).toBeEnabled();
    });

    it("находки человеческими словами: текст сервера, правило и файл только в технических подробностях (V1)", async () => {
      openLint();
      await screen.findByText(/Проверка шаблона/);
      const items = screen.getAllByTestId("check-finding");
      expect(items.length).toBeGreaterThan(0);
      for (const item of items) {
        const clone = item.cloneNode(true) as HTMLElement;
        const tech = clone.querySelector("details");
        expect(tech).not.toBeNull();
        tech?.remove();
        expect(clone.textContent).not.toMatch(
          /слот|атлас|вводн|signing_slots|signatures\.|visible_if|supported_|\bhelp\b|\blangs\b|\bwhen\b|[a-z]+_[a-z]+|[a-z]+-[a-z]+/i,
        );
        // Сырое сообщение сервера и номер правила на месте, под «Технические подробности».
        const raw = item.querySelector("details dl")?.textContent ?? "";
        expect(raw).toMatch(/Текст сервера/);
        expect(raw).toMatch(/Номер проверки/);
      }
    });

    it("подпись, которой не будет: заголовок словами, роль из словаря, остальные названия не получены: «…», «Как исправить» есть (V1)", async () => {
      openLint();
      const title = await screen.findByText(
        "Подпись «Академический руководитель» у документа «…» в «…» не появится никогда",
      );
      expect(title.textContent).toBe(
        "Подпись «Академический руководитель» у документа «…» в «…» не появится никогда",
      );
      const item = title.closest("li");
      expect(item?.textContent).toMatch(/Как исправить:/);
      const clone = item?.cloneNode(true) as HTMLElement;
      clone.querySelector("details")?.remove();
      expect(clone.textContent).not.toMatch(
        /academic_supervisor|project_proposal/,
      );
    });

    it("файл и номер проверки спрятаны в технических подробностях", async () => {
      openLint();
      await screen.findByText(/Проверка шаблона/);
      const details = screen.getAllByText("Технические подробности")[0];
      expect(details?.closest("details")).not.toHaveAttribute("open");
    });

    it("«Показать в результате» ведёт на «Результат» с выбранным элементом", async () => {
      openLint();
      const [button] = await screen.findAllByRole("button", {
        name: "Показать в результате",
      });
      fireEvent.click(button!);
      expect(location()).toMatch(/\/result\?.*sel=/);
    });

    it("«Показать такую ситуацию» кладёт условия в адрес результата", async () => {
      openLint();
      await screen.findByText(/Проверка шаблона/);
      const [button] = screen.getAllByRole("button", {
        name: "Показать такую ситуацию",
      });
      fireEvent.click(button!);
      expect(location()).toMatch(/\/result\?.*i\./);
    });

    it("«Открыть место в файле» ведёт в «Содержимое» с файлом версии", async () => {
      openLint();
      const [button] = await screen.findAllByRole("button", {
        name: "Открыть место в файле",
      });
      fireEvent.click(button!);
      expect(location()).toContain("/content?");
      expect(decodeURIComponent(location())).toContain(
        "file=hse-cs-sse/templates/coursework/versions/2026.1.3/",
      );
    });

    it("какие правила проверены готовыми случаями: процент и «Добавить готовые случаи»", async () => {
      openLint();
      await screen.findByText(/Проверка шаблона/);
      expect(
        screen.getByRole("heading", {
          name: "Какие правила проверены готовыми случаями",
        }),
      ).toBeInTheDocument();
      expect(screen.getByText(/^\d+(\.\d+)? %$/)).toBeInTheDocument();
      expect(
        screen.getAllByText("Не проверено ни в одном случае").length,
      ).toBeGreaterThan(0);
      const add = screen.getByRole("button", { name: /Добавить готов/ });
      fireEvent.click(add);
      expect(
        screen.getByText(/нажмите «Запомнить этот случай»/),
      ).toBeInTheDocument();
    });

    it("без замечаний: пустое состояние объясняет и ведёт дальше", async () => {
      openLint("clean");
      expect(await screen.findByText("Замечаний нет")).toBeInTheDocument();
      expect(
        screen.getByText(/проверьте, достаточно ли готовых случаев/),
      ).toBeInTheDocument();
    });

    it("отказ по частоте: человеческие слова и «Повторить»", async () => {
      openLint("rate_limited");
      expect(
        await screen.findByText("Слишком много проверок"),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Повторить" }),
      ).toBeInTheDocument();
    });

    it("пока считается: статус без пустого экрана", async () => {
      openLint("loading");
      expect(
        await screen.findByText(/Проверяю шаблон, это займёт/),
      ).toBeInTheDocument();
    });
  });

  describe("Типовые случаи", () => {
    const openCases = (kind: "ready" | "empty" = "ready") =>
      open((client) => {
        seedCases(client, kind);
      }, "?part=cases");

    it("таблица: готовые случаи в строках, части результата в столбцах", async () => {
      openCases();
      const table = await screen.findByRole("grid", {
        name: "Типовые случаи и части результата",
      });
      expect(within(table).getAllByRole("row")).toHaveLength(4);
      expect(
        within(table).getByRole("columnheader", { name: "Сроки и сдача" }),
      ).toBeInTheDocument();
      expect(screen.getByText(/^Случаев: 3\./)).toBeInTheDocument();
    });

    it("клетка показывает, что в ней, и ведёт к результату или сравнению", async () => {
      openCases();
      const table = await screen.findByRole("grid");
      const cells = within(table)
        .getAllByRole("button")
        .filter((item) => item.hasAttribute("data-r"));
      fireEvent.click(cells[0]!);
      expect(
        screen.getByRole("region", {
          name: "Что изменилось в выбранной части",
        }),
      ).toBeInTheDocument();
      fireEvent.click(
        screen.getByRole("button", { name: "Показать результат" }),
      );
      expect(location()).toMatch(/\/result\?.*case=/);
    });

    it("«Сравнить с другим» открывает сравнение с этим случаем слева", async () => {
      openCases();
      const table = await screen.findByRole("grid");
      fireEvent.click(
        within(table)
          .getAllByRole("button")
          .find((item) => item.hasAttribute("data-r"))!,
      );
      fireEvent.click(
        screen.getByRole("button", { name: "Сравнить с другим" }),
      );
      expect(decodeURIComponent(location())).toMatch(
        /compare=1&left=scenario:[\w-]+/,
      );
    });

    it("переключатель «Относительно» пишет `against` в адрес", async () => {
      openCases();
      await screen.findByRole("grid");
      // Пространство в галерее подключено по git: сверка с версией до правок доступна.
      fireEvent.click(
        screen.getByRole("button", { name: "Версии до моих правок" }),
      );
      expect(location()).toContain("against=base");
    });

    it("нет готовых случаев: объяснение и один следующий шаг", async () => {
      openCases("empty");
      expect(
        await screen.findByText("Готовых случаев пока нет"),
      ).toBeInTheDocument();
      fireEvent.click(
        screen.getByRole("button", { name: "Открыть результат" }),
      );
      expect(location()).toContain("/result");
    });
  });

  describe("Что на что влияет", () => {
    const openMap = (kind: "ready" | "too_many" = "ready", search = "") =>
      open((client) => {
        seedMap(client, kind);
      }, `?part=map${search}`);

    it("сколько всего вариантов и карточки условий с «Меняет»", async () => {
      openMap();
      expect(
        await screen.findByText(
          "Всего вариантов результата: 12 (из 576 сочетаний условий)",
        ),
      ).toBeInTheDocument();
      expect(screen.getAllByText("Меняет:").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Зафиксировать").length).toBeGreaterThan(0);
    });

    it("значение условия фиксируется в адресе и снимается", async () => {
      openMap();
      await screen.findByText(/Всего вариантов результата/);
      const [select] = screen.getAllByRole("combobox", {
        name: /Зафиксировать/,
      });
      const option = within(select!).getAllByRole("option")[1];
      fireEvent.change(select!, {
        target: { value: option?.getAttribute("value") ?? "" },
      });
      expect(decodeURIComponent(location())).toMatch(/[?&]p\.[a-z_]+=/);
    });

    it("все варианты за кнопкой; вариант открывается в «Результате»", async () => {
      openMap();
      await screen.findByText(/Всего вариантов результата/);
      expect(screen.queryByRole("list", { name: /Все варианты/ })).toBeNull();
      fireEvent.click(
        screen.getByRole("button", { name: "Показать все варианты" }),
      );
      fireEvent.click(
        screen.getAllByRole("button", {
          name: "Показать результат",
        })[0]!,
      );
      expect(location()).toContain("/result");
    });

    it("слишком много вариантов: объяснение и выбор, что зафиксировать", async () => {
      openMap("too_many");
      expect(
        await screen.findByText("Слишком много вариантов"),
      ).toBeInTheDocument();
      expect(screen.getByText("Что зафиксировать")).toBeInTheDocument();
    });
  });

  describe("Сравнить", () => {
    it("`compare=1`: экран сравнения со стороны слева и справа, подписи без внутренних слов", async () => {
      open((client) => {
        seedCompare(client);
      }, `?${COMPARE_SEARCH}`);
      expect((await screen.findAllByText("Слева")).length).toBeGreaterThan(0);
      expect(screen.getAllByText("Справа").length).toBeGreaterThan(0);
      expect(
        screen.getByRole("heading", { name: "Сравнить с другой ситуацией" }),
      ).toBeInTheDocument();
      expect(screen.getByText("Два готовых случая")).toBeInTheDocument();
      expect(screen.queryByText("Два сценария")).toBeNull();
      expect(screen.queryByText(/Рабочее дерево/)).toBeNull();
    });

    it("подписи изменений словами: роли по-русски, сырые «участник supervisor» и «было: …» в технических подробностях (V1)", async () => {
      open((client) => {
        seedCompare(client);
      }, `?${COMPARE_SEARCH}`);
      await screen.findAllByText("Слева");
      const view = document.querySelector(".sp-ck");
      const clone = view?.cloneNode(true) as HTMLElement;
      for (const tech of clone.querySelectorAll("details")) tech.remove();
      expect(clone.textContent).not.toMatch(
        /участник [a-z]|[a-z]+_[a-z]+|было: [a-z]|шаг \d/,
      );
      expect(clone.textContent).toMatch(/Участник: Консультант/);
      expect(view?.textContent).toMatch(/Вид изменения/);
    });

    it("«К проверке» убирает сравнение и его стороны из адреса", async () => {
      open((client) => {
        seedCompare(client);
      }, `?${COMPARE_SEARCH}`);
      fireEvent.click(await screen.findByRole("link", { name: "К проверке" }));
      expect(location()).not.toMatch(/compare|left|right/);
    });
  });

  it("на телефоне части переключает полоса над заголовком", async () => {
    openLint();
    await screen.findByText(/Проверка шаблона/);
    // Левая колонка и полоса телефона: нужную показывает CSS по ширине экрана пространства.
    const bar = document.querySelector(".sp-ck-switch");
    expect(bar).not.toBeNull();
    const labels = [...(bar?.querySelectorAll("a") ?? [])].map(
      (link) => link.textContent,
    );
    expect(labels).toEqual([
      "Замечания",
      "Типовые случаи",
      "Что на что влияет",
      "Сравнить",
    ]);
    expect(bar?.querySelector("[aria-current]")?.textContent).toBe("Замечания");
  });
});
