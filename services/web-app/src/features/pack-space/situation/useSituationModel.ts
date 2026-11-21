import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  usePackOutcomeInputs,
  usePackScenarioRun,
  usePackScenarios,
  type OutcomeInput,
  type PackScenarioEntry,
} from "@entities/pack-studio";
import {
  baseValue,
  baselineOf,
  exampleDefaultsOf,
  withValue,
} from "@features/pack-outcome/lib/inputs";
import {
  badgeOf,
  resultsById,
  scenarioName,
  type ScenarioBadge,
} from "@features/pack-outcome/lib/scenarios";
import { useSpace } from "../context/SpaceContext";
import { useSituation } from "../context/useSituation";
import { deltaStore } from "./deltaStore";
import { groupInputs, type InputGroups } from "./topInputs";
import { EXAMPLE_PARAM } from "./useSituationDelta";
import { useSituationLabels } from "./useSituationLabels";

export type SituationModel = {
  status: "loading" | "error" | "ready";
  retry: () => void;
  groups: InputGroups;
  total: number;
  /** Значение условия на экране: изменение из адреса или исходное. */
  valueOf: (input: OutcomeInput) => string;
  /** Исходное значение: готового случая, примера данных или умолчание версии. */
  baseOf: (input: OutcomeInput) => string;
  changedCount: number;
  caseId: string | null;
  cases: readonly PackScenarioEntry[];
  /** Состояние готового случая для значка: совпал ожидаемый результат, «поехал», не прочитан. */
  badge: (entry: PackScenarioEntry) => ScenarioBadge;
  setInput: (input: OutcomeInput, value: string) => void;
  pickCase: (id: string | null) => void;
  reset: () => void;
  /** Есть что сбрасывать: изменённые условия или выбранный случай. */
  dirty: boolean;
  caseName: (id: string) => string;
};

/**
 * Условия студента для полосы: ответ сервера (`inputs`), готовые случаи и их прогон, значения
 * из адреса и запись обратно. Запись одновременно помнит прежнее состояние для плашки
 * «что изменилось». Условий пака здесь нет: всё из ответов сервера.
 */
export const useSituationModel = (): SituationModel => {
  const { workspace, versionRef, location } = useSpace();
  const situation = useSituation();
  const { t, i18n } = useTranslation("packSpace");
  const { inputLabel, valueLabel } = useSituationLabels();
  const inputsQuery = usePackOutcomeInputs(
    workspace.id,
    versionRef,
    "work_tree",
  );
  const scenarios = usePackScenarios(
    workspace.id,
    versionRef.pack,
    versionRef.template,
    true,
    "work_tree",
  );
  const run = usePackScenarioRun(
    workspace.id,
    versionRef,
    "work_tree",
    inputsQuery.data?.revision,
    (scenarios.data?.scenarios.length ?? 0) > 0,
  );
  const example = new URLSearchParams(location.search).get(EXAMPLE_PARAM);
  const data = inputsQuery.data;
  const entries = scenarios.data?.scenarios;
  const { inputs: overrides, caseId } = situation;

  const baseline = useMemo(
    () => (data ? baselineOf(data, scenarios.data, caseId) : null),
    [data, scenarios.data, caseId],
  );
  const exampleDefaults = useMemo(
    () =>
      data ? exampleDefaultsOf(data, example ?? baseline?.example ?? "") : {},
    [data, example, baseline],
  );
  const baseOf = (input: OutcomeInput): string =>
    baseline ? baseValue(input, baseline, exampleDefaults) : input.default;
  const valueOf = (input: OutcomeInput): string =>
    overrides[input.id] ?? baseOf(input);

  const list = data?.inputs ?? [];
  const changedIds = new Set(
    list
      .filter((input) => valueOf(input) !== baseOf(input))
      .map((input) => input.id),
  );

  const scope = `${workspace.id}/${versionRef.pack}/${versionRef.template}/${versionRef.version}`;
  const apply = (
    next: Record<string, string>,
    nextCase: string | null,
    label: string,
  ) => {
    deltaStore.record({
      scope,
      before: { inputs: overrides, caseId },
      after: { inputs: next, caseId: nextCase },
      label,
    });
    situation.setInputs(next, nextCase);
  };

  const caseName = (id: string): string => {
    const entry = entries?.find((item) => item.id === id);
    return entry ? scenarioName(entry, i18n.language) : id;
  };

  return {
    status: inputsQuery.isError
      ? "error"
      : inputsQuery.isPending
        ? "loading"
        : "ready",
    retry: () => void inputsQuery.refetch(),
    groups: groupInputs(list, changedIds),
    total: list.length,
    valueOf,
    baseOf,
    changedCount: changedIds.size,
    caseId,
    cases: entries ?? [],
    badge: (entry) =>
      badgeOf(
        entry,
        resultsById(run.data),
        run.isError ? "failed" : run.data ? "ready" : "loading",
      ),
    setInput: (input, value) => {
      apply(
        withValue(overrides, input.id, value, baseOf(input)),
        caseId,
        `${inputLabel(input)}: ${valueLabel(input, value)}`,
      );
    },
    pickCase: (id) => {
      apply(
        {},
        id,
        id === null
          ? t("situation.delta.noCaseLabel")
          : t("situation.delta.caseLabel", { name: caseName(id) }),
      );
    },
    reset: () => {
      apply({}, null, t("situation.delta.resetLabel"));
    },
    dirty: Object.keys(overrides).length > 0 || caseId !== null,
    caseName,
  };
};
