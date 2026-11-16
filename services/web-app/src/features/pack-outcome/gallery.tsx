import type { QueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import {
  packOutcomeKeys,
  packStudioKeys,
  type PackOutcome,
  type PackOutcomeInputs,
  type PackTree,
  type PackVersionRef,
  type PackWorkspace,
} from "@entities/pack-studio";
import {
  COURSEWORK_INPUTS,
  COURSEWORK_OUTCOME,
  COURSEWORK_SCENARIOS,
  VKR_INPUTS,
  VKR_OUTCOME,
} from "@entities/pack-studio/reference";
import { ApiError } from "@shared/api";
import type { GalleryGroup } from "@shared/lib/stateGallery";
import { OutcomeSearchContext, parseOutcomeSearch } from "./lib/urlState";
import { OutcomeBody } from "./OutcomeBody";

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
/** Состояние панели «Вводные»: у неё свой запрос, и он может быть в любом состоянии. */
type InputsKind = "ready" | "loading" | "error" | "none";

/** Заполнить кэш так, чтобы экран видел данные без сервера, и запретить перечитывание. */
const seedWorkspace = (
  client: QueryClient,
  id: string,
  kind: Kind,
  search: string,
  work: Work,
  inputsKind: InputsKind,
  edit?: (outcome: PackOutcome) => void,
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
  client.setQueryData(packOutcomeKeys.scenarios(id, ref.pack, ref.template), {
    ...COURSEWORK_SCENARIOS,
    workspace_id: id,
    pack: ref.pack,
    template: ref.template,
  });
  const key = packOutcomeKeys.result(id, ref, request);
  const scenario = COURSEWORK_SCENARIOS.scenarios.find(
    (entry) => entry.id === url.scenario,
  )?.scenario;
  const outcome = work === "vkr" ? VKR_OUTCOME : COURSEWORK_OUTCOME;
  const base = {
    ...withIdentity(id, outcome),
    state: url.state,
    inputs: { ...outcome.inputs, ...(scenario?.inputs ?? {}), ...url.inputs },
  };
  if (kind === "ready") {
    edit?.(base);
    client.setQueryData(key, base);
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
    id: "po_student",
    title: "Режим «Как студент»",
    note: "Правая панель с правилами скрыта, остаётся то, что видит студент.",
    kind: "ready",
    search: "mode=student",
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
          );
        },
        render: () => (
          <GalleryUrl initial={spec.search ?? ""}>
            <div className="ps-shell ui-console" style={{ minHeight: "40rem" }}>
              <OutcomeBody
                workspace={workspace(id)}
                version={refOf(spec.work ?? "vkr")}
              />
            </div>
          </GalleryUrl>
        ),
      };
    }),
  },
];
