import { apiClient } from "@shared/api";
import {
  createDemoRouter,
  demoError,
  demoJson,
  installDemoAdapter,
  type DemoRoute,
} from "@shared/api/demo";
import type {
  PackOutcome,
  PackOutcomeInputs,
  PackOutcomeRequest,
  PackScenarioList,
} from "../api/outcome";
import type { OutcomeElementRef } from "../api/outcome";
import { explainFor } from "./explain";
import {
  COURSEWORK_INPUTS,
  COURSEWORK_OUTCOME,
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
  | "slow"
  | "error"
  | "unreadable";

export const REFERENCE_BEHAVIORS: readonly ReferenceBehavior[] = [
  "normal",
  "empty",
  "no_inputs",
  "no_scenarios",
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
  return out;
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

const scenariosFor = (params: Params): PackScenarioList => {
  const out = structuredClone(COURSEWORK_SCENARIOS);
  out.workspace_id = params.id;
  out.pack = params.pack;
  out.template = params.template;
  if (behavior === "no_scenarios") out.scenarios = [];
  return out;
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

export const outcomeReferenceRoutes: DemoRoute[] = [
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
];

let installed = false;

/** Подключить подмену к клиенту API. Повторный вызов ничего не делает. */
export const installOutcomeReference = (): void => {
  if (installed) return;
  installed = true;
  installDemoAdapter(apiClient, createDemoRouter(outcomeReferenceRoutes));
};
