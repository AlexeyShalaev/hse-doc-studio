import { apiClient } from "@shared/api";
import {
  createDemoRouter,
  demoError,
  demoJson,
  demoNoContent,
  installDemoAdapter,
  type DemoRoute,
} from "@shared/api/demo";
import {
  PackScenarioWriteRequestSchema,
  type PackOutcome,
  type PackOutcomeInputs,
  type PackOutcomeRequest,
  type PackScenarioEntry,
  type PackScenarioList,
  type PackScenarioRun,
  type PackScenarioRunRequest,
} from "../api/outcome";
import type { OutcomeElementRef } from "../api/outcome";
import { explainFor } from "./explain";
import { previewReferenceRoutes } from "./previewRoutes";
import {
  applyReferenceEdits,
  patchReferenceModel,
  readReferenceFile,
  referenceModel,
  writeReferenceFile,
} from "./manifests";
import {
  COURSEWORK_INPUTS,
  COURSEWORK_OUTCOME,
  COURSEWORK_RUN,
  COURSEWORK_SCENARIOS,
  VKR_BRANCHES,
  VKR_CHECKS,
  VKR_INPUTS,
  VKR_OUTCOME,
} from "./fixtures";

// Подмена API результата «на эталонах»: тела ответов это эталоны контракта с подставленным
// адресом (пространство, пак, шаблон, версия) и вводными запроса. Она нужна только в разработке
// и тестах: экран разрабатывается и проверяется на эталонах, не поднимая сервер. По умолчанию
// запросы идут настоящему серверу (эндпоинты `outcome`, срез O2), а «Эталоны» в переключателе
// dev-экрана включает подмену. Вызовы в приложении от этого не меняются: подмена живёт только в
// транспорте axios и в рабочую сборку не попадает.

/** Что подмена отвечает: нормальный ответ или состояние экрана, которое нужно увидеть. */
export type ReferenceBehavior =
  | "normal"
  | "empty"
  | "no_inputs"
  | "no_scenarios"
  | "run_error"
  | "slow"
  | "error"
  | "unreadable";

export const REFERENCE_BEHAVIORS: readonly ReferenceBehavior[] = [
  "normal",
  "empty",
  "no_inputs",
  "no_scenarios",
  "run_error",
  "slow",
  "error",
  "unreadable",
];

export type ReferenceSource = "reference" | "server";

const SOURCE_KEY = "hse-studio.packOutcome.source";
const BEHAVIOR_KEY = "hse-studio.packOutcome.behavior";
const SLOW_MS = 2600;

const read = (key: string): string | null => {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
};
const write = (key: string, value: string): void => {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Без хранилища выбор живёт до перезагрузки: для разработки достаточно.
  }
};

let source: ReferenceSource =
  read(SOURCE_KEY) === "reference" ? "reference" : "server";
let behavior: ReferenceBehavior =
  REFERENCE_BEHAVIORS.find((item) => item === read(BEHAVIOR_KEY)) ?? "normal";
const listeners = new Set<() => void>();
const emit = (): void => {
  listeners.forEach((listener) => {
    listener();
  });
};

/** Переключатель подмены: откуда идут ответы и что они показывают. */
export const outcomeReference = {
  source: (): ReferenceSource => source,
  behavior: (): ReferenceBehavior => behavior,
  setSource: (next: ReferenceSource): void => {
    source = next;
    write(SOURCE_KEY, next);
    emit();
  },
  setBehavior: (next: ReferenceBehavior): void => {
    behavior = next;
    write(BEHAVIOR_KEY, next);
    emit();
  },
  subscribe: (listener: () => void): (() => void) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
};

const sleep = (ms: number): Promise<void> =>
  new Promise((resolve) => {
    setTimeout(resolve, ms);
  });

type Params = { id: string; pack: string; template: string; version: string };

