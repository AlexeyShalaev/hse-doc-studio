import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { ApiError } from "@shared/api";
import type {
  OutcomeElementRef,
  OutcomeState,
  OutcomeSubject,
  PackOutcome,
  PackOutcomeAtlas,
  PackOutcomeCompare,
  PackOutcomeCompareRequest,
  PackOutcomeExplain,
  PackOutcomeExplainRequest,
  PackOutcomeImpact,
  PackOutcomeImpactRequest,
  PackOutcomeInputs,
  PackOutcomeMatrix,
  PackOutcomeMatrixRequest,
  PackOutcomeRequest,
  PackScenarioEntry,
  PackScenarioList,
  PackScenarioRun,
  PackScenarioWriteRequest,
} from "./outcome";
import {
  packOutcomeApi,
  type OutcomeExplainReply,
  type OutcomeReply,
  type PackOutcomeAtlasRequest,
} from "./outcomeApi";
import type { PackVersionRef } from "./packStudioApi";
import { packStudioKeys } from "./queries";

/**
 * Запрос расчёта в каноническом виде: ключи вводных по алфавиту, пустые части отброшены.
 * Одинаковые по смыслу запросы дают один ключ кэша и один ETag на сервере.
 */
export const normalizeOutcomeRequest = (
  request: PackOutcomeRequest,
): PackOutcomeRequest => {
  const out: PackOutcomeRequest = { state: request.state ?? "work_tree" };
  if (request.scenario) out.scenario = request.scenario;
  if (request.example) out.example = request.example;
  const inputs = Object.entries(request.inputs ?? {}).sort(([a], [b]) =>
    a < b ? -1 : a > b ? 1 : 0,
  );
  if (inputs.length > 0) out.inputs = Object.fromEntries(inputs);
  if (request.include && request.include.length > 0) {
    out.include = [...request.include].sort();
  }
  return out;
};

/** Запрос «Почему?» в каноническом виде: как у расчёта, плюс элемент. */
export const normalizeExplainRequest = (
  request: PackOutcomeExplainRequest,
): PackOutcomeExplainRequest => {
  const { element, ...rest } = request;
  const base = normalizeOutcomeRequest(rest);
  return { ...base, element: { section: element.section, id: element.id } };
};

const byName = ([a]: [string, string], [b]: [string, string]): number =>
  a < b ? -1 : a > b ? 1 : 0;

const sortedInputs = (
  inputs: Record<string, string> | undefined,
): Record<string, string> | undefined => {
  const entries = Object.entries(inputs ?? {}).sort(byName);
  return entries.length > 0 ? Object.fromEntries(entries) : undefined;
};

/** Запрос атласа в каноническом виде: `pin` по алфавиту, пустое отброшено. */
export const normalizeAtlasRequest = (
  request: PackOutcomeAtlasRequest,
): PackOutcomeAtlasRequest => {
  const out: PackOutcomeAtlasRequest = { state: request.state ?? "work_tree" };
  if (request.example) out.example = request.example;
  if (request.scenario) out.scenario = request.scenario;
  const pin = sortedInputs(request.pin);
  if (pin) out.pin = pin;
  return out;
};

/** Сторона сравнения в каноническом виде: одинаковые по смыслу стороны дают один ключ и один ETag. */
export const normalizeSubject = (subject: OutcomeSubject): OutcomeSubject => {
  const out: OutcomeSubject = { state: subject.state ?? "work_tree" };
  if (subject.scenario) out.scenario = subject.scenario;
  if (subject.example) out.example = subject.example;
  const inputs = sortedInputs(subject.inputs);
  if (inputs) out.inputs = inputs;
  return out;
};

export const normalizeCompareRequest = (
  request: PackOutcomeCompareRequest,
): PackOutcomeCompareRequest => ({
  left: normalizeSubject(request.left),
  right: normalizeSubject(request.right),
});

/** «До и после»: база по умолчанию `base`, сценарии по алфавиту (пусто или null: все), атлас по умолчанию включён. */
export const normalizeImpactRequest = (
  request: PackOutcomeImpactRequest,
): PackOutcomeImpactRequest => {
  const out: PackOutcomeImpactRequest = {
    base: request.base ?? "base",
    include_atlas: request.include_atlas ?? true,
  };
  if (request.scenarios && request.scenarios.length > 0) {
    out.scenarios = [...request.scenarios].sort();
  }
  return out;
};

