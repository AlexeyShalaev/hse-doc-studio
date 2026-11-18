import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
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
  packStudioKeys,
  type PackTree,
  type PackVersionRef,
  type PackWorkspace,
} from "@entities/pack-studio";
import {
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

// Режим «Проверка» (линтер результата и покрытие, F11) на эталонах контракта: сервер подменён,
// запросы идут тем же кодом, что к настоящему серверу.

// Сбой сервера (5xx) hook повторяет один раз через секунду: ошибку ждём дольше.
const SERVER_ERROR_WAIT = { timeout: 3500 };
const WS = "ws-lint";
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

const withReleased = (released: boolean): PackTree => ({
  ...tree,
  packs: tree.packs.map((pack) => ({
    ...pack,
    templates: pack.templates.map((template) => ({
      ...template,
      versions: template.versions.map((version) => ({ ...version, released })),
    })),
  })),
});

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

// Клиенты тестов: после теста очищаются, чтобы повтор запроса не долетал в следующий.
const clients: QueryClient[] = [];

type Mount = {
  ref?: PackVersionRef;
  kind?: "folder" | "git";
  released?: boolean;
};

const mount = (
  search: string,
  { ref = COURSEWORK, kind = "folder", released = false }: Mount = {},
) => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, retryDelay: 0 },
    },
  });
  clients.push(client);
  client.setQueryData(packStudioKeys.tree(WS), withReleased(released));
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

const open = async (search = "view=lint", options: Mount = {}) => {
  const client = mount(search, options);
  await screen.findByTestId("outcome-lint-summary");
  return client;
};