const outcomeFor = (params: Params, body: PackOutcomeRequest): PackOutcome => {
  const base = params.template === "vkr" ? VKR_OUTCOME : COURSEWORK_OUTCOME;
  const scenario = COURSEWORK_SCENARIOS.scenarios.find(
    (entry) => entry.id === body.scenario,
  )?.scenario;
  const out = structuredClone(base);
  out.workspace_id = params.id;
  out.pack = params.pack;
  out.template = params.template;
  out.version = params.version;
  out.state = body.state ?? "work_tree";
  if (body.example) out.example = body.example;
  out.inputs = {
    ...out.inputs,
    ...(scenario?.inputs ?? {}),
    ...(body.inputs ?? {}),
  };
  const include = body.include ?? [];
  const vkr = base === VKR_OUTCOME;
  out.checks = include.includes("checks")
    ? (out.checks ?? (vkr ? structuredClone(VKR_CHECKS) : null))
    : null;
  out.branches = include.includes("branches")
    ? (out.branches ?? (vkr ? structuredClone(VKR_BRANCHES) : null))
    : null;
  if (behavior === "empty") {
    out.documents = [];
    out.meta = [];
    out.forms = [];
    out.participants = [];
    out.points = [];
    out.trace = [];
    out.digest = {
      documents: {},
      participants: [],
      meta_visible: [],
      points: [],
      sections: out.digest.sections.map((print) => ({ ...print, count: 0 })),
    };
  }
  return applyReferenceEdits(
    out,
    params.id,
    params.pack,
    params.template,
    params.version,
  );
};

const inputsFor = (params: Params, state: string | null): PackOutcomeInputs => {
  const out = structuredClone(
    params.template === "vkr" ? VKR_INPUTS : COURSEWORK_INPUTS,
  );
  out.workspace_id = params.id;
  out.pack = params.pack;
  out.template = params.template;
  out.version = params.version;
  if (state === "head" || state === "base" || state === "work_tree") {
    out.state = state;
  }
  if (behavior === "no_inputs") {
    out.inputs = [];
    out.defaults = {};
  }
  return out;
};

// Сценарии «на эталонах» живут в памяти страницы: запись, правка, удаление и прогон работают как
// у сервера (ETag записи, `scenario_taken`, `stale_file`, `record_snapshot`), чтобы экран и тесты
// проходили весь путь «создал, увидел в списке, прогнал» без сервера.
type ScenarioStore = {
  entries: PackScenarioEntry[];
  counter: number;
  /** Сценарии, чей снимок принят после правки правила: на прогоне они совпадают. */
  accepted: Set<string>;
};

const freshStore = (): ScenarioStore => ({
  entries: structuredClone(COURSEWORK_SCENARIOS.scenarios),
  counter: 0,
  accepted: new Set(),
});
let store = freshStore();

const SCENARIO_ID = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const byId = (a: PackScenarioEntry, b: PackScenarioEntry) =>
  a.id < b.id ? -1 : a.id > b.id ? 1 : 0;

/** Состояние сценариев подмены: тесты и галерея сбрасывают и подстраивают его. */
export const scenarioReference = {
  reset: (): void => {
    store = freshStore();
  },
  entries: (): readonly PackScenarioEntry[] => store.entries,
  /** Файл изменили снаружи: ETag записи меняется, чужая правка получит `stale_file`. */
  touch: (id: string): void => {
    const entry = store.entries.find((item) => item.id === id);
    if (entry) {
      store.counter += 1;
      entry.etag = `"ref-${String(store.counter)}"`;
    }
  },
};

const scenariosFor = (params: Params): PackScenarioList => {
  const out = structuredClone({
    ...COURSEWORK_SCENARIOS,
    scenarios: store.entries,
  });
  out.workspace_id = params.id;
  out.pack = params.pack;
  out.template = params.template;
  if (behavior === "no_scenarios") out.scenarios = [];
  return out;
};