export const normalizeMatrixRequest = (
  request: PackOutcomeMatrixRequest,
): PackOutcomeMatrixRequest => {
  const out: PackOutcomeMatrixRequest = { state: request.state ?? "work_tree" };
  if (request.scenarios && request.scenarios.length > 0) {
    out.scenarios = [...request.scenarios].sort();
  }
  if (request.against) out.against = request.against;
  return out;
};

export const packOutcomeKeys = {
  all: (id: string) => [...packStudioKeys.workspace(id), "outcome"] as const,
  version: (id: string, ref: PackVersionRef) =>
    [...packOutcomeKeys.all(id), ref.pack, ref.template, ref.version] as const,
  inputs: (id: string, ref: PackVersionRef, state: OutcomeState) =>
    [...packOutcomeKeys.version(id, ref), "inputs", state] as const,
  result: (id: string, ref: PackVersionRef, request: PackOutcomeRequest) =>
    [
      ...packOutcomeKeys.version(id, ref),
      "result",
      normalizeOutcomeRequest(request),
    ] as const,
  explain: (
    id: string,
    ref: PackVersionRef,
    request: PackOutcomeExplainRequest,
  ) =>
    [
      ...packOutcomeKeys.version(id, ref),
      "explain",
      normalizeExplainRequest(request),
    ] as const,
  /**
   * Режимы экрана (срез F9): ключи под общим префиксом версии, поэтому `packOutcomeKeys.all(id)` и
   * `version(id, ref)` сбрасывают их вместе с результатом; запись сценария сбрасывает `matrix`,
   * `impact` и `compare`, где участвует сценарий (`refreshScenarioViews`).
   */
  atlas: (id: string, ref: PackVersionRef, request: PackOutcomeAtlasRequest) =>
    [
      ...packOutcomeKeys.version(id, ref),
      "atlas",
      normalizeAtlasRequest(request),
    ] as const,
  compare: (
    id: string,
    ref: PackVersionRef,
    request: PackOutcomeCompareRequest,
  ) =>
    [
      ...packOutcomeKeys.version(id, ref),
      "compare",
      normalizeCompareRequest(request),
    ] as const,
  impact: (
    id: string,
    ref: PackVersionRef,
    request: PackOutcomeImpactRequest,
  ) =>
    [
      ...packOutcomeKeys.version(id, ref),
      "impact",
      normalizeImpactRequest(request),
    ] as const,
  matrix: (
    id: string,
    ref: PackVersionRef,
    request: PackOutcomeMatrixRequest,
  ) =>
    [
      ...packOutcomeKeys.version(id, ref),
      "matrix",
      normalizeMatrixRequest(request),
    ] as const,
  /** Все списки сценариев шаблона (по состояниям): общий префикс для сброса после записи. */
  scenariosAll: (id: string, pack: string, template: string) =>
    [...packOutcomeKeys.all(id), "scenarios", pack, template] as const,
  scenarios: (
    id: string,
    pack: string,
    template: string,
    state: OutcomeState = "work_tree",
  ) => [...packOutcomeKeys.scenariosAll(id, pack, template), state] as const,
  /** Прогон всех сценариев на версии; `revision` вводных версии: правка манифеста даёт новый прогон. */
  scenarioRun: (
    id: string,
    ref: PackVersionRef,
    state: OutcomeState,
    revision: string,
  ) =>
    [
      ...packOutcomeKeys.version(id, ref),
      "scenario-run",
      state,
      revision,
    ] as const,
};

/** Повтор имеет смысл только после сбоя сети и ответа 5xx: отказ 4xx повторится тем же. */
export const retryOutcome = (count: number, error: unknown): boolean =>
  count < 1 &&
  (!(error instanceof ApiError) || error.status === 0 || error.status >= 500);

/** Вводные версии: из них строится левая панель. */
export const usePackOutcomeInputs = (
  id: string,
  ref: PackVersionRef | null,
  state: OutcomeState,
  enabled = true,
) =>
  useQuery<PackOutcomeInputs>({
    queryKey: packOutcomeKeys.inputs(
      id,
      ref ?? { pack: "", template: "", version: "" },
      state,
    ),
    queryFn: ({ signal }) => {
      if (!ref) throw new Error("version is not chosen");
      return packOutcomeApi.inputs(id, ref, state, signal);
    },
    enabled: enabled && ref !== null,
    retry: retryOutcome,
    // Вводные меняются только правкой манифестов; сам ответ несёт `revision`.
    staleTime: 30_000,
  });

