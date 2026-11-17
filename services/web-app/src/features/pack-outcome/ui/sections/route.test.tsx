import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { packOutcomeKeys, type PackOutcome } from "@entities/pack-studio";
import {
  COURSEWORK_OUTCOME,
  VKR_INPUTS,
  VKR_OUTCOME,
} from "@entities/pack-studio/reference";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { useOutcomeUrlState } from "../../lib/urlState";
import { OutcomeModelContext, type OutcomeModel } from "../../model";
import { DocumentsSection } from "./DocumentsSection";
import { ParticipantsSection } from "./ParticipantsSection";
import { PointsSection } from "./PointsSection";
import { RouteSection } from "./RouteSection";

// Секции F4 на эталонах: ВКР (маршруты по умолчанию, много may_add), курсовая hse-cs-sse (профиль
// с пресетом, параллельный шаг) и правки под случаи, которых в эталонах нет (пропущенные пары,
// шаг без человека, команда). Сервер не нужен: модель собрана вручную, адрес в MemoryRouter.

const client = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

const Probe = () => {
  const { search } = useLocation();
  return <output data-testid="search">{search}</output>;
};

const Harness = ({
  outcome,
  stale = false,
}: {
  outcome: PackOutcome | undefined;
  stale?: boolean;
}) => {
  const url = useOutcomeUrlState();
  const model = {
    workspaceId: "w",
    request: { state: "work_tree", scenario: null, example: null, inputs: {} },
    ref: { pack: "p", template: "t", version: "v" },
    released: false,
    phone: false,
    url,
    shown: outcome,
    stale,
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
  } as unknown as OutcomeModel;
  return (
    <QueryClientProvider client={client}>
      <OutcomeModelContext.Provider value={model}>
        <DocumentsSection />
        <ParticipantsSection />
        <PointsSection />
        <RouteSection />
        <Probe />
      </OutcomeModelContext.Provider>
    </QueryClientProvider>
  );
};

const mount = (outcome: PackOutcome | undefined, search = "", stale = false) =>
  render(
    <MemoryRouter initialEntries={[`/${search ? `?${search}` : ""}`]}>
      <Harness outcome={outcome} stale={stale} />
    </MemoryRouter>,
  );

const edit = (
  base: PackOutcome,
  change?: (o: PackOutcome) => void,
): PackOutcome => {
  const out = structuredClone(base);
  change?.(out);
  return out;
};
const vkr = (change?: (o: PackOutcome) => void) => edit(VKR_OUTCOME, change);
const course = (change?: (o: PackOutcome) => void) =>
  edit(COURSEWORK_OUTCOME, change);

const point = (o: PackOutcome, id: string) => {
  const found = o.points.find((p) => p.id === id);
  if (!found) throw new Error(`no point ${id}`);
  return found;
};

/** Научрук не указан: шаги маршрута с ним остаются без человека. */
const noSupervisor = (o: PackOutcome) => {
  for (const p of o.participants) {
    if (p.persona === "supervisor") {
      p.present = false;
      p.name = "";
      p.org = null;
    }
  }
  for (const pt of o.points) {
    for (const step of pt.route.steps) {
      for (const person of step) {
        if (person.persona === "supervisor") person.name = "";
      }
    }
  }
};

/**
 * Курсовая hse-cs-se: научрук из университета, академрук не подписывает, пресета нет. Слот
 * академрука пропущен условием (трасса: условие не выполнено), порядок шагов встроенный.
 */
const universityCourse = (o: PackOutcome) => {
  const topic = point(o, "topic-approval");
  topic.route.steps = topic.route.steps.slice(0, 2);
  topic.route.pairs = topic.route.pairs.filter(
    (p) => p.slot_id !== "academic_supervisor",
  );
  topic.route.skipped = [
    {
      doc_id: "topic_application",
      slot_id: "academic_supervisor",
      when: { person: "supervisor", role: "company" },
      why: ["t15"],
    },
  ];
  topic.route.order_source = "version";
  topic.route.preset = false;
  const t15 = o.trace.find((x) => x.id === "t15");
  if (t15) {
    t15.status = "not_held";
    t15.actual = { supervisor: "yes", "supervisor.role": "university" };
  }
};

