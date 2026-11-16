import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ApiError } from "@shared/api";
import type {
  OutcomeState,
  PackOutcome,
  PackOutcomeInputs,
  PackOutcomeRequest,
  PackScenarioList,
} from "./outcome";
import { packOutcomeApi } from "./outcomeApi";
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
