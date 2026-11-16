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
import { useEffect } from "react";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import {
  packOutcomeKeys,
  packStudioKeys,
  type PackOutcomeInputs,
  type PackTree,
  type PackVersionRef,
  type PackWorkspace,
} from "@entities/pack-studio";
import {
  VKR_INPUTS,
  installOutcomeReference,
  outcomeReference,
} from "@entities/pack-studio/reference";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { installViewport } from "@shared/lib/viewport/testing";
import { OutcomeBody } from "../OutcomeBody";
import { INPUTS_DEBOUNCE_MS } from "../lib/useDraftInputs";

// Панель «Вводные» на эталонах контракта: что рисуется для каждого типа вводной, как выбор
// попадает в адрес (по паузе, одним разом), сброс, блок «Не влияют», сценарии, клавиатура.

const WS = "ws-inputs";
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
      name: { ru: "ФКН" },
      templates: [
        {
          id: "vkr",
          path: "hse-cs-se/templates/vkr",
          name: { ru: "ВКР бакалавра", en: "Bachelor thesis" },
          default_version: "2026.1.2",
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

/** Журнал адресов: каждая смена адреса отдельной строкой, по ним видно число записей. */
const history: string[] = [];
const Probe = () => {
  const { search } = useLocation();
  useEffect(() => {
    history.push(search);
  }, [search]);
  return <output data-testid="location">{search}</output>;
};
const at = <T,>(list: T[], index: number): T => {
  const item = list[index];
  if (item === undefined) throw new Error(`no item at ${String(index)}`);
  return item;
};
const search = () => screen.getByTestId("location").textContent;

type MountOptions = {
  query?: string;
  /** Подменить словарь вводных до первого запроса. */
  inputs?: PackOutcomeInputs;
};

const mount = ({ query = "", inputs }: MountOptions = {}) => {
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
  if (inputs) {
    client.setQueryData(packOutcomeKeys.inputs(WS, REF, "work_tree"), inputs);
  }
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[
          `/pack-studio/w/${WS}/result/hse-cs-se/vkr/2026.1.2${query ? `?${query}` : ""}`,
        ]}
      >
        <OutcomeBody workspace={workspace} version={REF} />
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
};

const panel = async () => {
  await screen.findByTestId("outcome-inputs");
  return screen.getByTestId("outcome-inputs-panel");
};
const row = (id: string) => screen.getByTestId(`outcome-input-${id}`);
const pause = () =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, INPUTS_DEBOUNCE_MS + 80);
  });