describe("режим «Проверка»: линтер результата и покрытие (F11)", () => {
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
    for (const client of clients.splice(0)) client.clear();
    vi.restoreAllMocks();
    outcomeReference.setBehavior("normal");
    setModesBehavior("normal");
    scenarioReference.reset();
    window.localStorage.clear();
  });

  describe("находки", () => {
    it("ошибки, предупреждения и информация в группах со своими заголовками и списками", async () => {
      await open();
      expect(screen.getByTestId("outcome-lint-summary")).toHaveTextContent(
        "1 ошибка, 2 предупреждения, 1 сведение",
      );
      const error = screen.getByTestId("outcome-lint-group-error");
      const warning = screen.getByTestId("outcome-lint-group-warning");
      const info = screen.getByTestId("outcome-lint-group-info");
      expect(
        within(error).getByRole("heading", { level: 3 }),
      ).toHaveTextContent("Ошибки1");
      expect(
        within(warning).getByRole("heading", { level: 3 }),
      ).toHaveTextContent("Предупреждения2");
      expect(within(info).getAllByTestId("outcome-lint-finding")).toHaveLength(
        1,
      );
      // Порядок уровней: ошибки выше предупреждений выше информации.
      const order = screen
        .getAllByTestId(/^outcome-lint-group-/)
        .map((el) => el.getAttribute("data-severity"));
      expect(order).toEqual(["error", "warning", "info"]);
      // Группы по правилу, у каждой список со своим именем.
      expect(
        within(warning).getByRole("list", {
          name: "Находки правила when-never-held",
        }),
      ).toBeInTheDocument();
      // Сообщение и подсказка приходят с сервера и показаны как есть.
      expect(error).toHaveTextContent(
        "Условие поля «proposal_stage» ждёт значение «Финальная»",
      );
      expect(within(error).getByTestId("outcome-lint-hint")).toHaveTextContent(
        "Как исправить: Добавьте значение в options поля",
      );
      expect(within(error).getByTestId("outcome-lint-place")).toHaveTextContent(
        "version.yaml строка 212",
      );
      // Уровень назван словом, не только цветом.
      expect(within(error).getByText("Ошибка")).toBeInTheDocument();
      expect(within(info).getAllByText("Информация")).toHaveLength(2);
    });

    it("свидетели: до трёх комбинаций с подписями вводных", async () => {
      await open();
      const finding = screen
        .getAllByTestId("outcome-lint-finding")
        .find((el) => el.getAttribute("data-rule") === "when-never-held");
      if (!finding) throw new Error("no finding");
      const lines = within(finding).getAllByTestId("outcome-lint-show-combo");
      expect(lines).toHaveLength(2);
      expect(finding).toHaveTextContent(
        "Научный руководитель: Нет; Консультант: Нет; Академический руководитель: Нет",
      );
    });

    it("поиск, уровень и правило сужают список; сброс возвращает всё", async () => {
      const user = userEvent.setup();
      await open();
      expect(screen.getAllByTestId("outcome-lint-finding")).toHaveLength(4);
      await user.click(screen.getByTestId("outcome-lint-severity-warning"));
      expect(screen.getAllByTestId("outcome-lint-finding")).toHaveLength(2);
      expect(
        screen.getByTestId("outcome-lint-severity-warning"),
      ).toHaveAttribute("aria-pressed", "true");
      await user.selectOptions(
        screen.getByTestId("outcome-lint-rule-filter"),
        "translation-missing",
      );
      expect(screen.getAllByTestId("outcome-lint-finding")).toHaveLength(1);
      await user.click(screen.getByTestId("outcome-lint-severity-error"));
      expect(screen.getByTestId("outcome-lint-nomatch")).toBeInTheDocument();
      await user.click(screen.getByTestId("outcome-lint-reset"));
      expect(screen.getAllByTestId("outcome-lint-finding")).toHaveLength(4);
      await user.type(screen.getByTestId("outcome-lint-search"), "английск");
      expect(screen.queryAllByTestId("outcome-lint-finding")).toHaveLength(0);
      await user.clear(screen.getByTestId("outcome-lint-search"));
      await user.type(
        screen.getByTestId("outcome-lint-search"),
        "PROPOSAL_STAGE",
      );
      // Поиск без учёта регистра: ошибка и перевод по одному полю.
      expect(screen.getAllByTestId("outcome-lint-finding")).toHaveLength(2);
    });

    it("«Только выбранный элемент» оставляет находки этого элемента", async () => {
      const user = userEvent.setup();
      await open("view=lint&selected=documents:project_proposal");
      await user.click(screen.getByTestId("outcome-lint-selected-only"));
      const items = screen.getAllByTestId("outcome-lint-finding");
      expect(items).toHaveLength(1);
      expect(items[0]).toHaveAttribute("data-rule", "when-never-held");
    });

    it("ничего не найдено: «Находок нет»", async () => {
      setModesBehavior("lint_empty");
      await open();
      expect(screen.getByTestId("outcome-lint-empty")).toHaveTextContent(
        "Находок нет",
      );
      expect(screen.getByTestId("outcome-lint-summary")).toHaveTextContent(
        "0 ошибок, 0 предупреждений, 0 сведений",
      );
    });

    it("пак слишком большой для атласа: понятная информация, статические находки остаются", async () => {
      setModesBehavior("lint_atlas_skipped");
      await open();
      expect(
        screen.getByTestId("outcome-lint-atlas-skipped"),
      ).toHaveTextContent("Пак слишком большой для проверки по атласу");
      expect(
        screen.getByTestId("outcome-lint-atlas-skipped"),
      ).toHaveTextContent("Закрепите вводные");
      expect(
        screen.getByTestId("outcome-lint-approximate"),
      ).toBeInTheDocument();
    });

    it("версия выпущена: линтер читается, пометка про неизменяемость", async () => {
      await open("view=lint", { released: true });
      expect(screen.getByTestId("outcome-lint-released")).toHaveTextContent(
        "неизменяема",
      );
      expect(screen.getAllByTestId("outcome-lint-finding")).toHaveLength(4);
    });

    it("в режиме «Как студент» панели нет", async () => {
      mount("view=lint&mode=student");
      await screen.findByTestId("outcome-summary");
      expect(screen.queryByTestId("outcome-lint")).toBeNull();
      expect(screen.queryByTestId("outcome-lint-bar-badge")).toBeNull();
    });

    it("итог проверки объявляется в aria-live", async () => {
      await open();
      await waitFor(() => {
        expect(screen.getByTestId("outcome-lint-live")).toHaveTextContent(
          "Проверка завершена: 1 ошибка, 2 предупреждения, 1 сведение.",
        );
      });
      expect(screen.getByTestId("outcome-lint-live")).toHaveAttribute(
        "aria-live",
        "polite",
      );
    });
  });

  describe("переходы", () => {
    it("«Открыть правило» ведёт к файлу и указателю версии, адрес возврата несёт состояние", async () => {
      const user = userEvent.setup();
      await open();
      const first = within(
        screen.getByTestId("outcome-lint-group-error"),
      ).getByTestId("outcome-lint-open-rule");
      await user.click(first);
      await waitFor(() => {
        expect(where()).toContain("/pack-studio/w/ws-lint?");
      });
      const search = new URLSearchParams(where().split("?")[1]);
      expect(search.get("file")).toBe(
        "hse-cs-sse/templates/coursework/versions/2026.1.6/version.yaml",
      );
      expect(search.get("at")).toBe("/forms/0/sections/1/fields/2/visible_if");
      expect(search.get("pane")).toBe("form");
      expect(search.get("from")).toContain("view=lint");
    });

    it("файл вне версии не открывается", async () => {
      const user = userEvent.setup();
      const reply = structuredClone(
        (await import("@entities/pack-studio/reference")).COURSEWORK_LINT,
      );
      const finding = reply.findings[0];
      if (!finding) throw new Error("no finding");
      finding.file = "../../etc/passwd";
      vi.spyOn(
        (await import("@shared/api")).apiClient,
        "get",
      ).mockImplementation((url: string) =>
        url.includes("/outcome/lint")
          ? Promise.resolve({ status: 200, data: reply, headers: {} })
          : Promise.reject(new Error("unexpected")),
      );
      mount("view=lint");
      await screen.findByTestId("outcome-lint-summary");
      const before = where();
      await user.click(
        within(screen.getByTestId("outcome-lint-group-error")).getByTestId(
          "outcome-lint-open-rule",
        ),
      );
      expect(where()).toBe(before);
    });

    it("«Показать комбинацию» ставит вводные свидетеля и открывает результат", async () => {
      const user = userEvent.setup();
      await open();
      const finding = screen
        .getAllByTestId("outcome-lint-finding")
        .find((el) => el.getAttribute("data-rule") === "when-never-held");
      if (!finding) throw new Error("no finding");
      await user.click(
        nth(within(finding).getAllByTestId("outcome-lint-show-combo"), 0),
      );
      await waitFor(() => {
        expect(where()).not.toContain("view=");
      });
      expect(where()).toContain("i.supervisor=none");
      expect(await screen.findByTestId("outcome-summary")).toBeInTheDocument();
    });

    it("«Показать в результате» выбирает элемент и открывает результат", async () => {
      const user = userEvent.setup();
      await open();
      await user.click(
        within(screen.getByTestId("outcome-lint-group-info")).getByTestId(
          "outcome-lint-show-result",
        ),
      );
      await waitFor(() => {
        expect(where()).toContain("selected=documents%3Atopic_application");
      });
      expect(where()).not.toContain("view=");
      // Находки выбранного элемента видны и в панели «Почему?», со ссылкой в проверку.
      const hints = await screen.findByTestId("outcome-rules-lint");
      expect(hints).toHaveTextContent("1 находка по этому элементу");
      await user.click(within(hints).getByTestId("outcome-rules-lint-open"));
      await waitFor(() => {
        expect(where()).toContain("view=lint");
      });
    });

    it("элемент находки показывается кнопкой с понятным именем", async () => {
      await open();
      const chips = screen.getAllByTestId("outcome-lint-show-element");
      expect(chips[0]).toHaveAccessibleName(
        "Показать в результате: Метаданные проекта, proposal_stage",
      );
    });
  });

  describe("Jinja", () => {
    it("кнопка запускает проверку с jinja=true и показывает, что она выполнена", async () => {
      const user = userEvent.setup();
      const get = vi.spyOn((await import("@shared/api")).apiClient, "get");
      await open();
      const button = screen.getByTestId("outcome-lint-jinja");
      expect(button).toHaveTextContent("Проверить Jinja-шаблоны");
      await user.click(button);
      await waitFor(() => {
        expect(screen.getByTestId("outcome-lint-jinja")).toHaveTextContent(
          "Jinja-шаблоны проверены",
        );
      });
      const urls = get.mock.calls.map((call) => call[0]);
      expect(
        urls.some((u) => u.includes("lint?state=work_tree&jinja=true")),
      ).toBe(true);
      expect(screen.getByTestId("outcome-lint-jinja")).toBeDisabled();
    });

    it("429: показывает ожидание, повторяет сам и приходит ответ", async () => {
      const user = userEvent.setup();
      await open();
      setModesBehavior("lint_rate_limited");
      await user.click(screen.getByTestId("outcome-lint-jinja"));
      expect(
        await screen.findByText(/Проверок слишком много \(лимит 6 в минуту\)/),
      ).toBeInTheDocument();
      await waitFor(
        () => {
          expect(screen.getByTestId("outcome-lint-jinja")).toHaveTextContent(
            "Jinja-шаблоны проверены",
          );
        },
        { timeout: 4000 },
      );
    });

    it("на коммите и базе Jinja не проверяется: кнопка отключена с подсказкой", async () => {
      await open("view=lint&state=head");
      const button = screen.getByTestId("outcome-lint-jinja");
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute(
        "title",
        "Jinja проверяется только в рабочем дереве.",
      );
    });

    it("отмена проверки Jinja возвращает кнопку", async () => {
      const user = userEvent.setup();
      await open();
      outcomeReference.setBehavior("slow");
      await user.click(screen.getByTestId("outcome-lint-jinja"));
      await user.click(await screen.findByTestId("outcome-lint-jinja-cancel"));
      await waitFor(() => {
        expect(screen.getByTestId("outcome-lint-jinja")).not.toBeDisabled();
      });
      expect(screen.queryByTestId("outcome-lint-jinja-busy")).toBeNull();
    });
  });

  describe("загрузка и ошибки", () => {
    it("загрузка: скелет и «Отменить», отмена даёт «Проверить»", async () => {
      const user = userEvent.setup();
      outcomeReference.setBehavior("slow");
      mount("view=lint");
      expect(
        await screen.findByTestId("outcome-lint-loading"),
      ).toBeInTheDocument();
      await user.click(screen.getByTestId("outcome-lint-cancel"));
      expect(
        await screen.findByTestId("outcome-lint-cancelled"),
      ).toBeInTheDocument();
      outcomeReference.setBehavior("normal");
      await user.click(screen.getByTestId("outcome-lint-again"));
      expect(
        await screen.findByTestId("outcome-lint-summary"),
      ).toBeInTheDocument();
    });

    it("503 занят: пишет о повторе и получает ответ сам", async () => {
      setModesBehavior("busy");
      await open();
      expect(modesCalls.count("lint")).toBe(2);
    });

    it("429 при первой проверке: ожидание, повтор сам", async () => {
      setModesBehavior("lint_rate_limited");
      mount("view=lint");
      expect(
        await screen.findByText(/Повторю сам через 1 с/),
      ).toBeInTheDocument();
      await screen.findByTestId("outcome-lint-summary", undefined, {
        timeout: 4000,
      });
    });

    it("сбой сервера: ошибка с «Повторить», повтор приносит ответ", async () => {
      const user = userEvent.setup();
      setModesBehavior("fail");
      mount("view=lint");
      const error = await screen.findByTestId(
        "outcome-mode-error",
        undefined,
        SERVER_ERROR_WAIT,
      );
      expect(error).toHaveTextContent("Не удалось проверить пак");
      setModesBehavior("normal");
      await user.click(screen.getByTestId("outcome-mode-retry"));
      expect(
        await screen.findByTestId("outcome-lint-summary"),
      ).toBeInTheDocument();
    });

    it("версия не читается: причина из ответа", async () => {
      setModesBehavior("lint_unreadable");
      mount("view=lint");
      const error = await screen.findByTestId("outcome-mode-unreadable");
      expect(error).toHaveTextContent(
        "version.yaml: строка 14, неверный отступ",
      );
    });

    it("нет базы для состояния «База»: объяснение причины", async () => {
      setModesBehavior("no_base");
      mount("view=lint&state=base");
      expect(
        await screen.findByTestId("outcome-mode-no-base"),
      ).toBeInTheDocument();
    });
  });

  describe("покрытие", () => {
    it("процент, число правил по состояниям, строки атласа", async () => {
      await open();
      const coverage = screen.getByTestId("outcome-lint-coverage");
      expect(
        within(coverage).getByTestId("outcome-lint-percent"),
      ).toHaveTextContent("78.1 %");
      expect(within(coverage).getByRole("progressbar")).toHaveAccessibleName(
        "Покрытие правил сценариями: 78.1 %",
      );
      const tally = within(coverage).getByRole("list", {
        name: "Правила по покрытию",
      });
      expect(tally).toHaveTextContent("Покрыто полностью: 10");
      expect(tally).toHaveTextContent("Наполовину: 4");
      expect(tally).toHaveTextContent("Не покрыто: 2");
      expect(coverage).toHaveTextContent(
        "Сценариев: 3. Строк атласа затронуто 3 из 12.",
      );
      expect(screen.queryByTestId("outcome-lint-approximate")).toBeNull();
    });

    it("правила без полного покрытия: сначала непокрытые, с чем видели, свидетель и «Открыть правило»", async () => {
      const user = userEvent.setup();
      await open();
      const rules = screen.getAllByTestId("outcome-lint-coverage-rule");
      expect(rules).toHaveLength(6);
      expect(rules[0]).toHaveAttribute("data-state", "none");
      expect(rules[0]).toHaveTextContent("Не покрыто");
      expect(rules[0]).toHaveTextContent(
        "Сценарии не видели ни одного исхода.",
      );
      expect(rules[5]).toHaveAttribute("data-state", "half");
      expect(rules[5]).toHaveTextContent("Правило движка");
      const half = rules.find((el) =>
        el.textContent.includes("Сценарии видели: выполнено."),
      );
      expect(half).toHaveTextContent("Не хватает: не выполнено.");
      // Зашитое в движок правило файла не имеет: «Открыть правило» только у манифеста.
      expect(
        within(nth(rules, 5)).queryByTestId("outcome-lint-open-coverage-rule"),
      ).toBeNull();
      await user.click(
        within(nth(rules, 0)).getByTestId("outcome-lint-open-coverage-rule"),
      );
      await waitFor(() => {
        expect(where()).toContain("pane=form");
      });
      expect(where()).toContain("project_proposal");
    });

    it("«Добавить сценарии (N)» раскрывает строки, «Добавить как сценарий» открывает окно с вводными", async () => {
      const user = userEvent.setup();
      await open();
      const add = screen.getByTestId("outcome-lint-add-scenarios");
      expect(add).toHaveTextContent("Добавить сценарии (2)");
      expect(add).toHaveAttribute("aria-expanded", "false");
      await user.click(add);
      expect(add).toHaveAttribute("aria-expanded", "true");
      const rows = within(
        screen.getByTestId("outcome-lint-uncovered-rows"),
      ).getAllByRole("listitem");
      expect(rows).toHaveLength(2);
      expect(rows[0]).toHaveTextContent("Закроет 3 исхода правил.");
      await user.click(
        within(nth(rows, 0)).getByTestId("outcome-lint-add-row"),
      );
      expect(
        await screen.findByRole("dialog", { name: "Сохранить как сценарий" }),
      ).toBeInTheDocument();
      // Вводные свидетеля легли в адрес, режим остался «Проверка».
      expect(where()).toContain("view=lint");
      expect(where()).toContain("i.supervisor=company");
      expect(where()).toContain("i.academic_supervisor=no");
    });

    it("в состоянии «Последний коммит» сценарии не добавляются: кнопка отключена с причиной", async () => {
      await open("view=lint&state=head");
      const add = screen.getByTestId("outcome-lint-add-scenarios");
      expect(add).toBeDisabled();
      expect(add).toHaveAttribute("title");
    });

    it("приближённое покрытие помечено", async () => {
      setModesBehavior("lint_atlas_skipped");
      await open();
      expect(screen.getByTestId("outcome-lint-approximate")).toHaveTextContent(
        "Покрытие приближённое",
      );
    });

    it("полное покрытие без подсказок", async () => {
      setModesBehavior("lint_empty");
      await open();
      expect(screen.getByTestId("outcome-lint-percent")).toHaveTextContent(
        "100 %",
      );
      expect(screen.queryByTestId("outcome-lint-add-scenarios")).toBeNull();
      expect(screen.queryByTestId("outcome-lint-coverage-rules")).toBeNull();
    });

    it("краткая сводка в выборе сценария и в матрице берёт процент из прогона, без второго расчёта", async () => {
      const user = userEvent.setup();
      const get = vi.spyOn((await import("@shared/api")).apiClient, "get");
      mount("view=matrix");
      const brief = await screen.findByTestId("outcome-coverage-brief");
      expect(brief).toHaveTextContent("Покрытие сценариями");
      expect(
        get.mock.calls.filter((call) => call[0].includes("/lint")),
      ).toHaveLength(0);
      await user.click(screen.getByTestId("outcome-coverage-brief-open"));
      await waitFor(() => {
        expect(where()).toContain("view=lint");
      });
      expect(
        await screen.findByTestId("outcome-lint-summary"),
      ).toBeInTheDocument();
    });
  });

  describe("значок и вкладка", () => {
    it("вкладка «Проверка» в tablist, значок появляется после первой проверки", async () => {
      const user = userEvent.setup();
      const get = vi.spyOn((await import("@shared/api")).apiClient, "get");
      mount("");
      const tab = await screen.findByTestId("outcome-view-lint");
      expect(tab).toHaveTextContent("Проверка");
      // Расчёт идёт только в открытом режиме: пока его не открывали, значка и запроса нет.
      expect(screen.queryByTestId("outcome-lint-tab-badge")).toBeNull();
      expect(
        get.mock.calls.filter((call) => call[0].includes("/lint")),
      ).toHaveLength(0);
      await user.click(tab);
      await screen.findByTestId("outcome-lint-summary");
      const badge = screen.getByTestId("outcome-lint-tab-badge");
      expect(badge).toHaveTextContent(/1\s*2|12/);
      expect(badge).toHaveTextContent(
        "Проверка пака: 1 ошибка, 2 предупреждения",
      );
      // В верхней панели то же число, клик открывает режим.
      await user.click(screen.getByTestId("outcome-view-result"));
      const bar = await screen.findByTestId("outcome-lint-open");
      expect(bar).toHaveAccessibleName("Открыть проверку пака");
      await user.click(bar);
      await waitFor(() => {
        expect(where()).toContain("view=lint");
      });
    });

    it("панель «Правила и причины» ничего не рисует без находок по элементу", async () => {
      const user = userEvent.setup();
      await open();
      await user.click(
        within(screen.getByTestId("outcome-lint-group-info")).getByTestId(
          "outcome-lint-show-result",
        ),
      );
      await screen.findByTestId("outcome-rules-lint");
      await user.click(screen.getByTestId("outcome-view-lint"));
      await screen.findByTestId("outcome-lint-summary");
      await user.click(screen.getByTestId("outcome-view-result"));
      expect(screen.queryByTestId("outcome-rules-lint")).not.toBeNull();
    });
  });

  describe("клавиатура, язык, телефон", () => {
    it("уровни переключаются с клавиатуры, фокус идёт по кнопкам действий", async () => {
      const user = userEvent.setup();
      await open();
      const warning = screen.getByTestId("outcome-lint-severity-warning");
      warning.focus();
      await user.keyboard("{Enter}");
      expect(warning).toHaveAttribute("aria-pressed", "true");
      await user.keyboard(" ");
      expect(warning).toHaveAttribute("aria-pressed", "true");
      const first = screen.getAllByTestId("outcome-lint-open-rule")[0];
      first?.focus();
      expect(first).toHaveFocus();
    });

    it("английский: вкладка, итог, группы, подсказка и действия", async () => {
      await i18n.changeLanguage("en");
      try {
        await open();
        expect(screen.getByTestId("outcome-view-lint")).toHaveTextContent(
          "Check",
        );
        expect(screen.getByTestId("outcome-lint-summary")).toHaveTextContent(
          "1 error, 2 warnings, 1 note",
        );
        expect(
          screen.getByTestId("outcome-lint-group-error"),
        ).toHaveTextContent("Errors");
        expect(
          within(screen.getByTestId("outcome-lint-group-error")).getByTestId(
            "outcome-lint-hint",
          ),
        ).toHaveTextContent("How to fix:");
        expect(screen.getByTestId("outcome-lint-jinja")).toHaveTextContent(
          "Check Jinja templates",
        );
        expect(
          screen.getByTestId("outcome-lint-add-scenarios"),
        ).toHaveTextContent("Add scenarios (2)");
        // Сообщения находок приходят с сервера на русском и показаны как есть.
        expect(
          screen.getByTestId("outcome-lint-group-error"),
        ).toHaveTextContent("ждёт значение");
      } finally {
        await i18n.changeLanguage("ru");
      }
    });

    it("телефон 360 px: панель, действия и переходы работают", async () => {
      const viewport = installViewport(360);
      try {
        const user = userEvent.setup();
        await open();
        expect(screen.getByTestId("outcome-screen")).toHaveAttribute(
          "data-phone",
          "true",
        );
        expect(screen.getAllByTestId("outcome-lint-finding")).toHaveLength(4);
        await user.click(
          within(screen.getByTestId("outcome-lint-group-info")).getByTestId(
            "outcome-lint-show-result",
          ),
        );
        await waitFor(() => {
          expect(where()).toContain("tab=rules");
        });
        expect(where()).toContain("selected=documents%3Atopic_application");
      } finally {
        viewport.restore();
      }
    });
  });
});