const putScenario = (
  params: Params & { scenario: string },
  ifMatch: string | null,
  body: unknown,
) => {
  if (!SCENARIO_ID.test(params.scenario) || params.scenario.length > 64) {
    return demoError(400, "scenario_invalid", "Сценарий не по формату.", {
      reason: "id: lowercase latin letters, digits and dashes only",
    });
  }
  const parsed = PackScenarioWriteRequestSchema.safeParse(body);
  if (!parsed.success) {
    return demoError(422, "model_invalid", "Тело запроса не по схеме.");
  }
  const at = store.entries.findIndex((item) => item.id === params.scenario);
  const current = at === -1 ? undefined : store.entries[at];
  if (ifMatch === null && current) {
    return demoError(409, "scenario_taken", "Сценарий уже есть.", {
      scenario: params.scenario,
    });
  }
  if (ifMatch !== null && !current) {
    return demoError(404, "scenario_not_found", "Сценария нет.", {
      scenario: params.scenario,
    });
  }
  if (ifMatch !== null && current && current.etag !== ifMatch) {
    return demoError(409, "stale_file", "Файл изменён.", {
      etag: current.etag,
      content: "format: 1\n",
    });
  }
  const scenario = structuredClone(parsed.data.scenario);
  if (parsed.data.record_snapshot) {
    scenario.snapshot = structuredClone(COURSEWORK_OUTCOME.digest);
    store.accepted.add(params.scenario);
  }
  store.counter += 1;
  const entry: PackScenarioEntry = {
    id: params.scenario,
    path: `${params.pack}/templates/${params.template}/scenarios/${params.scenario}.yaml`,
    etag: `"ref-${String(store.counter)}"`,
    scenario,
    error: null,
  };
  store.entries = [
    ...store.entries.filter((item) => item.id !== entry.id),
    entry,
  ].sort(byId);
  return demoJson(entry, ifMatch === null ? 201 : 200);
};

const deleteScenario = (
  params: Params & { scenario: string },
  ifMatch: string | null,
) => {
  const current = store.entries.find((item) => item.id === params.scenario);
  if (!current) {
    return demoError(404, "scenario_not_found", "Сценария нет.", {
      scenario: params.scenario,
    });
  }
  if (ifMatch !== null && current.etag !== ifMatch) {
    return demoError(409, "stale_file", "Файл изменён.", {
      etag: current.etag,
      content: "format: 1\n",
    });
  }
  store.entries = store.entries.filter((item) => item.id !== params.scenario);
  return demoNoContent();
};

const runScenarios = (
  params: Params,
  body: PackScenarioRunRequest,
): PackScenarioRun => {
  const chosen = body.scenarios ?? null;
  const fixture = new Map(
    COURSEWORK_RUN.results.map((result) => [result.scenario, result]),
  );
  const results = store.entries
    .filter(
      (entry) =>
        entry.scenario !== null &&
        (chosen === null || chosen.includes(entry.id)),
    )
    .map((entry) => {
      const base = fixture.get(entry.id);
      const expects =
        (entry.scenario?.snapshot ?? null) !== null ||
        (entry.scenario?.assertions?.length ?? 0) > 0;
      if (!expects) {
        return {
          scenario: entry.id,
          status: "unchecked" as const,
          fingerprint: COURSEWORK_OUTCOME.fingerprint,
          failures: [],
          changes: [],
          message: null,
        };
      }
      if (base?.status === "failed" && !store.accepted.has(entry.id)) {
        return structuredClone(base);
      }
      return {
        scenario: entry.id,
        status: "passed" as const,
        fingerprint: COURSEWORK_OUTCOME.fingerprint,
        failures: [],
        changes: [],
        message: null,
      };
    });
  const count = (status: string) =>
    results.filter((result) => result.status === status).length;
  return {
    ...structuredClone(COURSEWORK_RUN),
    workspace_id: params.id,
    pack: params.pack,
    template: params.template,
    version: body.version ?? params.version,
    state: body.state ?? "work_tree",
    passed: count("passed"),
    failed: count("failed"),
    errors: count("error"),
    unchecked: count("unchecked"),
    results,
  };
};

/** Сбой, который автор увидит в баннере экрана: код и текст как у настоящего сервера. */
const failure = () => {
  if (behavior === "unreadable") {
    return demoError(
      422,
      "version_unreadable",
      "Версию шаблона не удалось разобрать.",
      { reason: "version.yaml:12: unknown key `suported_kinds`" },
    );
  }
  if (behavior === "error") {
    return demoError(500, "internal_error", "Внутренняя ошибка.");
  }
  return null;
};

