import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import type { PackOutcome } from "@entities/pack-studio";
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
import { MetaSection } from "./MetaSection";
import { ParticipantsSection } from "./ParticipantsSection";

// Три секции результата на эталонах ВКР и курсовой: сервер не нужен, модель собрана вручную,
// адрес живёт в MemoryRouter. Выбор элемента пишется в `selected`, как в настоящем экране.

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
  withInputs = true,
}: {
  outcome: PackOutcome | undefined;
  stale?: boolean;
  withInputs?: boolean;
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
    inputs: { data: withInputs ? VKR_INPUTS : undefined },
    select: (el: { section: string; id: string } | null) => {
      const same =
        el !== null &&
        url.state.selected?.section === el.section &&
        url.state.selected.id === el.id;
      url.update({ selected: same ? null : (el as never) });
    },
  } as unknown as OutcomeModel;
  return (
    <QueryClientProvider client={client}>
      <OutcomeModelContext.Provider value={model}>
        <DocumentsSection />
        <MetaSection />
        <ParticipantsSection />
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

const vkr = (edit?: (o: PackOutcome) => void): PackOutcome => {
  const out = structuredClone(VKR_OUTCOME);
  edit?.(out);
  return out;
};

describe("секции F3: документы, метаданные, участники", () => {
  beforeAll(async () => {
    await loadPackOutcomeNamespace();
  });
  afterEach(async () => {
    cleanup();
    window.localStorage.clear();
    await i18n.changeLanguage("ru");
  });

  describe("документы", () => {
    it("карточка: название, состояние, итоговое имя файла, вариант", async () => {
      await i18n.changeLanguage("ru");
      mount(vkr());
      const card = screen.getByTestId("outcome-doc-technical_specification");
      expect(card).toHaveTextContent("Техническое задание");
      expect(card).toHaveTextContent("В комплекте");
      expect(card).toHaveTextContent("Личный");
      expect(card).toHaveTextContent("Техническое задание.pdf");
      const chosen = within(card).getByTestId(
        "outcome-doc-technical_specification-variant-espd",
      );
      expect(chosen).toHaveTextContent("ГОСТ 19 ЕСПД (ТЗ)");
      expect(chosen).toHaveAttribute("data-available", "true");
      const off = within(card).getByTestId(
        "outcome-doc-technical_specification-variant-srs-29148",
      );
      expect(off).toHaveAttribute("data-available", "false");
      expect(off).toHaveTextContent("только en");
    });

    it("выключенный документ остаётся в списке серым с причиной из трассы", () => {
      mount(vkr());
      const card = screen.getByTestId("outcome-doc-operator_manual");
      expect(card).toHaveTextContent("Выключен");
      expect(card).toHaveTextContent("Руководства в комплекте");
      expect(card).toHaveTextContent("Только программиста");
      expect(card.closest("[data-muted]")).toHaveAttribute(
        "data-muted",
        "true",
      );
    });

    it("отсутствующие документы лежат в свёрнутом блоке с причиной", () => {
      mount(vkr());
      const toggle = screen.getByTestId("outcome-documents-absent-toggle");
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByTestId("outcome-doc-annotation")).toBeNull();
      expect(toggle).toHaveTextContent("Не в этой комбинации");
      fireEvent.click(toggle);
      expect(toggle).toHaveAttribute("aria-expanded", "true");
      const annotation = screen.getByTestId("outcome-doc-annotation");
      expect(annotation).toHaveTextContent("вид работы: сейчас проектный");
      expect(annotation).toHaveTextContent("исследовательский");
      const shared = screen.getByTestId("outcome-doc-shared_annotation");
      expect(shared).toHaveTextContent("Общий");
      // Состав проверялся бы после вида работы и не выполнялся: причина одна.
      expect(shared).not.toHaveTextContent("состав");
      const team = screen.getByTestId(
        "outcome-doc-shared_technical_specification",
      );
      expect(team).toHaveTextContent("состав: сейчас один автор");
      expect(team).toHaveTextContent("команда из двух, команда из трёх");
    });

    it("сводка и группы берутся из данных", () => {
      mount(vkr());
      expect(
        screen.getByTestId("outcome-documents-stats-active"),
      ).toHaveTextContent("12");
      expect(
        screen.getByTestId("outcome-documents-stats-inactive"),
      ).toHaveTextContent("1");
      expect(
        screen.getByTestId("outcome-documents-stats-absent"),
      ).toHaveTextContent("5");
      const espd = screen.getByTestId("outcome-documents-group-espd");
      expect(within(espd).getByRole("heading", { level: 4 })).toHaveTextContent(
        "ЕСПД",
      );
      expect(within(espd).getAllByRole("listitem")).toHaveLength(5);
    });

    it("экземпляры по авторам и откат на другой язык", () => {
      mount(
        vkr((o) => {
          const doc = o.documents.find((d) => d.id === "source_listing");
          if (!doc) throw new Error("fixture");
          doc.lang_state = "fallback";
          doc.instances = [
            {
              id: "a1",
              owner: "author1",
              owner_name: "Иванов",
              file_name: "Текст_Иванов.pdf",
            },
            {
              id: "a2",
              owner: "author2",
              owner_name: "Петрова",
              file_name: "Текст_Петрова.pdf",
            },
          ];
        }),
      );
      const card = screen.getByTestId("outcome-doc-source_listing");
      expect(card).toHaveTextContent("Иванов");
      expect(card).toHaveTextContent("Текст_Петрова.pdf");
      expect(card).toHaveTextContent("2 экз.");
      expect(
        screen.getByTestId("outcome-doc-source_listing-fallback"),
      ).toHaveTextContent("Нет редакции на ru: берётся язык по умолчанию");
    });

    it("поиск по названию и имени файла, пустая выдача и сброс", () => {
      mount(vkr());
      const search = screen.getByTestId("outcome-documents-filter-search");
      fireEvent.change(search, { target: { value: "ПДП.pdf" } });
      expect(screen.getByTestId("outcome-doc-pdp_review")).toBeInTheDocument();
      expect(screen.queryByTestId("outcome-doc-thesis")).toBeNull();
      // Поиск раскрывает блок с отсутствующими, если там есть совпадение.
      fireEvent.change(search, { target: { value: "аннотация" } });
      expect(screen.getByTestId("outcome-doc-annotation")).toBeInTheDocument();
      expect(
        screen.getByTestId("outcome-documents-absent-toggle"),
      ).toHaveAttribute("aria-expanded", "true");
      fireEvent.change(search, { target: { value: "нет такого документа" } });
      expect(
        screen.getByTestId("outcome-documents-noresults"),
      ).toBeInTheDocument();
      fireEvent.click(
        within(screen.getByTestId("outcome-documents-noresults")).getByRole(
          "button",
        ),
      );
      expect(search).toHaveValue("");
      expect(screen.getByTestId("outcome-doc-thesis")).toBeInTheDocument();
    });

    it("фильтр по виду: только общие", () => {
      mount(
        vkr((o) => {
          const doc = o.documents.find(
            (d) => d.id === "shared_technical_specification",
          );
          if (doc) doc.state = "active";
        }),
      );
      fireEvent.change(screen.getByTestId("outcome-documents-scope"), {
        target: { value: "shared" },
      });
      expect(
        screen.getByTestId("outcome-doc-shared_technical_specification"),
      ).toBeInTheDocument();
      expect(screen.queryByTestId("outcome-doc-thesis")).toBeNull();
    });

    it("курсовая: четыре документа, у презентации вариантов нет", () => {
      mount(COURSEWORK_OUTCOME);
      expect(screen.getByTestId("outcome-count-documents")).toHaveTextContent(
        "4 из 4 в комплекте",
      );
      expect(screen.queryByTestId("outcome-documents-absent")).toBeNull();
      expect(screen.getByTestId("outcome-doc-report")).toHaveTextContent(
        "Отчёт о курсовом проекте.pdf",
      );
    });
  });

  describe("выбор элемента", () => {
    it("клик пишет selected в адрес, повторный клик снимает", () => {
      mount(vkr());
      const button = within(screen.getByTestId("outcome-doc-thesis")).getByRole(
        "button",
      );
      expect(button).toHaveAttribute("aria-pressed", "false");
      fireEvent.click(button);
      expect(screen.getByTestId("search")).toHaveTextContent(
        "selected=documents%3Athesis",
      );
      expect(button).toHaveAttribute("aria-pressed", "true");
      expect(button).toHaveAttribute("aria-current", "true");
      fireEvent.click(button);
      expect(screen.getByTestId("search")).not.toHaveTextContent("selected");
      expect(button).not.toHaveAttribute("aria-current");
    });

    it("выбранный из адреса элемент подсвечен в каждой секции", () => {
      mount(vkr(), "selected=meta:udc");
      const item = screen.getByTestId("outcome-meta-udc").closest("li");
      expect(item).toHaveAttribute("data-selected", "true");
    });

    it("кнопка называется по заголовку, а не по всему тексту карточки", () => {
      mount(vkr());
      expect(
        screen.getByRole("button", {
          name: "Выпускная квалификационная работа",
        }),
      ).toBeInTheDocument();
    });

    it("стрелки и Home и End двигают фокус по карточкам", () => {
      mount(vkr());
      const buttons = within(screen.getByTestId("outcome-documents"))
        .getAllByRole("button")
        .filter((b) => b.hasAttribute("data-po-pick"));
      const first = buttons[0];
      const second = buttons[1];
      const last = buttons.at(-1);
      if (!first || !second || !last) throw new Error("no cards");
      first.focus();
      fireEvent.keyDown(first, { key: "ArrowDown" });
      expect(second).toHaveFocus();
      fireEvent.keyDown(second, { key: "ArrowUp" });
      expect(first).toHaveFocus();
      fireEvent.keyDown(first, { key: "End" });
      expect(last).toHaveFocus();
      fireEvent.keyDown(last, { key: "Home" });
      expect(first).toHaveFocus();
    });
  });

  describe("метаданные и анкеты", () => {
    it("поля по группам с подписью, типом, обязательностью и значением", () => {
      mount(vkr());
      const year = screen.getByTestId("outcome-meta-year");
      expect(year).toHaveTextContent("Учебный год (год защиты)");
      expect(year).toHaveTextContent("При создании");
      expect(year).toHaveTextContent("Строка");
      expect(year).toHaveTextContent("2026");
      expect(screen.getByTestId("outcome-meta-udc")).toHaveTextContent(
        "При финализации",
      );
      expect(screen.getByTestId("outcome-meta-city")).toHaveTextContent(
        "Не обязательно",
      );
      expect(screen.getByTestId("outcome-meta-manuals")).toHaveTextContent(
        "Программиста и оператора, Только программиста, Только оператора",
      );
      expect(screen.getByTestId("outcome-meta-group-study")).toHaveTextContent(
        "Учёба",
      );
      // Логическое значение показано словом, а не `yes`.
      expect(screen.getByTestId("outcome-meta-nda")).toHaveTextContent("да");
      expect(
        screen.getByTestId("outcome-meta-academic_supervisor"),
      ).toHaveTextContent("нет значения");
    });

    it("скрытые поля лежат в свёрнутом блоке с причиной", () => {
      mount(
        vkr((o) => {
          const f = o.meta.find((m) => m.id === "udc");
          if (f) {
            f.visible = false;
            f.why = ["tx1"];
          }
          o.trace.push({
            id: "tx1",
            rule: {
              origin: "manifest",
              file: "version.yaml",
              pointer: "/meta_fields/udc",
              builtin: null,
            },
            kind: "field_kinds",
            effect: "display",
            join: "all",
            terms: [{ op: "in", subject: "kind", expected: ["research"] }],
            actual: { kind: "project" },
            status: "not_held",
            subjects: [{ section: "meta", id: "udc" }],
          });
        }),
      );
      const toggle = screen.getByTestId("outcome-meta-hidden-toggle");
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByTestId("outcome-meta-udc")).toBeNull();
      fireEvent.click(toggle);
      const field = screen.getByTestId("outcome-meta-udc");
      expect(field).toHaveTextContent("скрыто:");
      expect(field).toHaveTextContent(
        "вид работы: сейчас проектный, нужно исследовательский",
      );
    });

    it("анкеты: видимые поля, скрытые в блоке с причиной по ответу", () => {
      mount(vkr());
      const form = screen.getByTestId("outcome-form-ai_declaration");
      expect(form).toHaveTextContent("Декларация об использовании ИИ");
      expect(form).toHaveTextContent("Нужна для комплекта");
      expect(form).toHaveTextContent("Полей видно: 3 из 7");
      expect(
        within(form).getByTestId("outcome-field-ai_declaration-used_ai"),
      ).toHaveTextContent("Обязательное");
      expect(
        screen.queryByTestId("outcome-field-ai_declaration-tools"),
      ).toBeNull();
      fireEvent.click(
        screen.getByTestId("outcome-form-ai_declaration-hidden-toggle"),
      );
      const hidden = screen.getByTestId("outcome-field-ai_declaration-tools");
      expect(hidden).toHaveTextContent(
        "Использование ИИ: сейчас Я не использовал(а) ИИ",
      );
      expect(hidden).toHaveTextContent("нужно Я использовал(а) ИИ");
    });

    it("поле анкеты выбирается как раздел forms", () => {
      mount(vkr());
      fireEvent.click(
        within(
          screen.getByTestId("outcome-field-code_link-repo_url"),
        ).getByRole("button"),
      );
      expect(screen.getByTestId("search")).toHaveTextContent(
        "selected=forms%3Acode_link%2Frepo_url",
      );
    });

    it("анкета, которая не применяется, уходит в отдельный свёрнутый блок", () => {
      mount(
        vkr((o) => {
          const form = o.forms.find((f) => f.id === "code_link");
          if (form) form.applies = false;
        }),
      );
      expect(screen.queryByTestId("outcome-form-code_link")).toBeNull();
      fireEvent.click(screen.getByTestId("outcome-forms-off-toggle"));
      expect(screen.getByTestId("outcome-form-code_link")).toHaveTextContent(
        "Не применяется",
      );
    });

    it("фильтр обязательности и поиск", () => {
      mount(vkr());
      fireEvent.change(screen.getByTestId("outcome-meta-required"), {
        target: { value: "finalize" },
      });
      expect(screen.getByTestId("outcome-meta-udc")).toBeInTheDocument();
      expect(screen.queryByTestId("outcome-meta-year")).toBeNull();
      fireEvent.change(screen.getByTestId("outcome-meta-required"), {
        target: { value: "all" },
      });
      fireEvent.change(screen.getByTestId("outcome-meta-filter-search"), {
        target: { value: "cloudinfra" },
      });
      expect(screen.getByTestId("outcome-meta-name_short")).toBeInTheDocument();
      expect(screen.queryByTestId("outcome-meta-year")).toBeNull();
    });

    it("пустые метаданные и анкеты: честное пояснение", () => {
      mount(
        vkr((o) => {
          o.meta = [];
          o.forms = [];
        }),
      );
      expect(screen.getByTestId("outcome-meta-empty")).toBeInTheDocument();
    });
  });

  describe("участники", () => {
    it("автор, руководители, источник и обязательность из полей проекта", () => {
      mount(vkr());
      const sup = screen.getByTestId("outcome-participant-supervisor");
      expect(sup).toHaveTextContent("Руководитель");
      expect(sup).toHaveTextContent("Петров Пётр Петрович");
      expect(sup).toHaveTextContent("ВШЭ");
      expect(sup).toHaveTextContent("Указать при создании");
      expect(
        screen.getByTestId("outcome-participant-author"),
      ).toHaveTextContent("Всегда в проекте");
      expect(
        screen.getByTestId("outcome-participant-academic_supervisor"),
      ).toHaveTextContent("Не обязателен");
      expect(
        screen.getByTestId("outcome-participants-stats-authors"),
      ).toHaveTextContent("1");
      expect(
        screen.getByTestId("outcome-participants-stats-absent"),
      ).toHaveTextContent("1");
    });

    it("отсутствующий руководитель остаётся бледной карточкой с причиной из вводной", () => {
      mount(vkr());
      const card = screen.getByTestId("outcome-participant-co_supervisor");
      expect(card).toHaveTextContent("нет:");
      expect(card).toHaveTextContent("вводная «второй руководитель»: нет");
      expect(card.closest("[data-muted]")).toHaveAttribute(
        "data-muted",
        "true",
      );
    });

    it("компания как источник, команда авторов нумеруется", () => {
      mount(COURSEWORK_OUTCOME);
      expect(
        screen.getByTestId("outcome-participant-supervisor"),
      ).toHaveTextContent("Компания");
      cleanup();
      mount(
        vkr((o) => {
          o.participants = [
            {
              persona: "author1",
              role: "author",
              name: "Иванов",
              present: true,
              org: null,
              why: [],
            },
            {
              persona: "author2",
              role: "author",
              name: "Петрова",
              present: true,
              org: null,
              why: [],
            },
            ...o.participants.filter((p) => p.role !== "author"),
          ];
        }),
      );
      expect(
        screen.getByTestId("outcome-participant-author2"),
      ).toHaveTextContent("Автор 2");
      expect(
        screen.getByTestId("outcome-participants-stats-authors"),
      ).toHaveTextContent("2");
    });

    it("предупреждение, когда шаг маршрута остался без человека", () => {
      mount(vkr());
      expect(screen.queryByTestId("outcome-participants-warning")).toBeNull();
      cleanup();
      mount(
        vkr((o) => {
          const sup = o.participants.find((p) => p.persona === "supervisor");
          if (sup) {
            sup.present = false;
            sup.name = "";
            sup.org = null;
          }
          for (const point of o.points) {
            for (const step of point.route.steps) {
              for (const person of step) {
                if (person.persona === "supervisor") person.name = "";
              }
            }
          }
        }),
      );
      const warn = screen.getByTestId("outcome-participants-warning");
      expect(warn).toHaveTextContent("Нет человека для шага маршрута");
      expect(warn.querySelectorAll("li").length).toBeGreaterThan(0);
      expect(warn).toHaveTextContent("шаг 2: не указан supervisor");
    });

    it("выбор участника пишет в адрес раздел participants", () => {
      mount(vkr());
      fireEvent.click(
        within(screen.getByTestId("outcome-participant-supervisor")).getByRole(
          "button",
        ),
      );
      expect(screen.getByTestId("search")).toHaveTextContent(
        "selected=participants%3Asupervisor",
      );
    });
  });

  describe("состояния", () => {
    it("нет результата: скелет, без карточек", () => {
      mount(undefined);
      expect(screen.queryByTestId("outcome-documents")).toBeNull();
      expect(screen.queryByTestId("outcome-meta")).toBeNull();
      expect(screen.queryByTestId("outcome-participants")).toBeNull();
    });

    it("пересчёт: прежний результат на месте и приглушён", () => {
      mount(vkr(), "", true);
      expect(screen.getByTestId("outcome-documents")).toHaveAttribute(
        "data-stale",
        "true",
      );
      expect(screen.getByTestId("outcome-doc-thesis")).toBeInTheDocument();
    });

    it("без вводных причины всё равно читаются: подписи из словаря и значения как есть", () => {
      render(
        <MemoryRouter>
          <Harness outcome={vkr()} withInputs={false} />
        </MemoryRouter>,
      );
      fireEvent.click(screen.getByTestId("outcome-documents-absent-toggle"));
      expect(screen.getByTestId("outcome-doc-annotation")).toHaveTextContent(
        "вид работы: сейчас проектный, нужно исследовательский",
      );
    });
  });

  describe("английский словарь", () => {
    it("тексты переводятся, подписи пака берутся на языке интерфейса", async () => {
      await i18n.changeLanguage("en");
      mount(vkr());
      const op = screen.getByTestId("outcome-doc-operator_manual");
      expect(op).toHaveTextContent("Switched off");
      expect(op).toHaveTextContent("Manuals in the set");
      expect(
        screen.getByTestId("outcome-doc-technical_specification"),
      ).toHaveTextContent("Statement of Work");
      fireEvent.click(screen.getByTestId("outcome-documents-absent-toggle"));
      expect(screen.getByTestId("outcome-doc-annotation")).toHaveTextContent(
        "kind of work: now project, needs research",
      );
      expect(
        screen.getByTestId("outcome-participant-supervisor"),
      ).toHaveTextContent("Set at creation");
      expect(screen.getByTestId("outcome-meta-udc")).toHaveTextContent(
        "At finalization",
      );
    });
  });
});
