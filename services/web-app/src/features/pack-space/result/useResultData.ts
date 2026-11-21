import { useEffect, useMemo, useState } from "react";
import {
  usePackOutcome,
  usePackOutcomeInputs,
  type OutcomeInput,
  type PackOutcome,
  type PackOutcomeRequest,
} from "@entities/pack-studio";
import { useSpace } from "../context/SpaceContext";
import { readSituation } from "../context/situation";

/** Последнее значение, которое не было пустым: после сбоя расчёта на экране остаётся прежний результат. */
const useKept = <T>(value: T | undefined): T | undefined => {
  const [kept, setKept] = useState<T | undefined>(value);
  if (value !== undefined && value !== kept) setKept(value);
  return value ?? kept;
};

/** После стольких миллисекунд расчёта пишем «Считаю дольше обычного» (раздел 5.10). */
export const SLOW_AFTER_MS = 3000;

export type ResultData = {
  /** Последний полученный результат: при новом расчёте или сбое остаётся прежний. */
  outcome: PackOutcome | undefined;
  /** Подписи и значения условий версии: из них собираются причины. */
  inputs: readonly OutcomeInput[] | undefined;
  /** Первый расчёт ещё не пришёл. */
  pending: boolean;
  /** Идёт расчёт (в том числе повторный после смены условия). */
  calculating: boolean;
  slow: boolean;
  failed: boolean;
  error: unknown;
  /** Показан прежний результат: новый не пришёл или не получился. */
  stale: boolean;
  retry: () => void;
};

/**
 * Результат для условий студента из адреса. Всегда по текущим правкам (`work_tree`): выбора
 * источника на экране больше нет. И оглавление, и центр читают его этим хуком: запрос один,
 * кэш общий.
 */
export const useResultData = (): ResultData => {
  const { workspace, versionRef, version, location } = useSpace();
  const situation = useMemo(
    () => readSituation(location.search),
    [location.search],
  );
  const found = version !== undefined;
  const request: PackOutcomeRequest = {
    state: "work_tree",
    scenario: situation.caseId,
    inputs: situation.inputs,
  };
  const outcome = usePackOutcome(workspace.id, versionRef, request, found);
  const inputs = usePackOutcomeInputs(
    workspace.id,
    versionRef,
    "work_tree",
    found,
  );
  const shown = useKept(outcome.data);
  const calculating = outcome.isFetching;
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!calculating) return undefined;
    const timer = setTimeout(() => {
      setSlow(true);
    }, SLOW_AFTER_MS);
    return () => {
      clearTimeout(timer);
      setSlow(false);
    };
  }, [calculating]);
  return {
    outcome: shown,
    inputs: inputs.data?.inputs,
    pending: outcome.isPending && found,
    calculating,
    slow,
    failed: outcome.isError,
    error: outcome.error,
    stale: outcome.isPlaceholderData || outcome.isError,
    retry: () => void outcome.refetch(),
  };
};
