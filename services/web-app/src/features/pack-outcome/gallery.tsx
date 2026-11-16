import type { QueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import {
  packOutcomeKeys,
  packStudioKeys,
  type PackOutcome,
  type PackOutcomeInputs,
  type PackOutcomeRequest,
  type PackTree,
  type PackVersionRef,
  type PackWorkspace,
} from "@entities/pack-studio";
import {
  COURSEWORK_INPUTS,
  COURSEWORK_OUTCOME,
  COURSEWORK_RUN,
  COURSEWORK_SCENARIOS,
  VKR_BRANCHES,
  VKR_CHECKS,
  VKR_INPUTS,
  VKR_OUTCOME,
  explainFor,
} from "@entities/pack-studio/reference";
import { ApiError } from "@shared/api";
import type { GalleryGroup } from "@shared/lib/stateGallery";
import {
  OutcomeSearchContext,
  parseOutcomeSearch,
  type OutcomeSelection,
} from "./lib/urlState";
import { OutcomeBody } from "./OutcomeBody";
import type { ScenarioDialog } from "./ui/scenarios/context";

// Галерея экрана «Результат» (/dev/server-screens): каркас во всех состояниях на эталонах
// контракта, сервер не нужен. Каждая запись живёт в своём пространстве (свой кэш запросов), а
// адрес экрана задан в MemoryRouter: состояние в query видно так же, как в настоящем адресе.
// Телефон (360 px) галерея не показывает, он определяется шириной окна браузера: смотрите
// страницу в узком окне.

const NOW = "2026-11-16T09:30:00Z";
const VKR_REF: PackVersionRef = {
  pack: "hse-cs-se",
  template: "vkr",
  version: "2026.1.2",
};
const COURSEWORK_REF: PackVersionRef = {
  pack: "hse-cs-sse",
  template: "coursework",
  version: "2026.1.6",
};
const VERSION_DIR = "hse-cs-se/templates/vkr/versions";

/** Что показывает запись: ВКР бакалавра или курсовой проект магистратуры (эталоны контракта). */
type Work = "vkr" | "coursework";
const refOf = (work: Work): PackVersionRef =>
  work === "vkr" ? VKR_REF : COURSEWORK_REF;

const workspace = (id: string): PackWorkspace => ({
  id,
  kind: "folder",
  label: "packs",
  state: "ready",
  busy: false,
  packs_path: "packs",
  url: null,
  credential_id: null,
  service_access: false,
  insecure_http: false,
  folder: "/work/hse-doc-studio",
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

const tree = (id: string): PackTree => ({
  workspace_id: id,
  base_sha: null,
  packs: [
    {
      id: "hse-cs-se",
      path: "hse-cs-se",
      name: {
        ru: "ФКН, Программная инженерия",
        en: "CS, Software Engineering",
      },
      templates: [
        {
          id: "vkr",
          path: "hse-cs-se/templates/vkr",
          name: { ru: "ВКР бакалавра", en: "Bachelor thesis" },
          default_version: "2026.1.1",
          versions: [
            {
              version: "2026.1.1",
              path: `${VERSION_DIR}/2026.1.1`,
              status: "stable",
              released: true,
              modified: false,
            },
            {
              version: "2026.1.2",
              path: `${VERSION_DIR}/2026.1.2`,
              status: "beta",
              released: false,
              modified: false,
            },
          ],
        },
      ],
    },
    {
      id: "hse-cs-sse",
      path: "hse-cs-sse",
      name: {
        ru: "ФКН, Системная и программная инженерия",
        en: "CS, Systems and Software Engineering",
      },
      templates: [
        {
          id: "coursework",
          path: "hse-cs-sse/templates/coursework",
          name: { ru: "Курсовой проект", en: "Coursework project" },
          default_version: "2026.1.6",
          versions: [
            {
              version: "2026.1.6",
              path: "hse-cs-sse/templates/coursework/versions/2026.1.6",
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
});

const withIdentity = (id: string, outcome: PackOutcome): PackOutcome => ({
  ...outcome,
  workspace_id: id,
});

type Kind = "ready" | "loading" | "unreadable" | "empty";
/** Состояние «Почему?» выбранного элемента: ответ, ожидание, сбой или занятый сервер. */
type WhyKind = "ready" | "loading" | "error" | "busy";
/** Состояние панели «Вводные»: у неё свой запрос, и он может быть в любом состоянии. */
type InputsKind = "ready" | "loading" | "error" | "none";
/** Сценарии шаблона: есть (в эталоне один файл не разобран), нет; прогон: готов, идёт, не удался. */
type ScenariosKind = "ok" | "empty";
type RunKind = "ready" | "loading" | "failed";

/**
 * «Почему?» выбранного элемента: настоящий ответ ядра, если он записан для этого элемента, иначе
 * ответ, собранный из результата-эталона. У выбранной вводной («Ветки») запроса нет.
 */
const seedWhy = (
  client: QueryClient,
  id: string,
  ref: PackVersionRef,
  request: PackOutcomeRequest,
  selected: OutcomeSelection | null,
  outcome: PackOutcome,
  why: WhyKind,
) => {
  if (!selected || selected.section === "branches") return;
  const element = { section: selected.section, id: selected.id };
  const key = packOutcomeKeys.explain(id, ref, { ...request, element });
  if (why === "loading") {
    void client.prefetchQuery({
      queryKey: key,
      queryFn: () => new Promise<never>(() => undefined),
    });
    return;
  }
  if (why === "error" || why === "busy") {
    client
      .getQueryCache()
      .build(client, { queryKey: key })
      .setState({
        status: "error",
        fetchStatus: "idle",
        data: undefined,
        error:
          why === "busy"
            ? new ApiError("Сервер занят.", "outcome_busy", 503, {
                reason: "overloaded",
                retry_after_s: 2,
              })
            : new ApiError("Внутренняя ошибка.", "internal_error", 500),
        errorUpdateCount: 1,
        errorUpdatedAt: Date.now(),
      });
    return;
  }
  const data = explainFor(outcome, element, ref.template) ?? {
    element,
    state: "present",
    chain: [],
    readers: [],
    counterfactuals: [],
  };
  client.setQueryData(key, { data, etag: null });
};

/** Заполнить кэш так, чтобы экран видел данные без сервера, и запретить перечитывание. */
const seedWorkspace = (
  client: QueryClient,
  id: string,
  kind: Kind,
  search: string,
  work: Work,
  inputsKind: InputsKind,
  edit?: (outcome: PackOutcome) => void,
  parts: "ok" | "error" = "ok",
  why: WhyKind = "ready",
  scenarioKind: ScenariosKind = "ok",
  runKind: RunKind = "ready",
) => {
  const ref = refOf(work);
  const url = parseOutcomeSearch(new URLSearchParams(search));
  const request = {
    state: url.state,
    scenario: url.scenario,
    example: url.example,
    inputs: url.inputs,
  };
  client.setQueryData(packStudioKeys.tree(id), tree(id));
  client.setQueryData(packStudioKeys.workspace(id), workspace(id));
  client.setQueryDefaults(packOutcomeKeys.all(id), {
    retryOnMount: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
    refetchOnWindowFocus: false,
  });
  const inputsKey = packOutcomeKeys.inputs(id, ref, url.state);
  const inputsBase = work === "vkr" ? VKR_INPUTS : COURSEWORK_INPUTS;
  if (inputsKind === "ready" || inputsKind === "none") {
    client.setQueryData(inputsKey, {
      ...inputsBase,
      workspace_id: id,
      ...(inputsKind === "none" ? { inputs: [], defaults: {} } : {}),
    });
  } else if (inputsKind === "loading") {
    void client.prefetchQuery({
      queryKey: inputsKey,
      queryFn: () => new Promise<PackOutcomeInputs>(() => undefined),
    });
  } else {
    client
      .getQueryCache()
      .build(client, { queryKey: inputsKey })
      .setState({
        status: "error",
        fetchStatus: "idle",
        data: undefined,
        error: new ApiError("Внутренняя ошибка.", "internal_error", 500),
        errorUpdateCount: 1,
        errorUpdatedAt: Date.now(),
      });
  }
  const list = structuredClone({
    ...COURSEWORK_SCENARIOS,
    workspace_id: id,
    pack: ref.pack,
    template: ref.template,
  });
  if (scenarioKind === "empty") list.scenarios = [];
  client.setQueryData(
    packOutcomeKeys.scenarios(id, ref.pack, ref.template, url.state),
    list,
  );
  // Прогон сценариев: ждёт `revision` вводных версии, она в эталоне вводных.
  const runKey = packOutcomeKeys.scenarioRun(
    id,
    ref,
    url.state,
    inputsBase.revision,
  );
  if (scenarioKind === "empty") {
    // Без сценариев прогона нет.
  } else if (runKind === "ready") {
    client.setQueryData(runKey, {
      ...structuredClone(COURSEWORK_RUN),
      workspace_id: id,
      pack: ref.pack,
      template: ref.template,
      version: ref.version,
      state: url.state,
    });
  } else if (runKind === "loading") {
    void client.prefetchQuery({
      queryKey: runKey,
      queryFn: () => new Promise<never>(() => undefined),
    });
  } else {
    client
      .getQueryCache()
      .build(client, { queryKey: runKey })
      .setState({
        status: "error",
        fetchStatus: "idle",
        data: undefined,
        error: new ApiError("Сервер занят расчётом.", "outcome_busy", 503),
        errorUpdateCount: 1,
        errorUpdatedAt: Date.now(),
      });
  }
  const key = packOutcomeKeys.result(id, ref, request);
  const scenario = COURSEWORK_SCENARIOS.scenarios.find(
    (entry) => entry.id === url.scenario,
  )?.scenario;
  const outcome = work === "vkr" ? VKR_OUTCOME : COURSEWORK_OUTCOME;
  // Копия целиком: правки записей (`edit`) не должны просачиваться в общий эталон.
  const base: PackOutcome = {
    ...withIdentity(id, structuredClone(outcome)),
    state: url.state,
    inputs: { ...outcome.inputs, ...(scenario?.inputs ?? {}), ...url.inputs },
  };
  if (kind === "ready") {
    edit?.(base);
    client.setQueryData(key, base);
    seedWhy(client, id, ref, request, url.selected, base, why);
    // Правила проверок и ветки приходят отдельными запросами (`include`) раскрытых разделов.
    const partKey = (part: "checks" | "branches") =>
      packOutcomeKeys.result(id, ref, { ...request, include: [part] });
    if (parts === "error") {
      for (const part of ["checks", "branches"] as const) {
        client
          .getQueryCache()
          .build(client, { queryKey: partKey(part) })
          .setState({
            status: "error",
            fetchStatus: "idle",
            data: undefined,
            error: new ApiError("Внутренняя ошибка.", "internal_error", 500),
            errorUpdateCount: 1,
            errorUpdatedAt: Date.now(),
          });
      }
    } else {
      client.setQueryData(partKey("checks"), {
        ...base,
        checks: structuredClone(VKR_CHECKS),
      });
      client.setQueryData(partKey("branches"), {
        ...base,
        branches: structuredClone(VKR_BRANCHES),
      });
    }
  } else if (kind === "empty") {
    client.setQueryData(key, {
      ...base,
      documents: [],
      meta: [],
      forms: [],
      participants: [],
      points: [],
      trace: [],
    });
  } else if (kind === "loading") {
    void client.prefetchQuery({
      queryKey: key,
      queryFn: () => new Promise<PackOutcome>(() => undefined),
    });
  } else {
    client
      .getQueryCache()
      .build(client, { queryKey: key })
      .setState({
        status: "error",
        fetchStatus: "idle",
        data: undefined,
        error: new ApiError(
          "Версию не удалось разобрать.",
          "version_unreadable",
          422,
          {
            reason: "version.yaml:12: unknown key `suported_kinds`",
          },
        ),
        errorUpdateCount: 1,
        errorUpdatedAt: Date.now(),
      });
  }
};

type Spec = {
  id: string;
  title: string;
  note: string;
  kind: Kind;
  /** Query адреса экрана. */
  search?: string;
  /** ВКР (по умолчанию) или курсовой проект. */
  work?: Work;
  /** Состояние запроса вводных (по умолчанию готов). */
  inputs?: InputsKind;
  /** Правка эталона под состояние, которого в эталонах нет (команда, руководитель «нет»). */
  edit?: (outcome: PackOutcome) => void;
  /** Что отвечают запросы правил проверок и веток: данные или сбой. */
  parts?: "ok" | "error";
  /** Что отвечает «Почему?» (по умолчанию ответ). */
  why?: WhyKind;
  /** Сценарии шаблона и их прогон (по умолчанию из эталонов, прогон готов). */
  scenarios?: ScenariosKind;
  run?: RunKind;
  /** Окно сценариев, открытое сразу: список выбора, «Сохранить как сценарий», панель. */
  dialog?: ScenarioDialog;
};

/** Команда из двух: личные документы по авторам, у одного нет редакции на язык проекта. */
const teamOfTwo = (outcome: PackOutcome) => {
  outcome.participants = [
    {
      persona: "author1",
      role: "author",
      name: "Иванов Иван Иванович",
      present: true,
      org: null,
      why: [],
    },
    {
      persona: "author2",
      role: "author",
      name: "Петрова Анна Сергеевна",
      present: true,
      org: null,
      why: [],
    },
    ...outcome.participants.filter((p) => p.role !== "author"),
  ];
  for (const doc of outcome.documents) {
    if (doc.state === "active" && doc.scope === "personal") {
      doc.instances = [
        {
          id: `${doc.id}-1`,
          owner: "author1",
          owner_name: "Иванов",
          file_name: `${doc.name.ru ?? doc.id}_Иванов.pdf`,
        },
        {
          id: `${doc.id}-2`,
          owner: "author2",
          owner_name: "Петрова",
          file_name: `${doc.name.ru ?? doc.id}_Петрова.pdf`,
        },
      ];
    }
    if (doc.id === "pdp_review") doc.lang_state = "fallback";
  }
};

/** Научрук не указан: шаги маршрута с ним остаются без человека. */
const noSupervisor = (outcome: PackOutcome) => {
  for (const p of outcome.participants) {
    if (p.persona === "supervisor") {
      p.present = false;
      p.name = "";
      p.org = null;
    }
  }
  for (const point of outcome.points) {
    for (const step of point.route.steps) {
      for (const person of step) {
        if (person.persona === "supervisor") person.name = "";
      }
    }
  }
};

/**
 * Маршрут с пресетом: консультант подписывает параллельно с научруком, слот академрука пропущен
 * условием, порядок идёт из профиля точки.
 */
const presetRoute = (outcome: PackOutcome) => {
  const pdp = outcome.points.find((p) => p.id === "pdp-application");
  if (!pdp) return;
  const co = outcome.participants.find((x) => x.persona === "co_supervisor");
  if (co) {
    co.present = true;
    co.name = "Сидорова Анна Викторовна";
    co.org = "university";
  }
  const route = pdp.route;
  route.order_source = "profile";
  route.preset = true;
  route.steps = [
    [{ persona: "author", role: "author", name: "Иванов Иван Иванович" }],
    [
      {
        persona: "supervisor",
        role: "supervisor",
        name: "Петров Пётр Петрович",
      },
      {
        persona: "co_supervisor",
        role: "co_supervisor",
        name: "Сидорова Анна Викторовна",
      },
    ],
  ];
  const doc = route.pairs[0]?.doc_id ?? "pdp_assignment";
  route.pairs.push({
    doc_id: doc,
    slot_id: "co_supervisor",
    persona: "co_supervisor",
    source: "preset",
    optional: true,
    when: { person: "co_supervisor", role: null },
    why: [],
  });
  route.may_add = route.may_add.filter(
    (m) => !(m.doc_id === doc && m.slot_id === "co_supervisor"),
  );
  route.skipped = [
    {
      doc_id: doc,
      slot_id: "academic_supervisor",
      when: { person: "supervisor", role: "company" },
      why: [],
    },
  ];
};

const SPECS: Spec[] = [
  {
    id: "po_result",
    title: "Результат ВКР на эталоне",
    note: "Три колонки, верхняя панель, сводка и счётчики секций из ответа сервера.",
    kind: "ready",
  },
  {
    id: "po_loading",
    title: "Первая загрузка",
    note: "Скелет секций и вводных, расчёт ещё идёт.",
    kind: "loading",
  },
  {
    id: "po_unreadable",
    title: "Версия не читается",
    note: "Плашка с причиной от лоадера, переход к исходнику и повтор.",
    kind: "unreadable",
  },
  {
    id: "po_empty",
    title: "В версии нет документов",
    note: "Пустой результат: подсказка и переход к форме версии.",
    kind: "empty",
  },
  {
    id: "po_state_in_url",
    title: "Состояние в адресе",
    note: "Вводные, сценарий и выбранный документ взяты из query: ?scenario=…&i.kind=research&selected=documents:operator_manual.",
    kind: "ready",
    search:
      "scenario=company-supervisor&i.kind=research&i.staffing=team2&selected=documents:operator_manual",
  },
  {
    id: "po_sections_team",
    title: "Секции: команда из двух",
    note: "Документы с экземплярами по авторам и откатом на другой язык, два автора в участниках.",
    kind: "ready",
    search: "selected=documents:pdp_review",
    edit: teamOfTwo,
  },
  {
    id: "po_sections_no_supervisor",
    title: "Секции: руководитель не указан",
    note: "Бледная карточка руководителя и предупреждение о шагах маршрута без человека.",
    kind: "ready",
    search: "selected=participants:supervisor",
    edit: noSupervisor,
  },
  {
    id: "po_sections_points",
    title: "Секции: точки сдачи",
    note: "Карточки точек с пунктами, выключенными пунктами в свёрнутом блоке, дополнительными файлами и ссылкой «К документу».",
    kind: "ready",
    search: "selected=points:final",
  },
  {
    id: "po_sections_route",
    title: "Секции: маршрут с пресетом",
    note: "Дорожка шагов с параллельным шагом, пары с источником и условием, пропущенные и «можно добавить».",
    kind: "ready",
    search: "selected=route:pdp-application/step/2",
    edit: presetRoute,
  },
  {
    id: "po_checks",
    title: "Секция «Проверки»",
    note: "Правила по документам и слоям с движком и серьёзностью, выключенные в свёрнутом блоке, плашка про границы расчёта.",
    kind: "ready",
    search: "selected=checks:gost-7.32-2017/line-spacing",
  },
  {
    id: "po_checks_error",
    title: "Секция «Проверки»: сбой запроса",
    note: "Правила не получены: плашка с причиной и повтором, остальной экран на месте.",
    kind: "ready",
    search: "selected=checks:gost-7.32-2017/line-spacing",
    parts: "error",
  },
  {
    id: "po_branches",
    title: "Секция «Ветки и варианты»",
    note: "Варианты документов, откат языка, что изменится при другом значении вводной, ветка пространства.",
    kind: "ready",
    search: "selected=branches:staffing",
    edit: teamOfTwo,
  },
  {
    id: "po_branches_error",
    title: "Секция «Ветки и варианты»: сбой запроса",
    note: "Варианты и язык показаны из основного расчёта, а блок «что изменится» сообщает о сбое.",
    kind: "ready",
    search: "selected=branches:staffing",
    parts: "error",
  },
  {
    id: "po_why_document_off",
    title: "Почему?: документ выключен",
    note: "Цепочка из четырёх решений на настоящем ответе ядра: правило движка (руководства) не выполнено, у правил манифеста файл, указатель и «Открыть правило», ниже «Что если».",
    kind: "ready",
    search: "selected=documents:operator_manual",
  },
  {
    id: "po_why_document_on",
    title: "Почему?: документ в комплекте",
    note: "Три выполненных решения, одно «что если»: вид работы исследовательский уберёт документ.",
    kind: "ready",
    search: "selected=documents:technical_specification",
  },
  {
    id: "po_why_field_hidden",
    title: "Почему?: поле анкеты скрыто",
    note: "Условие visible_if не выполнено: ответ анкеты «использовали ИИ» не равен «да».",
    kind: "ready",
    search: "selected=forms:ai_declaration/tools",
  },
  {
    id: "po_why_empty_chain",
    title: "Почему?: у элемента нет правил",
    note: "Спокойный текст вместо ошибки: поле проекта не зависит от условий.",
    kind: "ready",
    search: "selected=meta:year",
  },
  {
    id: "po_why_participant_absent",
    title: "Почему?: участника нет в комбинации",
    note: "Пустая цепочка, но «Что если» объясняет, какая вводная его добавит.",
    kind: "ready",
    search: "selected=participants:co_supervisor",
  },
  {
    id: "po_why_route_step",
    title: "Почему?: шаг маршрута",
    note: "Цепочка шага это порядок маршрута и решения пар его людей.",
    kind: "ready",
    search: "selected=route:pdp-application/step/1",
  },
  {
    id: "po_why_route_skipped",
    title: "Почему?: пропущенная пара курсовой",
    note: "Слот консультанта не добавлен: условие when не выполнено, пара absent. Курсовой проект, научрук из ВШЭ.",
    kind: "ready",
    work: "coursework",
    search:
      "selected=route:topic-approval/topic_application/co_supervisor&i.supervisor=university&i.co_supervisor=no&i.academic_supervisor=yes",
  },
  {
    id: "po_why_loading",
    title: "Почему?: загрузка",
    note: "Скелет цепочки, пока сервер не ответил на explain; aria-busy.",
    kind: "ready",
    search: "selected=documents:operator_manual",
    why: "loading",
  },
  {
    id: "po_why_error",
    title: "Почему?: сбой запроса",
    note: "Плашка с причиной и «Повторить», остальной экран на месте.",
    kind: "ready",
    search: "selected=documents:operator_manual",
    why: "error",
  },
  {
    id: "po_why_busy",
    title: "Почему?: сервер занят",
    note: "503 outcome_busy после повторов: отдельный текст и «Повторить».",
    kind: "ready",
    search: "selected=documents:operator_manual",
    why: "busy",
  },
  {
    id: "po_why_impact",
    title: "Влияние вводной",
    note: "У вводной «Вид работы»: сколько элементов в скольких разделах она меняет, сколько правил её читают, списки элементов и правил с переходом к файлу.",
    kind: "ready",
    search: "selected=branches:kind",
  },
  {
    id: "po_student",
    title: "Режим «Как студент»",
    note: "Три упрощённых блока: документы с именами файлов, что заполнить (обязательные поля и анкеты), кто и в каком порядке подписывает. Без причин, источников, пресетов, предупреждений, идентификаторов и правой панели. Alt временно показывает вид автора.",
    kind: "ready",
    search: "mode=student",
  },
  {
    id: "po_student_no_supervisor",
    title: "Режим «Как студент»: руководителя нет",
    note: "Участника, которого нет при этой комбинации, студент не видит: из маршрута пропадает его шаг, предупреждений автора нет.",
    kind: "ready",
    search: "mode=student",
    edit: noSupervisor,
  },
  {
    id: "po_student_team",
    title: "Режим «Как студент»: команда и параллельный шаг",
    note: "Файлы по авторам, шаг с двумя подписантами помечен «параллельно», необязательные подписи словами.",
    kind: "ready",
    search: "mode=student",
    edit: (outcome) => {
      teamOfTwo(outcome);
      presetRoute(outcome);
    },
  },
  {
    id: "po_pale_slots",
    title: "Бледные слоты: «Добавить во вводных»",
    note: "Отсутствующий участник, выключенный и отсутствующий документы, выключенные пункты точек и пропущенные подписи стоят на своих местах бледными, с причиной. «Добавить во вводных» применяет одну вводную из «что если» сервера (здесь для второго руководителя ответ засеян, остальные ходят на сервер).",
    kind: "ready",
    search: "selected=participants:co_supervisor",
  },
  {
    id: "po_base",
    title: "Результат из базы",
    note: "Состояние «База»: сервер без базы ответил бы diff_base_unavailable, здесь данные есть.",
    kind: "ready",
    search: "state=base",
  },
  {
    id: "po_inputs_vkr",
    title: "Вводные: ВКР, значения по умолчанию",
    note: "Панель слева строится из ответа inputs: группы, переключатели, радио, подписи из пака и словаря. Блок «Не влияют» свёрнут, у каждой вводной «Влияет на» и кнопка «Сбросить» (пока отключена).",
    kind: "ready",
  },
  {
    id: "po_inputs_changed",
    title: "Вводные: изменены, подсветка связей",
    note: "Три вводные из адреса отличаются от умолчаний: полоса, пометка «Изменено», «Сбросить» у каждой и «Сбросить всё». «Подсветить N элементов» у вводной показывает связанные элементы из трассы.",
    kind: "ready",
    search: "i.kind=research&i.meta.nda=yes&i.supervisor=company",
  },
  {
    id: "po_inputs_scenario",
    title: "Вводные: сценарий и «изменено относительно сценария»",
    note: "Значения сценария помечены «из сценария», поверх него изменены две вводные: счётчик и «Вернуть сценарий». Быстрый выбор сценария и набор данных внизу.",
    kind: "ready",
    search:
      "scenario=company-supervisor&i.co_supervisor=no&i.kind=research&example=auto%3Along",
  },
  {
    id: "po_inputs_coursework",
    title: "Вводные: курсовой проект",
    note: "Курсовой проект магистратуры из эталонов: сценарий «Научрук из компании», поля select из пака (редакция заявки, поля отчёта) лежат в блоке «Не влияют»: трасса эталона их не читает.",
    kind: "ready",
    work: "coursework",
    search: "scenario=company-supervisor",
  },
  {
    id: "po_scenarios_picker",
    title: "Сценарии: выбор, статусы и итог прогона",
    note: "Список сценариев курсового проекта: значок статуса у каждого, итог «2 совпало, 1 изменилось», «Прогнать все», счётчик «1 из 3» на кнопке.",
    kind: "ready",
    work: "coursework",
    search: "scenario=university-supervisor",
    dialog: { kind: "picker" },
  },
  {
    id: "po_scenarios_empty",
    title: "Сценарии: пока нет",
    note: "Подсказка «Создайте первый сценарий из текущих вводных» с примерами для курсового проекта и ВКР.",
    kind: "ready",
    work: "coursework",
    scenarios: "empty",
    dialog: { kind: "picker" },
  },
  {
    id: "po_scenarios_broken",
    title: "Сценарии: сбой прогона",
    note: "Прогон не удался (сервер занят): плашка с повтором, значки «Не прогнан»; файл draft не разобран и виден с причиной.",
    kind: "ready",
    work: "coursework",
    run: "failed",
    dialog: { kind: "picker" },
  },
  {
    id: "po_scenarios_running",
    title: "Сценарии: идёт прогон",
    note: "Результатов прогона ещё нет: у сценариев «Прогоняю...», кнопка «Прогнать все» отключена.",
    kind: "ready",
    work: "coursework",
    run: "loading",
    dialog: { kind: "picker" },
  },
  {
    id: "po_scenario_create",
    title: "Сценарии: «Сохранить как сценарий»",
    note: "Окно из текущих вводных: название на двух языках, имя файла, версии, снимок и готовые утверждения по результату.",
    kind: "ready",
    work: "coursework",
    search: "i.supervisor=university&i.co_supervisor=no",
    dialog: { kind: "create" },
  },
  {
    id: "po_scenario_panel_failed",
    title: "Сценарии: панель, результат изменился",
    note: "Расхождение по разделам со знаками плюс, тильда, минус, «Принять текущий результат как ожидаемый», правка, дублирование и удаление.",
    kind: "ready",
    work: "coursework",
    search: "scenario=university-supervisor",
    dialog: { kind: "panel", id: "university-supervisor" },
  },
  {
    id: "po_scenario_panel_broken",
    title: "Сценарии: панель битого файла",
    note: "Причина от сервера и переход к файлу.",
    kind: "ready",
    work: "coursework",
    dialog: { kind: "panel", id: "draft" },
  },
  {
    id: "po_scenario_save_inputs",
    title: "Сценарии: «Сохранить в сценарий»",
    note: "Что изменится во вводных сценария, снимок обновляется по галочке.",
    kind: "ready",
    work: "coursework",
    search: "scenario=company-supervisor&i.supervisor=university",
    dialog: { kind: "saveInputs", id: "company-supervisor" },
  },
  {
    id: "po_inputs_loading",
    title: "Вводные: загрузка",
    note: "Скелет панели, пока сервер не ответил на inputs.",
    kind: "ready",
    inputs: "loading",
  },
  {
    id: "po_inputs_error",
    title: "Вводные: ошибка загрузки",
    note: "Не удалось получить вводные версии: ошибка с повтором, остальной экран работает.",
    kind: "ready",
    inputs: "error",
  },
  {
    id: "po_inputs_none",
    title: "Вводные: нет вводных",
    note: "Результат не зависит от вводных (версия с одним документом и одной точкой).",
    kind: "ready",
    inputs: "none",
  },
];

/** Адрес записи в памяти: запись не трогает адрес страницы галереи. */
const GalleryUrl = ({
  initial,
  children,
}: {
  initial: string;
  children: ReactNode;
}) => {
  const [search, setSearch] = useState(initial);
  return (
    <OutcomeSearchContext.Provider
      value={{
        search,
        set: (next) => {
          setSearch(next.toString());
        },
      }}
    >
      {children}
    </OutcomeSearchContext.Provider>
  );
};

export const getPackOutcomeGallery = (): GalleryGroup[] => [
  {
    id: "pack-outcome",
    title: "Студия шаблонов: экран «Результат»",
    description:
      "Каркас экрана на эталонах контракта (contracts/pack-studio/fixtures). Данные в кэше запросов, сервер не нужен.",
    entries: SPECS.map((spec) => {
      const id = `gallery-${spec.id}`;
      return {
        id: spec.id,
        title: spec.title,
        note: spec.note,
        frame: "screen" as const,
        seed: (client: QueryClient) => {
          seedWorkspace(
            client,
            id,
            spec.kind,
            spec.search ?? "",
            spec.work ?? "vkr",
            spec.inputs ?? "ready",
            spec.edit,
            spec.parts,
            spec.why,
            spec.scenarios,
            spec.run,
          );
        },
        render: () => (
          <GalleryUrl initial={spec.search ?? ""}>
            <div className="ps-shell ui-console" style={{ minHeight: "40rem" }}>
              <OutcomeBody
                workspace={workspace(id)}
                version={refOf(spec.work ?? "vkr")}
                scenarioDialog={spec.dialog ?? null}
              />
            </div>
          </GalleryUrl>
        ),
      };
    }),
  },
];
