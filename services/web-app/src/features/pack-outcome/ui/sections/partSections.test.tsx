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
  type OutcomeBranch,
  type OutcomeCheckRule,
  type PackGit,
  type PackOutcome,
  type PackOutcomeRequest,
} from "@entities/pack-studio";
import {
  VKR_BRANCHES,
  VKR_CHECKS,
  VKR_INPUTS,
  VKR_OUTCOME,
} from "@entities/pack-studio/reference";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { useOutcomeUrlState } from "../../lib/urlState";
import { OutcomeModelContext, type OutcomeModel } from "../../model";
import { BranchesSection } from "./BranchesSection";
import { ChecksSection } from "./ChecksSection";

// Секции F5 на эталонах: правила проверок и ветки приходят отдельными запросами `include`, и
// только когда раздел раскрыт. Запрос подменён шпионом на `packOutcomeApi.outcome`, поэтому
// видно, что именно и когда просили.

const Probe = () => {
  const { search } = useLocation();
  return <output data-testid="search">{search}</output>;
};

type Options = {
  workspaceKind?: "git" | "folder";
  git?: PackGit;
  outcome?: PackOutcome;
};

const Harness = ({
  workspaceKind = "folder",
  git,
  outcome = VKR_OUTCOME,
}: Options) => {
  const url = useOutcomeUrlState();
  const request: PackOutcomeRequest = {
    state: url.state.state,
    scenario: url.state.scenario,
    inputs: url.state.inputs,
  };
  const model = {
    workspaceId: "w",
    ref: { pack: "p", template: "t", version: "v" },
    released: false,
    phone: false,
    url,
    request,
    shown: outcome,
    stale: false,
    inputs: { data: VKR_INPUTS },
    select: (el: { section: string; id: string } | null) => {
      const same =
        el !== null &&
        url.state.selected?.section === el.section &&
        url.state.selected.id === el.id;
      url.update({ selected: same ? null : (el as never) });
    },
    reveal: (el: { section: string; id: string }) => {
      url.update({ selected: el as never });
    },
    workspaceKind,
    git,
  } as unknown as OutcomeModel;
  return (
    <OutcomeModelContext.Provider value={model}>
      <ChecksSection />
      <BranchesSection />
      <button
        type="button"
        data-testid="change-inputs"
        onClick={() => {
          url.update({ inputs: { kind: "research" } });
        }}
      />
      <Probe />
    </OutcomeModelContext.Provider>
  );
};