/**
 * Результат версии для вводных. Прежний ответ остаётся на экране, пока идёт новый
 * (`isPlaceholderData`): экран пишет «Пересчитываю...» и не мигает. Прежний запрос
 * отменяется сигналом, когда ключ меняется.
 */
export const usePackOutcome = (
  id: string,
  ref: PackVersionRef | null,
  request: PackOutcomeRequest,
  enabled = true,
) =>
  useQuery<PackOutcome>({
    queryKey: packOutcomeKeys.result(
      id,
      ref ?? { pack: "", template: "", version: "" },
      request,
    ),
    queryFn: ({ signal }) => {
      if (!ref) throw new Error("version is not chosen");
      return packOutcomeApi.outcome(
        id,
        ref,
        normalizeOutcomeRequest(request),
        signal,
      );
    },
    enabled: enabled && ref !== null,
    placeholderData: keepPreviousData,
    retry: retryOutcome,
    refetchOnWindowFocus: false,
  });

/** Сценарии шаблона для выбора в верхней панели; `state`: откуда читать файлы. */
export const usePackScenarios = (
  id: string,
  pack: string | null,
  template: string | null,
  enabled = true,
  state: OutcomeState = "work_tree",
) =>
  useQuery<PackScenarioList>({
    queryKey: packOutcomeKeys.scenarios(id, pack ?? "", template ?? "", state),
    queryFn: ({ signal }) => {
      if (pack === null || template === null) {
        throw new Error("template is not chosen");
      }
      return packOutcomeApi.scenarios(id, pack, template, signal, state);
    },
    enabled: enabled && pack !== null && template !== null,
    retry: retryOutcome,
    staleTime: 30_000,
  });

/**
 * Прогон всех сценариев шаблона на версии: статусы, расхождения со снимком и покрытие считает
 * сервер. Ждёт `revision` вводных версии (она меняется с правкой манифеста, и прогон идёт заново);
 * прежний ответ остаётся на экране, пока идёт новый, но только для того же шаблона.
 */
export const usePackScenarioRun = (
  id: string,
  ref: PackVersionRef | null,
  state: OutcomeState,
  revision: string | undefined,
  enabled = true,
) =>
  useQuery<PackScenarioRun>({
    queryKey: packOutcomeKeys.scenarioRun(
      id,
      ref ?? { pack: "", template: "", version: "" },
      state,
      revision ?? "",
    ),
    queryFn: ({ signal }) => {
      if (!ref) throw new Error("version is not chosen");
      return packOutcomeApi.runScenarios(
        id,
        ref.pack,
        ref.template,
        { state, version: ref.version, scenarios: null },
        signal,
      );
    },
    enabled: enabled && ref !== null && revision !== undefined,
    placeholderData: (previous) =>
      previous?.pack === ref?.pack &&
      previous?.template === ref?.template &&
      previous?.version === ref?.version
        ? previous
        : undefined,
    retry: retryOutcome,
    refetchOnWindowFocus: false,
    staleTime: 30_000,
  });

const byId = (a: PackScenarioEntry, b: PackScenarioEntry) =>
  a.id < b.id ? -1 : a.id > b.id ? 1 : 0;

/** После записи: списки сценариев, прогоны и результаты, которые читали этот сценарий, устарели. */
const refreshScenarioViews = (
  client: QueryClient,
  id: string,
  pack: string,
  template: string,
  scenario: string,
  /** Результаты, которые читали сценарий, после правки пересчитываются; после удаления нет. */
  results: boolean,
) => {
  void client.invalidateQueries({
    queryKey: packOutcomeKeys.scenariosAll(id, pack, template),
  });
  void client.invalidateQueries({
    queryKey: packOutcomeKeys.all(id),
    predicate: ({ queryKey }) => {
      if (queryKey[4] !== pack || queryKey[5] !== template) return false;
      // Прогон, матрица и «до и после» считают по всем сценариям шаблона.
      if (
        queryKey[7] === "scenario-run" ||
        queryKey[7] === "matrix" ||
        queryKey[7] === "impact"
      ) {
        return true;
      }
      const request: unknown = queryKey[8];
      if (!results || typeof request !== "object" || request === null) {
        return false;
      }
      if (queryKey[7] === "compare") {
        return [
          "left" in request ? request.left : null,
          "right" in request ? request.right : null,
        ].some(
          (side) =>
            typeof side === "object" &&
            side !== null &&
            "scenario" in side &&
            side.scenario === scenario,
        );
      }
      return (
        (queryKey[7] === "result" ||
          queryKey[7] === "explain" ||
          queryKey[7] === "atlas") &&
        "scenario" in request &&
        request.scenario === scenario
      );
    },
  });
};