describe("секции F4: точки сдачи и маршрут подписания", () => {
  beforeAll(async () => {
    await loadPackOutcomeNamespace();
  });
  afterEach(async () => {
    cleanup();
    window.localStorage.clear();
    await i18n.changeLanguage("ru");
  });

  describe("точки сдачи", () => {
    it("карточка точки: название, счётчик пунктов, подсказка срока, подписи", () => {
      mount(course());
      const card = screen.getByTestId("outcome-point-topic-approval");
      expect(card).toHaveTextContent("Заявка на тему КП (SmartLMS)");
      expect(card).toHaveTextContent("2 из 2 пунктов");
      expect(
        screen.getByTestId("outcome-point-topic-approval-hint"),
      ).toHaveTextContent("Срок: Обычно в середине ноября");
      const topic = screen.getByTestId(
        "outcome-item-topic-approval-topic_application",
      );
      expect(topic).toHaveTextContent("Подписи: Автор, Руководитель");
      expect(
        screen.getByTestId("outcome-item-extended-proposal-presentation"),
      ).toHaveTextContent("без подписей");
      expect(card).toHaveTextContent("Подписей: 5");
    });

    it("без подсказки срока строки нет", () => {
      mount(vkr());
      expect(
        screen.queryByTestId("outcome-point-checkpoint-1-hint"),
      ).toBeNull();
    });

    it("выключенные пункты в свёрнутом блоке, приглушены, с причиной", () => {
      mount(vkr());
      const toggle = screen.getByTestId("outcome-point-final-off-toggle");
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(
        screen.queryByTestId("outcome-item-final-operator_manual"),
      ).toBeNull();
      fireEvent.click(toggle);
      const row = screen.getByTestId("outcome-item-final-operator_manual");
      expect(row).toHaveAttribute("data-muted", "true");
      expect(row).toHaveTextContent("документ выключен");
      expect(row).toHaveTextContent("Только программиста");
      // Активные остаются снаружи, причины «документа нет» читаются из трассы.
      expect(
        screen.getByTestId("outcome-item-final-thesis"),
      ).not.toHaveAttribute("data-muted");
      fireEvent.click(
        screen.getByTestId("outcome-point-checkpoint-1-off-toggle"),
      );
      const absent = screen.getByTestId(
        "outcome-item-checkpoint-1-shared_annotation",
      );
      expect(absent).toHaveTextContent("документа нет в комплекте");
      expect(absent).toHaveTextContent("не сдаётся:");
    });

    it("причина выключения из сервера: NDA и вид работы", () => {
      mount(
        vkr((o) => {
          const final = point(o, "final");
          const nda = final.items.find((i) => i.doc_id === "nda");
          if (nda) {
            nda.active = false;
            nda.off_reason = "nda";
          }
          const prog = final.items.find(
            (i) => i.doc_id === "programmer_manual",
          );
          if (prog) {
            prog.active = false;
            prog.off_reason = "kind";
          }
        }),
      );
      fireEvent.click(screen.getByTestId("outcome-point-final-off-toggle"));
      expect(screen.getByTestId("outcome-item-final-nda")).toHaveTextContent(
        "NDA",
      );
      expect(
        screen.getByTestId("outcome-item-final-programmer_manual"),
      ).toHaveTextContent("вид работы");
    });

    it("дополнительные файлы: имя, источник, формат", () => {
      mount(course());
      const list = screen.getByTestId("outcome-point-final-extra");
      expect(list).toHaveTextContent("Ссылка на репозиторий.txt");
      expect(list).toHaveTextContent(".hse-studio/forms/code_link.json");
      expect(list).toHaveTextContent("markdown");
    });

    it("счётчики берутся из ответа", () => {
      mount(course());
      expect(
        screen.getByTestId("outcome-points-stats-points"),
      ).toHaveTextContent("4");
      expect(
        screen.getByTestId("outcome-points-stats-active"),
      ).toHaveTextContent("9");
      expect(
        screen.getByTestId("outcome-points-stats-extra"),
      ).toHaveTextContent("1");
      expect(screen.getByTestId("outcome-count-points")).toHaveTextContent("4");
    });

    it("«К документу» выбирает документ в секции «Документы», повтор не снимает", () => {
      mount(vkr());
      const link = screen.getByTestId("outcome-doc-link-final-thesis");
      fireEvent.click(link);
      expect(screen.getByTestId("search")).toHaveTextContent(
        "selected=documents%3Athesis",
      );
      expect(
        within(screen.getByTestId("outcome-doc-thesis")).getByRole("button"),
      ).toHaveAttribute("aria-pressed", "true");
      fireEvent.click(screen.getByTestId("outcome-doc-link-gia-thesis"));
      expect(screen.getByTestId("search")).toHaveTextContent(
        "selected=documents%3Athesis",
      );
    });

    it("выбор точки и пункта пишет в адрес раздел points", () => {
      mount(course());
      fireEvent.click(screen.getByTestId("outcome-point-final-pick"));
      expect(screen.getByTestId("search")).toHaveTextContent(
        "selected=points%3Afinal",
      );
      expect(screen.getByTestId("outcome-point-final")).toHaveAttribute(
        "data-selected",
        "true",
      );
      fireEvent.click(
        within(screen.getByTestId("outcome-item-final-report")).getAllByRole(
          "button",
        )[0]!,
      );
      expect(screen.getByTestId("search")).toHaveTextContent(
        "selected=points%3Afinal%2Freport",
      );
    });

    it("фильтр по точке и поиск по документу и имени файла", () => {
      mount(vkr());
      fireEvent.change(screen.getByTestId("outcome-points-only"), {
        target: { value: "gia" },
      });
      expect(screen.getByTestId("outcome-points-list").children).toHaveLength(
        1,
      );
      fireEvent.change(screen.getByTestId("outcome-points-only"), {
        target: { value: "" },
      });
      fireEvent.change(screen.getByTestId("outcome-points-filter-search"), {
        target: { value: "source_listing" },
      });
      const list = screen.getByTestId("outcome-points-list");
      expect(
        within(list).queryByTestId("outcome-point-checkpoint-1"),
      ).toBeNull();
      expect(
        within(list).getByTestId("outcome-point-checkpoint-3"),
      ).toBeInTheDocument();
      fireEvent.change(screen.getByTestId("outcome-points-filter-search"), {
        target: { value: "нет-такого-слова" },
      });
      expect(
        screen.getByTestId("outcome-points-noresults"),
      ).toBeInTheDocument();
    });

    it("поиск раскрывает выключенные пункты", () => {
      mount(vkr());
      fireEvent.change(screen.getByTestId("outcome-points-filter-search"), {
        target: { value: "interim_report" },
      });
      expect(
        screen.getAllByTestId("outcome-item-checkpoint-2-interim_report"),
      ).toHaveLength(1);
    });

    it("точек нет: пояснение", () => {
      mount(
        vkr((o) => {
          o.points = [];
        }),
      );
      expect(screen.getByTestId("outcome-points-empty")).toHaveTextContent(
        "В версии нет точек сдачи",
      );
      expect(screen.getByTestId("outcome-route-empty")).toBeInTheDocument();
    });

    it("стрелки двигают фокус по кнопкам секции", () => {
      mount(course());
      const section = screen.getByTestId("outcome-points");
      const first = within(section).getByTestId(
        "outcome-point-topic-approval-pick",
      );
      first.focus();
      fireEvent.keyDown(first, { key: "ArrowDown" });
      expect(document.activeElement).not.toBe(first);
      expect(section.contains(document.activeElement)).toBe(true);
      fireEvent.keyDown(document.activeElement as HTMLElement, { key: "Home" });
      expect(document.activeElement).toBe(first);
    });
  });

  describe("маршрут подписания", () => {
    it("шаги по порядку списком, параллельные люди в одном шаге", () => {
      mount(course());
      const lane = screen.getByTestId("outcome-route-topic-approval-steps");
      expect(lane.tagName).toBe("OL");
      expect(lane).toHaveAccessibleName(
        "Шаги маршрута точки «Заявка на тему КП (SmartLMS)»",
      );
      const steps = within(lane).getAllByRole("listitem");
      expect(steps).toHaveLength(3);
      expect(steps[0]).toHaveTextContent("Шаг 1");
      expect(steps[0]).toHaveTextContent("Иванов Иван Иванович");
      expect(steps[1]).toHaveTextContent("Шаг 2");
      expect(steps[1]).toHaveTextContent("Смирнов Олег Игоревич");
      expect(steps[1]).toHaveTextContent("Кузнецова Анна Викторовна");
      expect(steps[1]).toHaveTextContent("параллельно");
      expect(steps[1]).toHaveAttribute("data-parallel", "true");
      expect(steps[2]).toHaveTextContent("Васильев Дмитрий Андреевич");
      expect(steps[0]).not.toHaveAttribute("data-parallel");
    });

    it("источник порядка и пресет подписаны", () => {
      mount(course());
      expect(
        screen.getByTestId("outcome-route-topic-approval-order"),
      ).toHaveTextContent("Порядок: из профиля точки");
      expect(
        screen.getByTestId("outcome-route-topic-approval"),
      ).toHaveTextContent("пресет маршрута");
      expect(screen.getByTestId("outcome-route-final-order")).toHaveTextContent(
        "Порядок: встроенный",
      );
    });

    it("пары: слот, персона, источник, условие и необязательность", () => {
      mount(
        course((o) => {
          const pair = point(o, "topic-approval").route.pairs.find(
            (p) => p.slot_id === "co_supervisor",
          );
          if (pair) pair.optional = true;
        }),
      );
      const co = screen.getByTestId(
        "outcome-pair-topic-approval-topic_application-co_supervisor",
      );
      expect(co).toHaveTextContent("Второй руководитель");
      expect(co).toHaveTextContent("Кузнецова Анна Викторовна");
      expect(co).toHaveTextContent("из пресета");
      expect(co).toHaveTextContent("Необязательна");
      expect(co).toHaveTextContent("если второй руководитель указан");
      const academic = screen.getByTestId(
        "outcome-pair-topic-approval-topic_application-academic_supervisor",
      );
      expect(academic).toHaveTextContent("если руководитель из компании");
      const own = screen.getByTestId(
        "outcome-pair-topic-approval-topic_application-author",
      );
      expect(own).toHaveTextContent("из точки");
      expect(own).not.toHaveTextContent("если");
      expect(own).not.toHaveTextContent("Необязательна");
    });

    it("пары сгруппированы по документу", () => {
      mount(course());
      const card = screen.getByTestId("outcome-route-topic-approval");
      const groups = within(card).getAllByRole("list", {
        name: /Заявка на тему|Предложение|Project|Topic/i,
      });
      expect(groups.length).toBeGreaterThan(0);
      expect(card).toHaveTextContent("Подписи по документам");
    });

    it("пропущенные условием: серым, с причиной из трассы", () => {
      mount(course(universityCourse));
      expect(
        screen.getByTestId("outcome-route-topic-approval-order"),
      ).toHaveTextContent("из версии");
      expect(
        screen.queryByTestId("outcome-route-topic-approval"),
      ).not.toHaveTextContent("пресет маршрута");
      const toggle = screen.getByTestId(
        "outcome-route-topic-approval-skipped-toggle",
      );
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      fireEvent.click(toggle);
      const skipped = screen.getByTestId(
        "outcome-skipped-topic-approval-topic_application-academic_supervisor",
      );
      expect(skipped).toHaveTextContent("пропущено:");
      expect(skipped).toHaveTextContent("если руководитель из компании");
      expect(skipped).toHaveTextContent("организация: сейчас ВШЭ");
      expect(skipped).toHaveTextContent("нужно компания");
      expect(skipped.closest("[data-muted]")).toHaveAttribute(
        "data-muted",
        "true",
      );
      expect(
        screen.getByTestId("outcome-route-stats-skipped"),
      ).toHaveTextContent("1");
    });

    it("может_добавить: слоты по ролям, документы названиями", () => {
      mount(vkr());
      const toggle = screen.getByTestId("outcome-route-final-mayadd-toggle");
      expect(toggle).toHaveTextContent("Можно добавить при создании проекта");
      expect(toggle).toHaveTextContent("7");
      fireEvent.click(toggle);
      const block = screen.getByTestId("outcome-route-final-mayadd");
      expect(block).toHaveTextContent("Второй руководитель");
      expect(block).toHaveTextContent("Техническое задание");
      expect(block).toHaveTextContent("Автор проекта включит эти подписи сам");
    });

    it("точки без подписей лежат в свёрнутом блоке", () => {
      mount(vkr());
      const toggle = screen.getByTestId("outcome-route-unsigned-toggle");
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      fireEvent.click(toggle);
      const row = screen.getByTestId("outcome-route-checkpoint-1-none");
      expect(row).toHaveTextContent("КТ1");
      expect(row).toHaveTextContent("встроенный");
      expect(screen.queryByTestId("outcome-route-checkpoint-1")).toBeNull();
    });

    it("счётчики и подпись разделов из ответа", () => {
      mount(course());
      expect(
        screen.getByTestId("outcome-route-stats-points"),
      ).toHaveTextContent("2");
      expect(screen.getByTestId("outcome-route-stats-steps")).toHaveTextContent(
        "4",
      );
      expect(screen.getByTestId("outcome-route-stats-pairs")).toHaveTextContent(
        "6",
      );
      expect(
        screen.getByTestId("outcome-route-stats-mayAdd"),
      ).toHaveTextContent("1");
    });

    it("выбор шага и пары пишет в адрес раздел route", () => {
      mount(course());
      fireEvent.click(
        within(screen.getByTestId("outcome-step-topic-approval-2")).getByRole(
          "button",
        ),
      );
      expect(screen.getByTestId("search")).toHaveTextContent(
        "selected=route%3Atopic-approval%2Fstep%2F2",
      );
      fireEvent.click(
        within(
          screen.getByTestId(
            "outcome-pair-topic-approval-topic_application-co_supervisor",
          ),
        ).getByRole("button"),
      );
      expect(screen.getByTestId("search")).toHaveTextContent(
        "selected=route%3Atopic-approval%2Ftopic_application%2Fco_supervisor",
      );
      expect(
        screen.getByTestId(
          "outcome-pair-topic-approval-topic_application-co_supervisor",
        ),
      ).toHaveAttribute("data-selected", "true");
    });

    it("выбранная из адреса пара подсвечена", () => {
      mount(
        course(),
        "selected=route:topic-approval/topic_application/academic_supervisor",
      );
      expect(
        screen.getByTestId(
          "outcome-pair-topic-approval-topic_application-academic_supervisor",
        ),
      ).toHaveAttribute("data-selected", "true");
    });

    it("автор команды в слоте автора: в id пары идёт персона", () => {
      mount(
        course((o) => {
          const final = point(o, "final");
          final.route.pairs = [
            {
              doc_id: "report",
              slot_id: "author",
              persona: "author1",
              source: "point",
              optional: false,
              when: null,
              why: [],
            },
            {
              doc_id: "report",
              slot_id: "author",
              persona: "author2",
              source: "point",
              optional: false,
              when: null,
              why: [],
            },
          ];
          final.route.steps = [
            [
              { persona: "author1", role: "author", name: "Иванов" },
              { persona: "author2", role: "author", name: "Петрова" },
            ],
          ];
        }),
      );
      const second = screen.getByTestId(
        "outcome-pair-final-report-author-author2",
      );
      expect(
        screen.getByTestId("outcome-pair-final-report-author-author1"),
      ).toBeInTheDocument();
      fireEvent.click(within(second).getByRole("button"));
      expect(screen.getByTestId("search")).toHaveTextContent(
        "selected=route%3Afinal%2Freport%2Fauthor%2Fauthor2",
      );
      expect(second).toHaveTextContent("Автор 2");
    });

    it("пропущенный слот: «Добавить во вводных» применяет одну вводную из «что если» сервера", async () => {
      const element = {
        section: "route",
        id: "topic-approval/topic_application/academic_supervisor",
      } as const;
      client.setQueryData(
        packOutcomeKeys.explain(
          "w",
          { pack: "p", template: "t", version: "v" },
          {
            state: "work_tree",
            scenario: null,
            example: null,
            inputs: {},
            element,
          },
        ),
        {
          data: {
            element,
            state: "absent",
            chain: [],
            readers: [],
            // Первая запись не возвращает слот, вторая возвращает: берётся вторая.
            counterfactuals: [
              { input: "academic_supervisor", value: "no", result: "absent" },
              { input: "supervisor", value: "company", result: "present" },
            ],
          },
          etag: null,
        },
      );
      mount(course(universityCourse));
      fireEvent.click(
        screen.getByTestId("outcome-route-topic-approval-skipped-toggle"),
      );
      const skipped = screen.getByTestId(
        "outcome-skipped-topic-approval-topic_application-academic_supervisor",
      );
      expect(skipped).toHaveAttribute("data-pale", "true");
      fireEvent.click(
        within(skipped).getByTestId(
          "outcome-pale-add-route-topic-approval/topic_application/academic_supervisor",
        ),
      );
      await waitFor(() => {
        expect(screen.getByTestId("search")).toHaveTextContent(
          "?i.supervisor=company",
        );
      });
      client.clear();
    });

    it("фильтр по точке и поиск по документу и человеку", () => {
      mount(vkr());
      fireEvent.change(screen.getByTestId("outcome-route-only"), {
        target: { value: "gia" },
      });
      const list = screen.getByTestId("outcome-route-list");
      expect(list.children).toHaveLength(1);
      expect(screen.queryByTestId("outcome-route-final")).toBeNull();
      fireEvent.change(screen.getByTestId("outcome-route-only"), {
        target: { value: "" },
      });
      fireEvent.change(screen.getByTestId("outcome-route-filter-search"), {
        target: { value: "pdp_work_plan" },
      });
      expect(
        screen.getByTestId("outcome-route-pdp-application"),
      ).toBeInTheDocument();
      expect(
        screen.queryByTestId(
          "outcome-pair-pdp-application-pdp_assignment-author",
        ),
      ).toBeNull();
      fireEvent.change(screen.getByTestId("outcome-route-filter-search"), {
        target: { value: "нет-такого-слова" },
      });
      expect(screen.getByTestId("outcome-route-noresults")).toBeInTheDocument();
    });

    it("стрелки двигают фокус по шагам и парам", () => {
      mount(course());
      const section = screen.getByTestId("outcome-route");
      const step1 = within(
        screen.getByTestId("outcome-step-topic-approval-1"),
      ).getByRole("button");
      step1.focus();
      fireEvent.keyDown(step1, { key: "ArrowDown" });
      expect(document.activeElement).toBe(
        within(screen.getByTestId("outcome-step-topic-approval-2")).getByRole(
          "button",
        ),
      );
      fireEvent.keyDown(document.activeElement as HTMLElement, { key: "End" });
      expect(section.contains(document.activeElement)).toBe(true);
      expect(document.activeElement).not.toBe(step1);
    });
  });

  describe("шаг без человека", () => {
    it("предупреждение в обеих секциях из общего блока", () => {
      mount(vkr());
      expect(screen.queryByTestId("outcome-route-warning")).toBeNull();
      expect(screen.queryByTestId("outcome-participants-warning")).toBeNull();
      cleanup();
      mount(vkr(noSupervisor));
      const route = screen.getByTestId("outcome-route-warning");
      const people = screen.getByTestId("outcome-participants-warning");
      expect(route).toHaveTextContent("Нет человека для шага маршрута");
      expect(route.textContent).toBe(people.textContent);
      expect(route).toHaveTextContent("Точка «Заявление на ПДП», шаг 2");
      expect(route.querySelectorAll("li").length).toBeGreaterThan(0);
    });

    it("пустое имя: чип шага помечен, не пустое место", () => {
      mount(vkr(noSupervisor));
      const step = screen.getByTestId("outcome-step-pdp-application-2");
      const person = within(step).getByTestId(
        "outcome-route-person-pdp-application-2-supervisor",
      );
      expect(person).toHaveAttribute("data-empty", "true");
      expect(person).toHaveTextContent("не указан");
      expect(person).toHaveTextContent("шаг без человека");
      const author = within(
        screen.getByTestId("outcome-step-pdp-application-1"),
      ).getByTestId("outcome-route-person-pdp-application-1-author");
      expect(author).not.toHaveAttribute("data-empty");
    });

    it("отсутствующий участник с именем тоже считается шагом без человека", () => {
      mount(
        vkr((o) => {
          const sup = o.participants.find((p) => p.persona === "supervisor");
          if (sup) sup.present = false;
        }),
      );
      expect(screen.getByTestId("outcome-route-warning")).toBeInTheDocument();
    });
  });

  describe("состояния", () => {
    it("нет результата: скелет, без карточек", () => {
      mount(undefined);
      expect(screen.queryByTestId("outcome-points")).toBeNull();
      expect(screen.queryByTestId("outcome-route")).toBeNull();
      expect(screen.getByTestId("outcome-section-route")).toBeInTheDocument();
    });

    it("пересчёт: прежний результат на месте и приглушён", () => {
      mount(course(), "", true);
      expect(screen.getByTestId("outcome-points")).toHaveAttribute(
        "data-stale",
        "true",
      );
      expect(screen.getByTestId("outcome-route")).toHaveAttribute(
        "data-stale",
        "true",
      );
      expect(screen.getByTestId("outcome-step-topic-approval-1")).toBeVisible();
    });

    it("раздел сворачивается и помнит состояние", () => {
      mount(course());
      const toggle = within(
        screen.getByTestId("outcome-section-route"),
      ).getByRole("button", { name: /Маршрут подписания/ });
      fireEvent.click(toggle);
      expect(
        window.localStorage.getItem("hse-studio.packOutcome.section.route"),
      ).toBe("1");
      expect(screen.getByTestId("outcome-section-route")).toHaveAttribute(
        "data-collapsed",
        "true",
      );
    });
  });

  describe("английский словарь", () => {
    it("тексты точек и маршрута переводятся, названия берутся на языке интерфейса", async () => {
      await i18n.changeLanguage("en");
      mount(course(universityCourse));
      const card = screen.getByTestId("outcome-point-topic-approval");
      expect(card).toHaveTextContent("Topic application (SmartLMS)");
      expect(card).toHaveTextContent("2 of 2 items");
      expect(
        screen.getByTestId("outcome-point-topic-approval-hint"),
      ).toHaveTextContent("Deadline: Usually mid-November");
      expect(
        screen.getByTestId("outcome-item-topic-approval-topic_application"),
      ).toHaveTextContent("Signatures: Author, Supervisor");
      const lane = screen.getByTestId("outcome-route-topic-approval-steps");
      expect(lane).toHaveAccessibleName(
        'Route steps of checkpoint "Topic application (SmartLMS)"',
      );
      expect(within(lane).getAllByRole("listitem")[1]).toHaveTextContent(
        "in parallel",
      );
      expect(
        screen.getByTestId("outcome-route-topic-approval-order"),
      ).toHaveTextContent("Order: from the version");
      fireEvent.click(
        screen.getByTestId("outcome-route-topic-approval-skipped-toggle"),
      );
      const skipped = screen.getByTestId(
        "outcome-skipped-topic-approval-topic_application-academic_supervisor",
      );
      expect(skipped).toHaveTextContent("skipped:");
      expect(skipped).toHaveTextContent("if supervisor is from the company");
    });

    it("предупреждение и бледные состояния по-английски", async () => {
      await i18n.changeLanguage("en");
      mount(vkr(noSupervisor));
      expect(screen.getByTestId("outcome-route-warning")).toHaveTextContent(
        "No person for a route step",
      );
      expect(
        screen.getByTestId("outcome-route-person-pdp-application-2-supervisor"),
      ).toHaveTextContent("not set");
      fireEvent.click(screen.getByTestId("outcome-point-final-off-toggle"));
      expect(
        screen.getByTestId("outcome-item-final-operator_manual"),
      ).toHaveTextContent("document is off");
    });
  });
});