const guarded =
  (
    build: (
      params: Params,
      query: Record<string, string | string[]>,
      body: unknown,
    ) => unknown,
  ): DemoRoute["handler"] =>
  async (req) => {
    if (source === "server") return (await req.forward()) as never;
    if (behavior === "slow") await sleep(SLOW_MS);
    const failed = failure();
    if (failed) return failed;
    const params: Params = {
      id: req.params.id ?? "",
      pack: req.params.pack ?? "",
      template: req.params.template ?? "",
      version: req.params.version ?? "",
    };
    return demoJson(build(params, req.query, req.body));
  };

/** Что подмена отвечает на «Почему?»: ответ, 404 исчезнувшего элемента или 503 занятого сервера. */
export type ExplainBehavior = "normal" | "gone" | "busy" | "fail";

let explainBehavior: ExplainBehavior = "normal";
/** Для тестов и галереи: как отвечает подмена `explain`; `busy` один раз, затем нормально, `fail` пока не сменят. */
export const setExplainBehavior = (next: ExplainBehavior): void => {
  explainBehavior = next;
};

const VERSION =
  "/pack-studio/workspaces/:id/versions/:pack/:template/:version/outcome";
const SCENARIOS =
  "/pack-studio/workspaces/:id/templates/:pack/:template/scenarios";

const VERSION_ROOT =
  "/pack-studio/workspaces/:id/versions/:pack/:template/:version";

// Файлы версии целиком (прежний текст при откате): путь это шесть сегментов у version.yaml и
// восемь у doc.yaml документа; маршрутизатор подмены знает только одиночные сегменты.
const FILE_ROOT = "/pack-studio/workspaces/:id/files";
const SIX = "/:s1/:s2/:s3/:s4/:s5/:s6";
const EIGHT = `${SIX}/:s7/:s8`;
const filePathOf = (params: Record<string, string>): string =>
  ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"]
    .map((key) => params[key])
    .filter((part): part is string => part !== undefined)
    .join("/");
const fileRoutes = (suffix: string): DemoRoute[] => [
  {
    method: "GET",
    pattern: `${FILE_ROOT}${suffix}`,
    handler: (req) => {
      if (source === "server") return req.forward() as never;
      const found = readReferenceFile(
        req.params.id ?? "",
        filePathOf(req.params),
      );
      if (!found) return demoError(404, "file_not_found", "Файла нет.");
      return { status: 200, data: found.text, headers: { etag: found.etag } };
    },
  },
  {
    method: "PUT",
    pattern: `${FILE_ROOT}${suffix}`,
    handler: (req) => {
      if (source === "server") return req.forward() as never;
      const done = writeReferenceFile(
        req.params.id ?? "",
        filePathOf(req.params),
        req.body,
        req.headers?.["if-match"] ?? null,
      );
      if (done.status === 404) {
        return demoError(404, "file_not_found", "Файла нет.");
      }
      if (done.status === 409) {
        return demoError(409, "stale_file", "Файл изменён.", {
          etag: done.etag,
          content: "{}",
        });
      }
      return demoJson({
        path: filePathOf(req.params),
        etag: done.etag,
        size: done.size,
      });
    },
  },
];