export type WritePackScenario = {
  /** Имя файла сценария (`id`). */
  scenario: string;
  body: PackScenarioWriteRequest;
  /** ETag записи при правке; `null`: создание (файла быть не должно). */
  ifMatch: string | null;
};

/** Создание и правка сценария, «принять результат» и «Отменить удаление» (запись без `ifMatch`). */
export const useWritePackScenario = (
  id: string,
  pack: string,
  template: string,
) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ scenario, body, ifMatch }: WritePackScenario) =>
      packOutcomeApi.putScenario(id, pack, template, scenario, body, ifMatch),
    onSuccess: (entry) => {
      // Рабочее дерево видно сразу, остальное дочитается: запись идёт только в него.
      client.setQueryData<PackScenarioList>(
        packOutcomeKeys.scenarios(id, pack, template),
        (list) =>
          list
            ? {
                ...list,
                scenarios: [
                  ...list.scenarios.filter((item) => item.id !== entry.id),
                  entry,
                ].sort(byId),
              }
            : list,
      );
      refreshScenarioViews(client, id, pack, template, entry.id, true);
    },
  });
};

export type DeletePackScenario = { scenario: string; ifMatch: string | null };

/** Мягкое удаление сценария (в git остаётся в истории). */
export const useDeletePackScenario = (
  id: string,
  pack: string,
  template: string,
) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ scenario, ifMatch }: DeletePackScenario) =>
      packOutcomeApi.deleteScenario(id, pack, template, scenario, ifMatch),
    onSuccess: (_, { scenario }) => {
      client.setQueryData<PackScenarioList>(
        packOutcomeKeys.scenarios(id, pack, template),
        (list) =>
          list
            ? {
                ...list,
                scenarios: list.scenarios.filter(
                  (item) => item.id !== scenario,
                ),
              }
            : list,
      );
      refreshScenarioViews(client, id, pack, template, scenario, false);
    },
  });
};

/** Сервер занят (`outcome_busy`, 503): повтор через `retry_after_s` из ответа. */
export const isOutcomeBusy = (error: unknown): boolean =>
  error instanceof ApiError &&
  error.status === 503 &&
  error.code === "outcome_busy";

/** Элемента нет: вводные или версия поменялись, и он исчез из результата (404). */
export const isElementGone = (error: unknown): boolean =>
  error instanceof ApiError &&
  error.status === 404 &&
  error.code === "outcome_element_not_found";

const MAX_BUSY_WAIT_S = 10;

/** Через сколько секунд повторять после `outcome_busy`: из тела ответа, не больше 10 с. */
export const busyDelaySeconds = (error: unknown): number => {
  const raw = error instanceof ApiError ? error.data?.retry_after_s : undefined;
  const seconds = typeof raw === "number" && raw >= 0 ? raw : 1;
  return Math.min(seconds, MAX_BUSY_WAIT_S);
};

const sameElement = (a: OutcomeElementRef, b: OutcomeElementRef): boolean =>
  a.section === b.section && a.id === b.id;

/**
 * «Почему?» одного элемента для вводных. Повтор: сеть и 5xx один раз, занятый сервер
 * (`outcome_busy`) до двух раз через `retry_after_s`; 404 не повторяется (элемент исчез, экран
 * обновит результат). Прежний ответ остаётся на экране, пока идёт новый, но только для того же
 * элемента: чужая цепочка под новым заголовком вводила бы в заблуждение. Тот же ключ при
 * повторном запросе уходит с `If-None-Match` и на 304 берёт прежний ответ.
 */
