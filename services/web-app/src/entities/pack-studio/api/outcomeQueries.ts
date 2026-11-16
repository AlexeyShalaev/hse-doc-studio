import {
  keepPreviousData,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { ApiError } from "@shared/api";
import type {
  OutcomeElementRef,
  OutcomeState,
  PackOutcome,
  PackOutcomeExplain,
  PackOutcomeExplainRequest,
  PackOutcomeInputs,
  PackOutcomeRequest,
  PackScenarioList,
} from "./outcome";
import { packOutcomeApi, type OutcomeExplainReply } from "./outcomeApi";
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
  scenarios: (id: string, pack: string, template: string) =>
    [...packOutcomeKeys.all(id), "scenarios", pack, template] as const,
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

/** Сценарии шаблона для выбора в верхней панели. */
export const usePackScenarios = (
  id: string,
  pack: string | null,
  template: string | null,
  enabled = true,
) =>
  useQuery<PackScenarioList>({
    queryKey: packOutcomeKeys.scenarios(id, pack ?? "", template ?? ""),
    queryFn: ({ signal }) => {
      if (pack === null || template === null) {
        throw new Error("template is not chosen");
      }
      return packOutcomeApi.scenarios(id, pack, template, signal);
    },
    enabled: enabled && pack !== null && template !== null,
    retry: retryOutcome,
    staleTime: 30_000,
  });

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