const mount = (search = "", options: Options = {}) => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, staleTime: Infinity },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/${search ? `?${search}` : ""}`]}>
        <Harness {...options} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

type Parts = {
  checks?: OutcomeCheckRule[] | null;
  branches?: OutcomeBranch[] | null;
};

/** Ответ сервера: правила и ветки только если о них просили (`include`). */
const answer = (body: PackOutcomeRequest, parts: Parts): PackOutcome => {
  const include = body.include ?? [];
  return {
    ...VKR_OUTCOME,
    checks: include.includes("checks")
      ? (parts.checks ?? structuredClone(VKR_CHECKS))
      : null,
    branches: include.includes("branches")
      ? (parts.branches ?? structuredClone(VKR_BRANCHES))
      : null,
  };
};

const serve = (parts: Parts = {}) =>
  vi
    .spyOn(packOutcomeApi, "outcome")
    .mockImplementation((_id, _ref, body) =>
      Promise.resolve(answer(body, parts)),
    );

const includes = (spy: ReturnType<typeof serve>) =>
  spy.mock.calls.map(([, , body]) => body.include ?? []);

const open = async (name: "checks" | "branches") => {
  fireEvent.click(
    within(screen.getByTestId(`outcome-section-${name}`)).getByRole("button", {
      name: new RegExp(name === "checks" ? "Проверки" : "Ветки и варианты"),
    }),
  );
  await waitFor(() => {
    expect(screen.getByTestId(`outcome-${name}`)).toBeInTheDocument();
  });
};

const enabledRules = VKR_CHECKS.filter((r) => r.enabled);

describe("секции F5: проверки, ветки и варианты", () => {
  beforeAll(async () => {
    await loadPackOutcomeNamespace();
  });
  beforeEach(async () => {
    window.localStorage.clear();
    await i18n.changeLanguage("ru");
  });
  afterEach(async () => {
    cleanup();
    vi.restoreAllMocks();
    await i18n.changeLanguage("ru");
  });

  describe("ленивый запрос include", () => {
    it("свёрнутые разделы ничего не просят у сервера", () => {
      const spy = serve();
      mount();
      expect(spy).not.toHaveBeenCalled();
      expect(screen.getByTestId("outcome-count-checks")).toHaveTextContent(
        "Загружается при раскрытии",
      );
      expect(screen.getByTestId("outcome-count-branches")).toHaveTextContent(
        "Загружается при раскрытии",
      );
    });

    it("раскрытие просит только свою часть, повторное раскрытие берёт из кэша", async () => {
      const spy = serve();
      mount();
      await open("checks");
      expect(includes(spy)).toEqual([["checks"]]);
      const toggle = within(screen.getByTestId("outcome-section-checks"))
        .getAllByRole("button")
        .at(0);
      if (!toggle) throw new Error("no toggle");
      fireEvent.click(toggle);
      fireEvent.click(toggle);
      await open("branches");
      expect(includes(spy)).toEqual([["checks"], ["branches"]]);
    });

    it("запрос повторяет вводные экрана и состояние", async () => {
      const spy = serve();
      mount("state=head&i.kind=research");
      await open("checks");
      expect(spy.mock.calls[0]?.[2]).toMatchObject({
        state: "head",
        inputs: { kind: "research" },
        include: ["checks"],
      });
    });

    it("раздел с выбранным по ссылке элементом раскрыт сразу", async () => {
      const spy = serve();
      mount("selected=checks:gost-7.32-2017/line-spacing");
      await waitFor(() => {
        expect(screen.getByTestId("outcome-checks")).toBeInTheDocument();
      });
      expect(includes(spy)).toEqual([["checks"]]);
      expect(
        screen.getByTestId("outcome-check-gost-7.32-2017/line-spacing")
          .parentElement,
      ).toBeTruthy();
      expect(
        within(screen.getByTestId("outcome-section-branches")).getByRole(
          "button",
          { name: /Ветки и варианты/ },
        ),
      ).toHaveAttribute("aria-expanded", "false");
    });
  });

  describe("проверки", () => {
    it("счётчик в заголовке, плашка про границы расчёта и счётчики", async () => {
      serve();
      mount("selected=checks:gost-7.32-2017/line-spacing");
      await screen.findByTestId("outcome-checks");
      expect(screen.getByTestId("outcome-count-checks")).toHaveTextContent(
        `применимо ${String(enabledRules.length)} из ${String(VKR_CHECKS.length)}`,
      );
      const scope = screen.getByTestId("outcome-checks-scope");
      expect(scope).toHaveTextContent("Здесь только применимость правил");
      expect(scope).toHaveTextContent("Результат проверок (находки)");
      expect(scope).toHaveTextContent("видны в предпросмотре");
      expect(scope).toHaveTextContent("проверки на Python");
      expect(scope).toHaveTextContent("места подписей");
      expect(
        screen.getByTestId("outcome-checks-stats-enabled"),
      ).toHaveTextContent(String(enabledRules.length));
      expect(screen.getByTestId("outcome-checks-stats-off")).toHaveTextContent(
        "4",
      );
      expect(
        screen.getByTestId("outcome-checks-stats-python"),
      ).toHaveTextContent(
        String(enabledRules.filter((r) => r.engine === "python").length),
      );
    });

    it("группы по документу и слою, значок движка и серьёзность", async () => {
      serve();
      mount("selected=checks:gost-7.32-2017/line-spacing");
      await screen.findByTestId("outcome-checks");
      const thesis = screen.getByTestId("outcome-checks-doc-thesis");
      expect(thesis).toHaveTextContent("Выпускная квалификационная работа");
      expect(
        within(thesis).getByTestId(
          "outcome-checks-layer-thesis-gost-7.32-2017",
        ),
      ).toBeInTheDocument();
      expect(
        within(thesis).getByTestId("outcome-checks-layer-thesis-typography-ru"),
      ).toBeInTheDocument();
      const line = within(thesis).getByTestId(
        "outcome-check-gost-7.32-2017/line-spacing",
      );
      expect(line).toHaveTextContent("Межстрочный интервал 1.5");
      expect(line).toHaveTextContent("Предупреждение");
      expect(
        within(line).getByTestId(
          "outcome-check-gost-7.32-2017/line-spacing-engine",
        ),
      ).toHaveAttribute("data-engine", "structural");
      const intro = within(thesis).getByTestId(
        "outcome-check-gost-7.32-2017/section-introduction",
      );
      expect(intro).toHaveTextContent("Ошибка");
      // Правило с двумя документами стоит в группе каждого.
      const placeholders = screen.getAllByTestId(
        "outcome-check-hse-cs-se-vkr/spec-placeholders",
      );
      expect(placeholders).toHaveLength(2);
      expect(
        within(
          screen.getByTestId("outcome-checks-doc-technical_specification"),
        ).getByTestId("outcome-check-hse-cs-se-vkr/spec-placeholders"),
      ).toBeInTheDocument();
    });

    it("выключенные правила в свёрнутом блоке с причиной", async () => {
      serve();
      mount("selected=checks:gost-7.32-2017/line-spacing");
      await screen.findByTestId("outcome-checks");
      const toggle = screen.getByTestId("outcome-checks-off-toggle");
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(
        screen.queryByTestId("outcome-check-typography-ru/ellipsis"),
      ).toBeNull();
      fireEvent.click(toggle);
      const ellipsis = screen.getByTestId(
        "outcome-check-typography-ru/ellipsis",
      );
      expect(ellipsis).toHaveTextContent("выключена категория «formatting»");
      expect(ellipsis.closest("[data-muted]")).toHaveAttribute(
        "data-muted",
        "true",
      );
      expect(
        screen.getByTestId("outcome-check-gost-7.32-2017/figure-numbering"),
      ).toHaveTextContent("правило выключено в настройках проверок");
      expect(
        screen.getByTestId("outcome-check-hse-cs-se-vkr/annotation-length"),
      ).toHaveTextContent("нет документа в комплекте (Аннотация");
      expect(
        screen.getByTestId("outcome-checks-off-no_active_document"),
      ).toBeInTheDocument();
    });

    it("фильтры по серьёзности и движку, поиск, пустая выдача и сброс", async () => {
      serve();
      mount("selected=checks:gost-7.32-2017/line-spacing");
      await screen.findByTestId("outcome-checks");
      fireEvent.change(screen.getByTestId("outcome-checks-severity"), {
        target: { value: "err" },
      });
      expect(
        screen.getByTestId("outcome-check-gost-7.32-2017/section-introduction"),
      ).toBeInTheDocument();
      expect(
        screen.queryByTestId("outcome-check-gost-7.32-2017/line-spacing"),
      ).toBeNull();
      fireEvent.change(screen.getByTestId("outcome-checks-severity"), {
        target: { value: "all" },
      });
      fireEvent.change(screen.getByTestId("outcome-checks-engine"), {
        target: { value: "python" },
      });
      expect(
        screen.getByTestId("outcome-check-gost-7.32-2017/list-style"),
      ).toBeInTheDocument();
      expect(
        screen.queryByTestId("outcome-check-gost-7.32-2017/page-margins"),
      ).toBeNull();
      fireEvent.change(screen.getByTestId("outcome-checks-engine"), {
        target: { value: "all" },
      });
      const search = screen.getByTestId("outcome-checks-filter-search");
      // Поиск раскрывает блок выключенных, если там есть совпадение.
      fireEvent.change(search, { target: { value: "многоточие" } });
      expect(
        screen.getByTestId("outcome-check-typography-ru/ellipsis"),
      ).toBeInTheDocument();
      expect(screen.getByTestId("outcome-checks-off-toggle")).toHaveAttribute(
        "aria-expanded",
        "true",
      );
      fireEvent.change(search, { target: { value: "нет такого правила" } });
      const none = screen.getByTestId("outcome-checks-noresults");
      fireEvent.click(within(none).getByRole("button"));
      expect(search).toHaveValue("");
      expect(
        screen.getByTestId("outcome-check-gost-7.32-2017/line-spacing"),
      ).toBeInTheDocument();
    });

    it("выбор пишет checks:<id> в адрес, повторный клик снимает, стрелки двигают фокус", async () => {
      serve();
      mount("selected=checks:gost-7.32-2017/line-spacing");
      await screen.findByTestId("outcome-checks");
      const second = within(
        screen.getByTestId("outcome-check-gost-7.32-2017/page-margins"),
      ).getByRole("button");
      fireEvent.click(second);
      expect(screen.getByTestId("search").textContent).toContain(
        "selected=checks%3Agost-7.32-2017%2Fpage-margins",
      );
      expect(second).toHaveAttribute("aria-pressed", "true");
      fireEvent.click(second);
      expect(screen.getByTestId("search").textContent).not.toContain(
        "selected",
      );
      second.focus();
      fireEvent.keyDown(second, { key: "ArrowDown" });
      expect(document.activeElement).toBe(
        within(
          screen.getByTestId("outcome-check-gost-7.32-2017/line-spacing"),
        ).getByRole("button"),
      );
      fireEvent.keyDown(document.activeElement ?? second, { key: "ArrowUp" });
      expect(document.activeElement).toBe(second);
    });

    it("пересчёт: прежние правила на месте, статус объявляется", async () => {
      let resolve: (value: PackOutcome) => void = () => undefined;
      const spy = vi.spyOn(packOutcomeApi, "outcome");
      spy.mockImplementationOnce((_id, _ref, body) =>
        Promise.resolve(answer(body, {})),
      );
      spy.mockImplementationOnce(
        () =>
          new Promise<PackOutcome>((done) => {
            resolve = done;
          }),
      );
      mount("selected=checks:gost-7.32-2017/line-spacing");
      await screen.findByTestId("outcome-checks");
      fireEvent.click(screen.getByTestId("change-inputs"));
      await waitFor(() => {
        expect(
          screen.getByTestId("outcome-checks-refreshing"),
        ).toHaveTextContent("Считаю");
      });
      expect(
        screen.getByTestId("outcome-check-gost-7.32-2017/line-spacing"),
      ).toBeInTheDocument();
      expect(screen.getByTestId("outcome-checks")).toHaveAttribute(
        "data-stale",
        "true",
      );
      expect(screen.getByTestId("outcome-checks-refreshing")).toHaveAttribute(
        "aria-live",
        "polite",
      );
      await act(async () => {
        resolve(answer({ include: ["checks"] }, {}));
        await Promise.resolve();
      });
      await waitFor(() => {
        expect(
          screen.getByTestId("outcome-checks-refreshing"),
        ).toBeEmptyDOMElement();
      });
      expect(screen.getByTestId("outcome-checks")).not.toHaveAttribute(
        "data-stale",
      );
    });

    it("загрузка: скелет, потом правила", async () => {
      let resolve: (value: PackOutcome) => void = () => undefined;
      vi.spyOn(packOutcomeApi, "outcome").mockImplementation(
        () =>
          new Promise<PackOutcome>((done) => {
            resolve = done;
          }),
      );
      mount("selected=checks:gost-7.32-2017/line-spacing");
      expect(
        await screen.findByTestId("outcome-checks-skeleton"),
      ).toBeInTheDocument();
      await act(async () => {
        resolve(answer({ include: ["checks"] }, {}));
        await Promise.resolve();
      });
      await screen.findByTestId("outcome-checks");
      expect(screen.queryByTestId("outcome-checks-skeleton")).toBeNull();
    });

    it("ошибка: плашка с повтором, повтор приносит правила", async () => {
      const spy = vi.spyOn(packOutcomeApi, "outcome");
      spy.mockRejectedValueOnce(
        new ApiError("Сбой", "version_unreadable", 422),
      );
      spy.mockImplementation((_id, _ref, body) =>
        Promise.resolve(answer(body, {})),
      );
      mount("selected=checks:gost-7.32-2017/line-spacing");
      const error = await screen.findByTestId("outcome-checks-error");
      expect(error).toHaveAttribute("role", "alert");
      expect(error).toHaveTextContent("Не удалось получить раздел «Проверки»");
      fireEvent.click(screen.getByTestId("outcome-checks-retry"));
      await screen.findByTestId("outcome-checks");
      expect(screen.queryByTestId("outcome-checks-error")).toBeNull();
    });

    it("пусто: нет правил, сервер не вернул часть, ничего не применимо", async () => {
      serve({ checks: [] });
      const first = mount("selected=checks:x");
      expect(
        await screen.findByTestId("outcome-checks-empty"),
      ).toHaveTextContent("В версии нет правил проверок");
      first.unmount();
      vi.restoreAllMocks();
      vi.spyOn(packOutcomeApi, "outcome").mockResolvedValue({
        ...VKR_OUTCOME,
        checks: null,
      });
      mount("selected=checks:x");
      expect(
        await screen.findByTestId("outcome-checks-unavailable"),
      ).toBeInTheDocument();
      cleanup();
      vi.restoreAllMocks();
      serve({ checks: VKR_CHECKS.filter((r) => !r.enabled) });
      mount("selected=checks:x");
      expect(
        await screen.findByTestId("outcome-checks-none"),
      ).toHaveTextContent("Ни одно правило не применимо");
      expect(
        screen.getByTestId("outcome-checks-off-toggle"),
      ).toBeInTheDocument();
    });

    it("в плашке только то, что не входит по ответу сервера", async () => {
      serve();
      mount("selected=checks:gost-7.32-2017/line-spacing", {
        outcome: { ...VKR_OUTCOME, out_of_scope: ["tex_content"] },
      });
      await screen.findByTestId("outcome-checks");
      const scope = screen.getByTestId("outcome-checks-scope");
      expect(scope).not.toHaveTextContent("места подписей");
      expect(scope).not.toHaveTextContent("Не считаются здесь");
    });

    it("английский словарь", async () => {
      await i18n.changeLanguage("en");
      serve();
      mount("selected=checks:gost-7.32-2017/line-spacing");
      await screen.findByTestId("outcome-checks");
      expect(screen.getByTestId("outcome-count-checks")).toHaveTextContent(
        `${String(enabledRules.length)} of ${String(VKR_CHECKS.length)} apply`,
      );
      expect(screen.getByTestId("outcome-checks-scope")).toHaveTextContent(
        "Only which rules apply, not their results",
      );
      expect(
        screen.getByTestId("outcome-check-gost-7.32-2017/line-spacing"),
      ).toHaveTextContent("Line spacing 1.5");
      expect(screen.getByTestId("outcome-checks")).not.toHaveTextContent(
        /\b(checks|branches)\.[a-z]/,
      );
    });
  });

  describe("ветки и варианты", () => {
    const expanded = async (search = "", options: Options = {}) => {
      const spy = serve();
      mount(`selected=branches:staffing${search ? `&${search}` : ""}`, options);
      await screen.findByTestId("outcome-branch-staffing");
      return spy;
    };

    it("раскрытие просит include=branches, в заголовке число вводных", async () => {
      const spy = await expanded();
      expect(includes(spy)).toEqual([["branches"]]);
      expect(screen.getByTestId("outcome-count-branches")).toHaveTextContent(
        String(VKR_BRANCHES.length),
      );
    });

    it("варианты: выбранный, недоступный по языку и переход «Показать»", async () => {
      await expanded();
      const spec = screen.getByTestId(
        "outcome-variants-technical_specification",
      );
      expect(spec).toHaveTextContent("Техническое задание");
      expect(
        within(spec).getByTestId(
          "outcome-variants-technical_specification-espd",
        ),
      ).toHaveAttribute("data-chosen", "true");
      const off = within(spec).getByTestId(
        "outcome-variants-technical_specification-srs-29148",
      );
      expect(off).toHaveAttribute("data-available", "false");
      expect(off).toHaveTextContent("только en");
      // Вводной `variant.technical_specification` нет: кнопки нет.
      expect(
        within(spec).queryByRole("button", { name: /Показать результат/ }),
      ).toBeNull();

      const presentation = screen.getByTestId("outcome-variants-presentation");
      expect(presentation).toHaveTextContent("PowerPoint-шаблон");
      const show = within(presentation).getByTestId(
        "outcome-variants-presentation-show-reveal",
      );
      expect(show).toHaveAccessibleName(
        "Показать результат с вариантом «RevealJS (HTML)» у документа «Презентация защиты»",
      );
      fireEvent.click(show);
      expect(screen.getByTestId("search").textContent).toContain(
        "i.variant.presentation=reveal",
      );
    });

    it("откат языка: документ без редакции на язык проекта и пустое состояние", async () => {
      const withFallback = structuredClone(VKR_OUTCOME);
      for (const doc of withFallback.documents) {
        if (doc.id === "source_listing") doc.lang_state = "fallback";
      }
      await expanded("", { outcome: withFallback });
      const fallback = screen.getByTestId("outcome-fallback-source_listing");
      expect(fallback).toHaveTextContent(
        "Нет редакции на ru: берётся язык по умолчанию",
      );
      expect(screen.getByTestId("outcome-branches-lang")).toHaveTextContent(
        "Язык проекта: ru",
      );
      cleanup();
      const clean = structuredClone(VKR_OUTCOME);
      for (const doc of clean.documents) doc.lang_state = "native";
      serve();
      mount("selected=branches:staffing", { outcome: clean });
      await screen.findByTestId("outcome-branch-staffing");
      expect(screen.getByTestId("outcome-fallback-empty")).toBeInTheDocument();
    });

    it("ветка вводной: текущее значение, дельты по разделам словами и значками", async () => {
      await expanded();
      const row = screen.getByTestId("outcome-branch-staffing");
      expect(row).toHaveTextContent("состав");
      const team2 = screen.getByTestId("outcome-branch-staffing-team2");
      expect(team2).toHaveTextContent("команда из двух");
      const delta = within(team2).getByTestId(
        "outcome-branch-staffing-team2-route",
      );
      expect(delta).toHaveTextContent("Маршрут подписания");
      expect(delta).toHaveTextContent("+4");
      expect(delta).toHaveTextContent("добавлено: 4");
      expect(delta).toHaveTextContent("~2");
      expect(delta).toHaveTextContent("изменено: 2");
      expect(
        screen
          .getByTestId("outcome-branch-staffing-solo")
          .getAttribute("data-chosen"),
      ).toBe("true");
      expect(
        screen.getByTestId("outcome-branch-staffing-solo"),
      ).toHaveTextContent("сейчас");
      const kindResearch = screen.getByTestId("outcome-branch-kind-research");
      expect(kindResearch).toHaveTextContent("-7");
      expect(kindResearch).toHaveTextContent("убрано: 7");
    });

    it("«Показать эти вводные» пишет вводную в адрес; умолчание снимает её", async () => {
      await expanded();
      fireEvent.click(screen.getByTestId("outcome-branch-staffing-show-team2"));
      expect(screen.getByTestId("search").textContent).toContain(
        "i.staffing=team2",
      );
    });

    it("значение по умолчанию снимает вводную из адреса, поверх сценария остаётся", async () => {
      const kind = structuredClone(VKR_BRANCHES[0]);
      if (!kind) throw new Error("no branch");
      kind.chosen = "research";
      serve({ branches: [kind] });
      mount("selected=branches:kind&i.kind=research&i.staffing=team2");
      await screen.findByTestId("outcome-branch-kind");
      fireEvent.click(screen.getByTestId("outcome-branch-kind-show-project"));
      const search = screen.getByTestId("search").textContent;
      expect(search).not.toContain("i.kind");
      expect(search).toContain("i.staffing=team2");
      cleanup();
      vi.restoreAllMocks();
      serve({ branches: [kind] });
      mount("selected=branches:kind&scenario=company&i.kind=research");
      await screen.findByTestId("outcome-branch-kind");
      fireEvent.click(screen.getByTestId("outcome-branch-kind-show-project"));
      expect(screen.getByTestId("search").textContent).toContain(
        "i.kind=project",
      );
    });

    it("выбор ветки пишет branches:<вводная> в адрес", async () => {
      await expanded();
      const pick = within(
        screen.getByTestId("outcome-branch-kind"),
      ).getAllByRole("button")[0];
      if (!pick) throw new Error("no button");
      fireEvent.click(pick);
      expect(screen.getByTestId("search").textContent).toContain(
        "selected=branches%3Akind",
      );
      expect(pick).toHaveAttribute("aria-pressed", "true");
      fireEvent.click(pick);
      expect(screen.getByTestId("search").textContent).not.toContain(
        "selected",
      );
    });

    it("поиск и фильтр по разделу, пустая выдача и сброс", async () => {
      await expanded();
      fireEvent.change(screen.getByTestId("outcome-branches-affects"), {
        target: { value: "participants" },
      });
      expect(screen.getByTestId("outcome-branch-staffing")).toBeInTheDocument();
      expect(screen.queryByTestId("outcome-branch-kind")).toBeNull();
      expect(screen.queryByTestId("outcome-branch-meta.nda")).toBeNull();
      fireEvent.change(screen.getByTestId("outcome-branches-affects"), {
        target: { value: "all" },
      });
      const search = screen.getByTestId("outcome-branches-filter-search");
      fireEvent.change(search, { target: { value: "research" } });
      expect(screen.getByTestId("outcome-branch-kind")).toBeInTheDocument();
      expect(screen.queryByTestId("outcome-branch-staffing")).toBeNull();
      fireEvent.change(search, { target: { value: "нет такого" } });
      const none = screen.getByTestId("outcome-branches-noresults");
      fireEvent.click(within(none).getByRole("button"));
      expect(search).toHaveValue("");
      expect(screen.getByTestId("outcome-branch-staffing")).toBeInTheDocument();
    });

    it("счётчики блока", async () => {
      await expanded();
      expect(
        screen.getByTestId("outcome-branches-stats-inputs"),
      ).toHaveTextContent(String(VKR_BRANCHES.length));
      const alternatives = VKR_BRANCHES.flatMap((b) =>
        b.alternatives.filter((a) => a.value !== b.chosen),
      );
      expect(
        screen.getByTestId("outcome-branches-stats-alternatives"),
      ).toHaveTextContent(String(alternatives.length));
      expect(
        screen.getByTestId("outcome-branches-stats-same"),
      ).toHaveTextContent("0");
    });

    it("пусто: вводные ничего не меняют и сервер не вернул часть", async () => {
      serve({ branches: [] });
      const first = mount("selected=branches:x");
      expect(
        await screen.findByTestId("outcome-branches-empty"),
      ).toHaveTextContent("Результат не зависит от вводных");
      // Варианты и язык не зависят от запроса веток.
      expect(
        screen.getByTestId("outcome-variants-presentation"),
      ).toBeInTheDocument();
      first.unmount();
      vi.restoreAllMocks();
      vi.spyOn(packOutcomeApi, "outcome").mockResolvedValue({
        ...VKR_OUTCOME,
        branches: null,
      });
      mount("selected=branches:x");
      expect(
        await screen.findByTestId("outcome-branches-unavailable"),
      ).toBeInTheDocument();
    });

    it("нет вариантов у документов: честное пояснение", async () => {
      const bare = structuredClone(VKR_OUTCOME);
      for (const doc of bare.documents) doc.variants = [];
      serve();
      mount("selected=branches:staffing", { outcome: bare });
      await screen.findByTestId("outcome-branch-staffing");
      expect(screen.getByTestId("outcome-variants-empty")).toHaveTextContent(
        "нет вариантов",
      );
    });

    it("ошибка запроса: плашка с повтором, варианты и язык остаются", async () => {
      const spy = vi.spyOn(packOutcomeApi, "outcome");
      spy.mockRejectedValueOnce(
        new ApiError("Сбой", "version_unreadable", 422),
      );
      spy.mockImplementation((_id, _ref, body) =>
        Promise.resolve(answer(body, {})),
      );
      mount("selected=branches:staffing");
      const error = await screen.findByTestId("outcome-branches-error");
      expect(error).toHaveTextContent(
        "Не удалось получить раздел «Ветки и варианты»",
      );
      expect(
        screen.getByTestId("outcome-variants-presentation"),
      ).toBeInTheDocument();
      expect(screen.queryByTestId("outcome-branch-staffing")).toBeNull();
      fireEvent.click(screen.getByTestId("outcome-branches-retry"));
      await screen.findByTestId("outcome-branch-staffing");
    });

    it("загрузка: скелет только в блоке веток", async () => {
      vi.spyOn(packOutcomeApi, "outcome").mockImplementation(
        () => new Promise<PackOutcome>(() => undefined),
      );
      mount("selected=branches:staffing");
      expect(
        await screen.findByTestId("outcome-branches-skeleton"),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId("outcome-variants-presentation"),
      ).toBeInTheDocument();
    });

    it("ветка пространства: папка без git", async () => {
      await expanded("", { workspaceKind: "folder" });
      expect(screen.getByTestId("outcome-branches-folder")).toHaveTextContent(
        "без git",
      );
      expect(screen.getByTestId("outcome-branches-state")).toHaveTextContent(
        "Рабочее дерево",
      );
      expect(
        screen.getByTestId("outcome-branches-fingerprint"),
      ).toHaveTextContent(VKR_OUTCOME.fingerprint);
      for (const print of VKR_OUTCOME.digest.sections) {
        expect(
          screen.getByTestId(`outcome-branches-print-${print.section}`),
        ).toHaveTextContent(String(print.count));
      }
    });

    it("ветка пространства: git с расхождением и несохранёнными правками", async () => {
      const git = {
        branch: "feat/template-fix",
        base_branch: "main",
        ahead: 3,
        behind: 1,
        uncommitted: [{ path: "a" }, { path: "b" }],
      } as unknown as PackGit;
      await expanded("state=base", { workspaceKind: "git", git });
      expect(screen.getByTestId("outcome-branches-branch")).toHaveTextContent(
        "feat/template-fix",
      );
      expect(screen.getByTestId("outcome-branches-base")).toHaveTextContent(
        "main",
      );
      expect(screen.getByTestId("outcome-branches-drift")).toHaveTextContent(
        "впереди на 3, позади на 1",
      );
      expect(
        screen.getByTestId("outcome-branches-uncommitted"),
      ).toHaveTextContent("2");
    });

    it("ветка пространства: git ещё не пришёл", async () => {
      await expanded("", { workspaceKind: "git" });
      expect(screen.getByTestId("outcome-branches-nogit")).toBeInTheDocument();
    });

    it("английский словарь", async () => {
      await i18n.changeLanguage("en");
      await expanded();
      expect(screen.getByTestId("outcome-branches-whatif")).toHaveTextContent(
        "What changes with another choice",
      );
      expect(
        screen.getByTestId("outcome-variants-presentation"),
      ).toHaveTextContent("PowerPoint template");
      expect(
        screen.getByTestId("outcome-branch-staffing-team2-route"),
      ).toHaveTextContent("added: 4");
      expect(screen.getByTestId("outcome-branches")).not.toHaveTextContent(
        /\b(checks|branches)\.[a-z]/,
      );
    });
  });
});