export const usePackOutcomeExplain = (
  id: string,
  ref: PackVersionRef | null,
  request: PackOutcomeExplainRequest | null,
  enabled = true,
) => {
  const client = useQueryClient();
  const none = { pack: "", template: "", version: "" };
  const key = packOutcomeKeys.explain(
    id,
    ref ?? none,
    request ?? { element: { section: "documents", id: "-" } },
  );
  return useQuery<OutcomeExplainReply, Error, PackOutcomeExplain>({
    queryKey: key,
    queryFn: ({ signal, queryKey }) => {
      if (!ref || !request) throw new Error("element is not chosen");
      const known = client.getQueryData<OutcomeExplainReply>(queryKey) ?? null;
      return packOutcomeApi.explain(
        id,
        ref,
        normalizeExplainRequest(request),
        known,
        signal,
      );
    },
    select: (reply) => reply.data,
    enabled: enabled && ref !== null && request !== null,
    placeholderData: (previous) =>
      previous && request && sameElement(previous.data.element, request.element)
        ? previous
        : undefined,
    retry: (count, error) =>
      isOutcomeBusy(error) ? count < 2 : retryOutcome(count, error),
    retryDelay: (_count, error) =>
      isOutcomeBusy(error) ? busyDelaySeconds(error) * 1000 : 1000,
    refetchOnWindowFocus: false,
    // Ответ зависит только от ключа: свежим он остаётся, пока не сменится `revision`.
    staleTime: 15_000,
  });
};

/** Занятый сервер повторяется до трёх раз через `retry_after_s`; сеть и 5xx один раз; 4xx никогда. */
const retryOutcomeOrBusy = (count: number, error: unknown): boolean =>
  isOutcomeBusy(error) ? count < 3 : retryOutcome(count, error);
const busyRetryDelay = (_count: number, error: unknown): number =>
  isOutcomeBusy(error) ? busyDelaySeconds(error) * 1000 : 1000;

/**
 * Общая основа запросов режимов (атлас, сравнение, матрица, «до и после»): прежний ответ того же
 * ключа уходит условным запросом (`If-None-Match`), на 304 берётся он же; прежние данные другого
 * ключа на экране не остаются (чужая таблица под новым заголовком вводила бы в заблуждение).
 */
const useConditionalOutcome = <T>(
  key: readonly unknown[],
  fetcher: (
    known: OutcomeReply<T> | null,
    signal: AbortSignal,
  ) => Promise<OutcomeReply<T>>,
  enabled: boolean,
) => {
  const client = useQueryClient();
  return useQuery<OutcomeReply<T>, Error, T>({
    queryKey: key,
    queryFn: ({ signal, queryKey }) =>
      fetcher(client.getQueryData<OutcomeReply<T>>(queryKey) ?? null, signal),
    select: (reply) => reply.data,
    enabled,
    retry: retryOutcomeOrBusy,
    retryDelay: busyRetryDelay,
    refetchOnWindowFocus: false,
    staleTime: 15_000,
  });
};

const NO_VERSION: PackVersionRef = { pack: "", template: "", version: "" };
const noVersion = (): Error => new Error("version is not chosen");

/**
 * Атлас версии (режим «Атлас»): измерения, исходы, таблица `{key, outcome}`. Считается секунды, поэтому
 * включается только на открытом режиме (`enabled`). Ошибки: `atlas_too_large`, `outcome_busy`
 * (разбирает `classifyOutcomeFailure`).
 */
export const usePackOutcomeAtlas = (
  id: string,
  ref: PackVersionRef | null,
  request: PackOutcomeAtlasRequest,
  enabled = true,
) =>
  useConditionalOutcome<PackOutcomeAtlas>(
    packOutcomeKeys.atlas(id, ref ?? NO_VERSION, request),
    (known, signal) => {
      if (!ref) throw noVersion();
      return packOutcomeApi.atlas(
        id,
        ref,
        normalizeAtlasRequest(request),
        known,
        signal,
      );
    },
    enabled && ref !== null,
  );

/**
 * Сравнение двух сторон (режим «Сравнить»): `changes` со знаками, причинами `why` и сводкой по
 * разделам. Ошибки: `diff_base_unavailable` (причины `no_git`, `no_base`, `new_version`),
 * `inputs_invalid`, `outcome_busy`.
 */
export const usePackOutcomeCompare = (
  id: string,
  ref: PackVersionRef | null,
  request: PackOutcomeCompareRequest,
  enabled = true,
) =>
  useConditionalOutcome<PackOutcomeCompare>(
    packOutcomeKeys.compare(id, ref ?? NO_VERSION, request),
    (known, signal) => {
      if (!ref) throw noVersion();
      return packOutcomeApi.compare(
        id,
        ref,
        normalizeCompareRequest(request),
        known,
        signal,
      );
    },
    enabled && ref !== null,
  );