export const outcomeReferenceRoutes: DemoRoute[] = [
  ...fileRoutes(SIX),
  ...fileRoutes(EIGHT),
  {
    method: "GET",
    pattern: `${VERSION_ROOT}/model`,
    handler: (req) =>
      source === "server"
        ? (req.forward() as never)
        : demoJson(
            referenceModel(
              req.params.id ?? "",
              req.params.pack ?? "",
              req.params.template ?? "",
              req.params.version ?? "",
            ),
          ),
  },
  {
    method: "PATCH",
    pattern: `${VERSION_ROOT}/model`,
    handler: (req) => {
      if (source === "server") return req.forward() as never;
      const done = patchReferenceModel(
        req.params.id ?? "",
        req.params.pack ?? "",
        req.params.template ?? "",
        req.params.version ?? "",
        req.body,
        req.headers?.["if-match"] ?? null,
      );
      if (done.status === 200) return demoJson(done.model);
      if (done.status === 409) {
        return demoError(409, done.code, "Файл изменён.", {
          etag: done.etag,
          content: "langs: [ru]\n",
        });
      }
      return demoError(422, done.code, "Правку нельзя записать.", {
        reason: done.reason,
      });
    },
  },
  {
    method: "GET",
    pattern: `${VERSION}/inputs`,
    handler: guarded((params, query) => {
      const state = query.state;
      return inputsFor(params, typeof state === "string" ? state : null);
    }),
  },
  {
    method: "POST",
    pattern: VERSION,
    handler: guarded((params, _query, body) =>
      outcomeFor(params, body as PackOutcomeRequest),
    ),
  },
  {
    method: "POST",
    pattern: `${VERSION}/explain`,
    handler: async (req) => {
      if (source === "server") return (await req.forward()) as never;
      if (behavior === "slow") await sleep(SLOW_MS);
      const failed = failure();
      if (failed) return failed;
      if (explainBehavior === "fail") {
        return demoError(500, "internal_error", "Внутренняя ошибка.");
      }
      if (explainBehavior === "busy") {
        explainBehavior = "normal";
        return demoError(503, "outcome_busy", "Сервер занят.", {
          reason: "overloaded",
          retry_after_s: 0,
        });
      }
      const params: Params = {
        id: req.params.id ?? "",
        pack: req.params.pack ?? "",
        template: req.params.template ?? "",
        version: req.params.version ?? "",
      };
      const body = req.body as PackOutcomeRequest & {
        element: OutcomeElementRef;
      };
      const outcome = outcomeFor(params, {
        ...body,
        include: ["checks", "branches"],
      });
      const reply =
        explainBehavior === "gone"
          ? null
          : explainFor(outcome, body.element, params.template);
      if (!reply) {
        return demoError(
          404,
          "outcome_element_not_found",
          "Элемента нет в результате.",
          { section: body.element.section, id: body.element.id },
        );
      }
      return demoJson(reply);
    },
  },
  {
    method: "GET",
    pattern: SCENARIOS,
    handler: guarded((params) => scenariosFor(params)),
  },
  {
    method: "POST",
    pattern: `${SCENARIOS}/run`,
    handler: async (req) => {
      if (source === "server") return (await req.forward()) as never;
      if (behavior === "slow") await sleep(SLOW_MS);
      if (behavior === "run_error") {
        return demoError(503, "outcome_busy", "Сервер занят расчётом.");
      }
      const failed = failure();
      if (failed) return failed;
      return demoJson(
        runScenarios(
          {
            id: req.params.id ?? "",
            pack: req.params.pack ?? "",
            template: req.params.template ?? "",
            version: "",
          },
          req.body as PackScenarioRunRequest,
        ),
      );
    },
  },
  {
    method: "PUT",
    pattern: `${SCENARIOS}/:scenario`,
    handler: (req) =>
      source === "server"
        ? (req.forward() as never)
        : putScenario(
            {
              id: req.params.id ?? "",
              pack: req.params.pack ?? "",
              template: req.params.template ?? "",
              version: "",
              scenario: req.params.scenario ?? "",
            },
            req.headers?.["if-match"] ?? null,
            req.body,
          ),
  },
  {
    method: "DELETE",
    pattern: `${SCENARIOS}/:scenario`,
    handler: (req) =>
      source === "server"
        ? (req.forward() as never)
        : deleteScenario(
            {
              id: req.params.id ?? "",
              pack: req.params.pack ?? "",
              template: req.params.template ?? "",
              version: "",
              scenario: req.params.scenario ?? "",
            },
            req.headers?.["if-match"] ?? null,
          ),
  },
];

let installed = false;

/** Подключить подмену к клиенту API. Повторный вызов ничего не делает. */
export const installOutcomeReference = (): void => {
  if (installed) return;
  installed = true;
  installDemoAdapter(
    apiClient,
    createDemoRouter([
      ...outcomeReferenceRoutes,
      ...previewReferenceRoutes({
        server: () => source === "server",
        failing: () => behavior === "error",
      }),
    ]),
  );
};