describe("панель «Вводные»", () => {
  beforeAll(async () => {
    // Radix Select в jsdom ждёт методов, которых там нет.
    const proto = Element.prototype as unknown as Record<string, unknown>;
    proto.hasPointerCapture ??= () => false;
    proto.setPointerCapture ??= () => undefined;
    proto.releasePointerCapture ??= () => undefined;
    proto.scrollIntoView ??= () => undefined;
    installOutcomeReference();
    // Панель проверяется на эталонах: источник по умолчанию это сервер.
    outcomeReference.setSource("reference");
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    window.localStorage.clear();
    history.length = 0;
  });
  afterEach(async () => {
    cleanup();
    outcomeReference.setSource("reference");
    outcomeReference.setBehavior("normal");
    window.localStorage.clear();
    await i18n.changeLanguage("ru");
  });

  describe("типы вводных", () => {
    it("группы строятся из ответа сервера и называются по-русски", async () => {
      mount();
      await panel();
      for (const group of [
        "project",
        "people",
        "meta",
        "answers",
        "variants",
      ]) {
        const section = screen.queryByTestId(`outcome-inputs-group-${group}`);
        // «Варианты» состоят из вводной без влияния: она уходит в блок «Не влияют».
        if (group === "variants") expect(section).not.toBeInTheDocument();
        else expect(section).toBeInTheDocument();
      }
      expect(
        screen.getByRole("heading", { name: "Проект" }),
      ).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Анкеты" })).toBeVisible();
    });

    it("булева вводная это переключатель с подписью состояния", async () => {
      mount();
      await panel();
      const nda = within(row("meta.nda")).getByRole("switch", {
        name: "Работа под NDA",
      });
      expect(nda).toHaveAttribute("aria-checked", "false");
      expect(row("meta.nda")).toHaveTextContent("Нет");
      fireEvent.click(nda);
      expect(nda).toHaveAttribute("aria-checked", "true");
      expect(row("meta.nda")).toHaveTextContent("Да");
      expect(row("meta.nda")).toHaveAttribute("data-changed", "true");
    });

    it("состав это число авторов: три значения группой радио", async () => {
      mount();
      await panel();
      const group = within(row("staffing")).getByRole("radiogroup", {
        name: "Число авторов",
      });
      const radios = within(group).getAllByRole("radio");
      expect(radios.map((r) => r.textContent)).toEqual([
        "Один автор",
        "Два автора",
        "Три автора",
      ]);
      expect(radios[0]).toBeChecked();
    });

    it("руководитель: из ВШЭ, из компании или без него", async () => {
      mount();
      await panel();
      const supervisor = row("supervisor");
      expect(
        within(supervisor)
          .getAllByRole("radio")
          .map((r) => r.textContent),
      ).toEqual(["Из ВШЭ", "Из компании", "Нет"]);
      expect(
        within(supervisor).getByRole("radio", { name: "Из ВШЭ" }),
      ).toBeChecked();
      // Консультант и академический руководитель: да или нет.
      expect(
        within(row("co_supervisor")).getByRole("switch", {
          name: "Консультант",
        }),
      ).toBeInTheDocument();
    });

    it("поле пака с подписью из пака: значения как в словаре версии", async () => {
      mount();
      await panel();
      const manuals = row("meta.manuals");
      expect(
        within(manuals).getByRole("radiogroup", {
          name: "Руководства в комплекте",
        }),
      ).toBeInTheDocument();
      expect(
        within(manuals).getByRole("radio", { name: "Только программиста" }),
      ).toBeInTheDocument();
    });

    it("ответ анкеты: подписи значений берутся из пака", async () => {
      mount();
      await panel();
      const answer = row("answer.ai_declaration.used_ai");
      expect(
        within(answer).getByRole("radio", { name: "Я не использовал(а) ИИ" }),
      ).toBeChecked();
      expect(
        within(answer).getByRole("radio", { name: "Я использовал(а) ИИ" }),
      ).not.toBeChecked();
    });

    it("вариант документа лежит в блоке «Не влияют» и открывается там", async () => {
      mount();
      await panel();
      expect(
        screen.queryByTestId("outcome-input-variant.presentation"),
      ).not.toBeInTheDocument();
      fireEvent.click(screen.getByTestId("outcome-inputs-inert-toggle"));
      const variant = row("variant.presentation");
      expect(
        within(variant).getByRole("radio", { name: "PowerPoint-шаблон" }),
      ).toBeChecked();
      expect(
        within(variant)
          .getAllByRole("radio")
          .map((r) => r.textContent),
      ).toEqual(["PowerPoint-шаблон", "RevealJS (HTML)", "LaTeX Beamer"]);
    });

    it("больше четырёх значений: выпадающий список с подписью вводной", async () => {
      const long = structuredClone(VKR_INPUTS);
      long.workspace_id = WS;
      long.inputs.push({
        id: "meta.edition",
        group: "meta",
        type: "select",
        label: { ru: "Редакция", en: "Edition" },
        values: ["a", "b", "c", "d", "e"].map((value) => ({
          value,
          label: { ru: `Редакция ${value}`, en: `Edition ${value}` },
        })),
        default: "a",
        affects: ["documents"],
        rules: 1,
      });
      long.defaults["meta.edition"] = "a";
      mount({ inputs: long });
      await panel();
      const edition = row("meta.edition");
      expect(within(edition).queryByRole("radio")).not.toBeInTheDocument();
      expect(
        within(edition).getByRole("combobox", { name: "Редакция" }),
      ).toHaveTextContent("Редакция a");
    });

    it("подписи по-английски: пак и словарь интерфейса", async () => {
      await i18n.changeLanguage("en");
      mount();
      await panel();
      expect(
        screen.getByRole("region", { name: "Inputs" }),
      ).toBeInTheDocument();
      expect(
        within(row("staffing")).getByRole("radio", { name: "Two authors" }),
      ).toBeInTheDocument();
      expect(
        within(row("supervisor")).getByRole("radio", {
          name: "From a company",
        }),
      ).toBeInTheDocument();
      expect(
        within(row("meta.nda")).getByRole("switch", { name: "NDA work" }),
      ).toBeInTheDocument();
      expect(
        within(row("answer.ai_declaration.used_ai")).getByRole("radio", {
          name: "I used AI",
        }),
      ).toBeInTheDocument();
      expect(screen.getByTestId("outcome-inputs-reset")).toHaveTextContent(
        "Reset all",
      );
    });
  });

  describe("запись в адрес", () => {
    it("выбор виден сразу, а в адрес попадает по паузе одной записью", async () => {
      mount();
      await panel();
      const before = history.length;
      const staffing = row("staffing");
      fireEvent.click(
        within(staffing).getByRole("radio", { name: "Два автора" }),
      );
      fireEvent.click(
        within(staffing).getByRole("radio", { name: "Три автора" }),
      );
      // Контрол уже показывает выбор, адрес ещё прежний.
      expect(
        within(staffing).getByRole("radio", { name: "Три автора" }),
      ).toBeChecked();
      expect(search()).toBe("");
      await waitFor(() => {
        expect(search()).toBe("?i.staffing=team3");
      });
      // Промежуточное «team2» в адрес не попало, запись одна.
      expect(history.slice(before)).toEqual(["?i.staffing=team3"]);
    });

    it("возврат к исходному значению убирает его из адреса", async () => {
      mount({ query: "i.kind=research" });
      await panel();
      fireEvent.click(
        within(row("kind")).getByRole("radio", { name: "Проектная" }),
      );
      await waitFor(() => {
        expect(search()).toBe("");
      });
    });

    it("адрес восстанавливает выбор в контролах", async () => {
      mount({ query: "i.supervisor=company&i.meta.nda=yes" });
      await panel();
      expect(
        within(row("supervisor")).getByRole("radio", { name: "Из компании" }),
      ).toBeChecked();
      expect(within(row("meta.nda")).getByRole("switch")).toHaveAttribute(
        "aria-checked",
        "true",
      );
      expect(row("supervisor")).toHaveAttribute("data-changed", "true");
      expect(row("staffing")).not.toHaveAttribute("data-changed");
    });

    it("остальные строки не перерисовываются при выборе в одной", async () => {
      mount();
      await panel();
      const other = row("meta.manuals");
      fireEvent.click(
        within(row("staffing")).getByRole("radio", { name: "Два автора" }),
      );
      expect(row("meta.manuals")).toBe(other);
      await pause();
    });
  });

  describe("сброс", () => {
    it("«Сбросить» у вводной возвращает исходное значение сразу", async () => {
      mount({ query: "i.staffing=team2&i.kind=research" });
      await panel();
      const reset = within(row("staffing")).getByRole("button", {
        name: "Сбросить: Число авторов",
      });
      expect(reset).toBeEnabled();
      fireEvent.click(reset);
      expect(search()).toBe("?i.kind=research");
      expect(
        within(row("staffing")).getByRole("button", {
          name: "Сбросить: Число авторов",
        }),
      ).toBeDisabled();
    });

    it("у вводной без изменений кнопка «Сбросить» есть, но отключена", async () => {
      mount();
      await panel();
      expect(
        within(row("kind")).getByRole("button", {
          name: "Сбросить: Вид работы",
        }),
      ).toBeDisabled();
    });

    it("«Сбросить всё» чистит вводные и набор данных, остальное в адресе остаётся", async () => {
      mount({
        query: "state=head&i.kind=research&i.staffing=team3&example=auto:long",
      });
      await panel();
      const all = screen.getByTestId("outcome-inputs-reset");
      expect(all).toBeEnabled();
      fireEvent.click(all);
      expect(search()).toBe("?state=head");
      expect(all).toBeDisabled();
    });

    it("«Сбросить всё» отменяет выбор, который ещё не записан", async () => {
      mount();
      await panel();
      fireEvent.click(
        within(row("kind")).getByRole("radio", { name: "Исследовательская" }),
      );
      fireEvent.click(within(row("meta.nda")).getByRole("switch"));
      expect(screen.getByTestId("outcome-inputs-reset")).toBeEnabled();
      // Ничего не записано: сбрасывать в адресе нечего, но выбор должен исчезнуть.
      fireEvent.click(screen.getByTestId("outcome-inputs-reset"));
      await pause();
      expect(search()).toBe("");
      expect(
        within(row("kind")).getByRole("radio", { name: "Проектная" }),
      ).toBeChecked();
    });
  });

  describe("«Не влияют»", () => {
    it("блок свёрнут, показывает число и объяснение при раскрытии", async () => {
      mount();
      await panel();
      const toggle = screen.getByTestId("outcome-inputs-inert-toggle");
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(toggle).toHaveTextContent("Не влияют");
      expect(toggle).toHaveTextContent("2");
      fireEvent.click(toggle);
      expect(toggle).toHaveAttribute("aria-expanded", "true");
      // Язык читают правила, но разделы не меняются; у варианта правил нет вовсе.
      expect(row("lang")).toHaveTextContent("Читают правил: 21");
      expect(row("lang")).toHaveAttribute("data-inert", "true");
      expect(row("variant.presentation")).toHaveTextContent(
        "Ничего не меняет в результате.",
      );
      expect(
        window.localStorage.getItem("hse-studio.packOutcome.inputs.inert.open"),
      ).toBe("1");
    });

    it("влияющие вводные показывают, на что влияют", async () => {
      mount();
      await panel();
      expect(row("kind")).toHaveTextContent(
        "Влияет на: Документы, Метаданные проекта, Точки сдачи, Маршрут подписания",
      );
      expect(row("kind")).toHaveTextContent("Читают правил: 21");
      expect(row("kind")).not.toHaveAttribute("data-inert");
    });

    it("изменённая вводная в свёрнутом блоке видна счётчиком", async () => {
      mount({ query: "i.lang=en" });
      await panel();
      const toggle = screen.getByTestId("outcome-inputs-inert-toggle");
      expect(toggle).toHaveTextContent("Не влияют");
      expect(
        within(toggle).getByTitle("Есть изменённые вводные"),
      ).toHaveTextContent("1");
    });
  });

  describe("связи с результатом", () => {
    it("клик по вводной подсвечивает связанные элементы из трассы", async () => {
      mount();
      await panel();
      await screen.findByTestId("outcome-count-documents");
      const button = within(row("meta.nda")).getByTestId(
        "outcome-input-meta.nda-highlight",
      );
      // Решение про NDA в трассе одно: связан один элемент.
      expect(button).toHaveTextContent("Подсветить 1 элемент");
      expect(button).toHaveAttribute("aria-pressed", "false");
      fireEvent.click(button);
      expect(button).toHaveAttribute("aria-pressed", "true");
      expect(row("meta.nda")).toHaveAttribute("data-highlighted", "true");
      const links = screen.getByTestId("outcome-input-meta.nda-links");
      expect(within(links).getAllByRole("listitem")).toHaveLength(1);
      fireEvent.click(at(within(links).getAllByRole("button"), 0));
      expect(search()).toMatch(/selected=/);
      fireEvent.click(button);
      expect(
        screen.queryByTestId("outcome-input-meta.nda-links"),
      ).not.toBeInTheDocument();
    });

    it("без связей в трассе кнопки подсветки нет", async () => {
      mount();
      await panel();
      await screen.findByTestId("outcome-count-documents");
      // Руководитель в трассе эталона не читается: догадок нет.
      expect(
        screen.queryByTestId("outcome-input-supervisor-highlight"),
      ).not.toBeInTheDocument();
    });
  });

  describe("сценарии и набор данных", () => {
    it("сценарий задаёт исходные значения, отличие от умолчания помечено", async () => {
      mount({ query: "scenario=company-supervisor" });
      await panel();
      await screen.findByTestId("outcome-count-documents");
      expect(
        within(row("supervisor")).getByRole("radio", { name: "Из компании" }),
      ).toBeChecked();
      // Значение пришло из сценария: не «Изменено», а «из сценария»; сбрасывать нечего.
      expect(row("supervisor")).not.toHaveAttribute("data-changed");
      expect(row("supervisor")).toHaveTextContent("из сценария");
      expect(
        screen.queryByTestId("outcome-inputs-dirty"),
      ).not.toBeInTheDocument();
    });

    it("изменение поверх сценария считается и возвращается кнопкой", async () => {
      mount({
        query: "scenario=company-supervisor&i.supervisor=none&i.kind=research",
      });
      await panel();
      const dirty = screen.getByTestId("outcome-inputs-dirty");
      expect(dirty).toHaveTextContent(
        "Изменено 2 вводные относительно сценария",
      );
      fireEvent.click(screen.getByTestId("outcome-inputs-restore"));
      expect(search()).toBe("?scenario=company-supervisor");
      expect(
        screen.queryByTestId("outcome-inputs-dirty"),
      ).not.toBeInTheDocument();
      expect(
        within(row("supervisor")).getByRole("radio", { name: "Из компании" }),
      ).toBeChecked();
    });

    it("«Сбросить» у вводной возвращает значение сценария, а не умолчание версии", async () => {
      mount({ query: "scenario=company-supervisor&i.supervisor=none" });
      await panel();
      fireEvent.click(
        within(row("supervisor")).getByRole("button", {
          name: "Сбросить: Научный руководитель",
        }),
      );
      expect(search()).toBe("?scenario=company-supervisor");
    });

    it("значение, равное значению сценария, из адреса убирается", async () => {
      mount({ query: "scenario=company-supervisor&i.supervisor=none" });
      await panel();
      fireEvent.click(
        within(row("supervisor")).getByRole("radio", { name: "Из компании" }),
      );
      await waitFor(() => {
        expect(search()).toBe("?scenario=company-supervisor");
      });
    });

    it("быстрый выбор сценария пишется в адрес, «без сценария» убирает", async () => {
      const user = userEvent.setup();
      mount();
      await panel();
      const quick = screen.getByRole("combobox", {
        name: "Быстрый выбор сценария",
      });
      await user.click(quick);
      await user.click(
        await screen.findByRole("option", {
          name: "Без научного руководителя",
        }),
      );
      expect(search()).toBe("?scenario=no-supervisor");
      await user.click(quick);
      await user.click(
        await screen.findByRole("option", {
          name: "Без сценария (свободные вводные)",
        }),
      );
      expect(search()).toBe("");
    });

    it("набор данных: выбор пишется в адрес, умолчание убирает", async () => {
      const user = userEvent.setup();
      mount();
      await panel();
      const example = screen.getByRole("combobox", { name: "Набор данных" });
      expect(example).toHaveTextContent("Обычный");
      await user.click(example);
      await user.click(
        await screen.findByRole("option", { name: "Длинные значения" }),
      );
      expect(search()).toBe("?example=auto%3Along");
      fireEvent.click(screen.getByTestId("outcome-inputs-example-reset"));
      expect(search()).toBe("");
    });
  });

  describe("состояния", () => {
    it("первая загрузка: скелет, не пустое место", () => {
      mount();
      expect(screen.getByTestId("outcome-inputs-loading")).toHaveAttribute(
        "aria-busy",
        "true",
      );
    });

    it("нет вводных: сообщение вместо групп", async () => {
      outcomeReference.setBehavior("no_inputs");
      mount();
      expect(
        await screen.findByTestId("outcome-inputs-empty"),
      ).toHaveTextContent("Результат не зависит от вводных");
    });

    it("не загрузились: ошибка с повтором, после починки панель строится", async () => {
      outcomeReference.setBehavior("error");
      mount();
      const error = await screen.findByTestId("outcome-inputs-error");
      expect(error).toHaveAttribute("role", "alert");
      outcomeReference.setBehavior("normal");
      fireEvent.click(within(error).getByRole("button", { name: "Повторить" }));
      expect(await screen.findByTestId("outcome-inputs")).toBeInTheDocument();
    });

    it("все вводные без влияния: панель так и говорит", async () => {
      const flat = structuredClone(VKR_INPUTS);
      flat.workspace_id = WS;
      flat.inputs = flat.inputs.map((input) => ({ ...input, affects: [] }));
      mount({ inputs: flat });
      await panel();
      expect(screen.getByTestId("outcome-inputs-all-inert")).toHaveTextContent(
        "Ни одна вводная не меняет результат",
      );
    });

    it("свёрнутая группа помнит состояние", async () => {
      mount();
      await panel();
      const group = screen.getByTestId("outcome-inputs-group-people");
      const toggle = at(
        within(group).getAllByRole("button", { expanded: true }),
        0,
      );
      fireEvent.click(toggle);
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(
        window.localStorage.getItem(
          "hse-studio.packOutcome.inputs.group.people",
        ),
      ).toBe("1");
    });
  });

  describe("клавиатура и доступность", () => {
    it("радио: один вход в порядок Tab, стрелки, Home и End выбирают значение", async () => {
      mount();
      await panel();
      const radios = within(row("staffing")).getAllByRole("radio");
      expect(radios.map((r) => r.getAttribute("tabindex"))).toEqual([
        "0",
        "-1",
        "-1",
      ]);
      radios[0]?.focus();
      fireEvent.keyDown(at(radios, 0), { key: "ArrowRight" });
      expect(radios[1]).toBeChecked();
      expect(radios[1]).toHaveFocus();
      expect(radios.map((r) => r.getAttribute("tabindex"))).toEqual([
        "-1",
        "0",
        "-1",
      ]);
      fireEvent.keyDown(at(radios, 1), { key: "End" });
      expect(radios[2]).toBeChecked();
      fireEvent.keyDown(at(radios, 2), { key: "ArrowRight" });
      expect(radios[0]).toBeChecked();
      fireEvent.keyDown(at(radios, 0), { key: "ArrowUp" });
      expect(radios[2]).toBeChecked();
      fireEvent.keyDown(at(radios, 2), { key: "Home" });
      expect(radios[0]).toBeChecked();
      await pause();
    });

    it("переключатель работает с клавиши Space и Enter", async () => {
      const user = userEvent.setup();
      mount();
      await panel();
      const nda = within(row("meta.nda")).getByRole("switch");
      nda.focus();
      await user.keyboard(" ");
      expect(nda).toHaveAttribute("aria-checked", "true");
      await user.keyboard("{Enter}");
      expect(nda).toHaveAttribute("aria-checked", "false");
      await pause();
    });

    it("Tab идёт по строке: сброс, значение, подсветка; отключённый сброс пропускается", async () => {
      const user = userEvent.setup();
      mount({ query: "i.kind=research" });
      await panel();
      await screen.findByTestId("outcome-count-documents");
      const kind = row("kind");
      const reset = within(kind).getByRole("button", {
        name: "Сбросить: Вид работы",
      });
      reset.focus();
      await user.tab();
      // Из группы радио в порядок обхода входит только выбранная кнопка.
      expect(
        within(kind).getByRole("radio", { name: "Исследовательская" }),
      ).toHaveFocus();
      await user.tab();
      expect(
        within(kind).getByTestId("outcome-input-kind-highlight"),
      ).toHaveFocus();
      await user.tab();
      // Следующая строка: сброс у неё отключён, фокус сразу на значении.
      expect(
        within(row("staffing")).getByRole("radio", { name: "Один автор" }),
      ).toHaveFocus();
    });

    it("у каждой строки есть имя и описание для читалки", async () => {
      mount();
      await panel();
      const kind = row("kind");
      expect(kind).toHaveAccessibleName("Вид работы");
      const group = within(kind).getByRole("radiogroup");
      expect(group).toHaveAccessibleName("Вид работы");
      expect(group).toHaveAccessibleDescription(/Влияет на: Документы/);
    });

    it("aria-live объявляет, что результат пересчитывается", async () => {
      mount();
      await panel();
      const live = screen.getByTestId("outcome-inputs-live");
      expect(live).toHaveAttribute("aria-live", "polite");
      fireEvent.click(
        within(row("staffing")).getByRole("radio", { name: "Два автора" }),
      );
      expect(live).toHaveTextContent("Результат пересчитывается");
      await waitFor(() => {
        expect(live).toBeEmptyDOMElement();
      });
    });
  });

  describe("телефон", () => {
    let viewport: ReturnType<typeof installViewport>;
    beforeEach(() => {
      viewport = installViewport(360);
    });
    afterEach(() => {
      viewport.restore();
    });

    it("лист «Вводные»: выбор по паузе не пишется, кнопка «Показать» применяет и закрывает лист", async () => {
      mount({ query: "tab=inputs" });
      const sheet = await screen.findByRole("dialog");
      await within(sheet).findByTestId("outcome-inputs");
      fireEvent.click(within(sheet).getByRole("radio", { name: "Два автора" }));
      await pause();
      expect(search()).toBe("?tab=inputs");
      fireEvent.click(within(sheet).getByTestId("outcome-inputs-apply"));
      expect(search()).toBe("?i.staffing=team2");
    });

    it("«Показать» без выбора просто закрывает лист", async () => {
      mount({ query: "tab=inputs" });
      const sheet = await screen.findByRole("dialog");
      fireEvent.click(await within(sheet).findByTestId("outcome-inputs-apply"));
      expect(search()).toBe("");
    });
  });
});