/**
 * «До и после»: рабочее дерево против базы по сценариям шаблона и атласу (`summary`, `scenarios`,
 * `new_findings`). Для среза F10 («Предложить изменения»): включается при открытом диалоге
 * (`enabled`), ключ `packOutcomeKeys.impact(id, ref, request)` под общим префиксом версии, поэтому
 * запись сценария и `packOutcomeKeys.all(id)` его сбрасывают. Атлас внутри считается секунды:
 * `include_atlas: false` его пропускает. Ошибки: `diff_base_unavailable`, `outcome_too_large`,
 * `outcome_busy` (повторяется сам до трёх раз), разбор в `classifyOutcomeFailure`.
 */
export const usePackOutcomeImpact = (
  id: string,
  ref: PackVersionRef | null,
  request: PackOutcomeImpactRequest,
  enabled = true,
) =>
  useConditionalOutcome<PackOutcomeImpact>(
    packOutcomeKeys.impact(id, ref ?? NO_VERSION, request),
    (known, signal) => {
      if (!ref) throw noVersion();
      return packOutcomeApi.impact(
        id,
        ref,
        normalizeImpactRequest(request),
        known,
        signal,
      );
    },
    enabled && ref !== null,
  );

/**
 * Матрица «сценарии на разделы» (режим «Матрица»). `against: "base"` добавляет пометки `changed`
 * против базы. Ошибки: `outcome_too_large`, `diff_base_unavailable` (только с `against`), `outcome_busy`.
 */
export const usePackOutcomeMatrix = (
  id: string,
  ref: PackVersionRef | null,
  request: PackOutcomeMatrixRequest,
  enabled = true,
) =>
  useConditionalOutcome<PackOutcomeMatrix>(
    packOutcomeKeys.matrix(id, ref ?? NO_VERSION, request),
    (known, signal) => {
      if (!ref) throw noVersion();
      return packOutcomeApi.matrix(
        id,
        ref,
        normalizeMatrixRequest(request),
        known,
        signal,
      );
    },
    enabled && ref !== null,
  );

/** Почему нет базы для сравнения (`reason` у `diff_base_unavailable`). */
export type DiffBaseReason = "no_git" | "no_base" | "new_version";

/**
 * Отказ вычислителя одним видом: экран решает, что показать (подсказка закрепить вводные, «сравнивать
 * не с чем», «выберите меньше сценариев», «повторить через N с»). Тексты берутся у экрана,
 * подробности (`limit`, `rows`, `reason`) из тела ответа.
 */
export type OutcomeFailure =
  | { kind: "busy"; retryAfterS: number }
  | { kind: "atlas_too_large"; limit: number | null; rows: number | null }
  | { kind: "diff_base_unavailable"; reason: DiffBaseReason | null }
  | { kind: "outcome_too_large"; limit: number | null; size: number | null }
  | {
      kind: "inputs_invalid";
      field: string | null;
      value: string | null;
      reason: string | null;
    }
  | { kind: "unreadable"; reason: string | null }
  | { kind: "offline" }
  | { kind: "server" }
  | { kind: "other" };

const num = (raw: unknown): number | null =>
  typeof raw === "number" && Number.isFinite(raw) ? raw : null;
const str = (raw: unknown): string | null =>
  typeof raw === "string" && raw !== "" ? raw : null;

export const classifyOutcomeFailure = (error: unknown): OutcomeFailure => {
  if (!(error instanceof ApiError)) return { kind: "other" };
  const data = error.data;
  if (isOutcomeBusy(error)) {
    return { kind: "busy", retryAfterS: busyDelaySeconds(error) };
  }
  if (error.code === "atlas_too_large") {
    return {
      kind: "atlas_too_large",
      limit: num(data?.limit),
      rows: num(data?.rows),
    };
  }
  if (error.code === "diff_base_unavailable") {
    const reason = data?.reason;
    return {
      kind: "diff_base_unavailable",
      reason:
        reason === "no_git" || reason === "no_base" || reason === "new_version"
          ? reason
          : null,
    };
  }
  if (error.code === "outcome_too_large") {
    return {
      kind: "outcome_too_large",
      limit: num(data?.limit),
      size: num(data?.size),
    };
  }
  if (error.code === "inputs_invalid") {
    return {
      kind: "inputs_invalid",
      field: str(data?.field),
      value: str(data?.value),
      reason: str(data?.reason),
    };
  }
  if (error.code === "version_unreadable") {
    return { kind: "unreadable", reason: str(data?.reason) };
  }
  if (error.status === 0) return { kind: "offline" };
  if (error.status >= 500) return { kind: "server" };
  return { kind: "other" };
};
