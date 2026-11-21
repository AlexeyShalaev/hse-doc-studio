import { useEffect, useMemo } from "react";
import { useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  OutcomeSectionSchema,
  isElementGone,
  packOutcomeKeys,
  usePackOutcome,
  usePackOutcomeExplain,
  usePackOutcomeInputs,
  type OutcomeCheckRule,
  type OutcomeElementRef,
  type OutcomeInput,
  type PackOutcome,
  type PackOutcomeExplain,
  type PackOutcomeRequest,
} from "@entities/pack-studio";
import {
  describeElement,
  type ElementInfo,
} from "@features/pack-outcome/lib/elements";
import { parseSelection, useSpace } from "../context/SpaceContext";
import { useSituation } from "../context/useSituation";
import { useSpaceNav } from "../context/useSpaceNav";
import {
  groupOf,
  stateOf,
  type ElementGroup,
  type ElementState,
} from "./elementGroup";
import { makeWords, type Words } from "./words";

// Всё, что панель «Подробности» знает о выбранном элементе: сам элемент из адреса, результат для
// условий студента, их названия и ответ «почему так». Запросы те же, что у центра «Результата»
// (общий кэш запросов), поэтому лишних обращений к серверу нет.

const EXAMPLE = /^[A-Za-z0-9][A-Za-z0-9_:./-]{0,254}$/;

/** Выбранный элемент из `sel` (`<раздел>:<id>`); незнакомый раздел это «ничего не выбрано». */
export const parseElement = (raw: string | null): OutcomeElementRef | null => {
  const picked = parseSelection(raw);
  if (!picked) return null;
  const section = OutcomeSectionSchema.safeParse(picked.section);
  return section.success ? { section: section.data, id: picked.id } : null;
};

export type DetailsData = {
  element: OutcomeElementRef | null;
  request: PackOutcomeRequest;
  outcome: UseQueryResult<PackOutcome>;
  /** Результат для показа: свежий либо прежний, пока идёт пересчёт. */
  shown: PackOutcome | undefined;
  /** Правила проверок: приходят отдельной частью и нужны, только если выбрана проверка. */
  checks: readonly OutcomeCheckRule[] | undefined;
  inputs: readonly OutcomeInput[] | undefined;
  words: Words;
  explain: UseQueryResult<PackOutcomeExplain>;
  info: ElementInfo | null;
  group: ElementGroup;
  /** Состояние элемента в ответе сервера; `null`, пока ответа нет. */
  state: ElementState | null;
};

export const useDetailsData = (): DetailsData => {
  const { t, i18n } = useTranslation("packSpace");
  const { workspace, versionRef, selection, location } = useSpace();
  const { inputs: chosen, caseId } = useSituation();
  const nav = useSpaceNav();
  const client = useQueryClient();
  const element = useMemo(() => parseElement(selection), [selection]);

  const example = new URLSearchParams(location.search).get("example");
  const validExample =
    example !== null && EXAMPLE.test(example) ? example : null;
  const request = useMemo<PackOutcomeRequest>(
    () => ({
      state: "work_tree",
      scenario: caseId,
      example: validExample,
      inputs: chosen,
    }),
    [caseId, validExample, chosen],
  );

  const outcome = usePackOutcome(workspace.id, versionRef, request);
  const withChecks = usePackOutcome(
    workspace.id,
    versionRef,
    { ...request, include: ["checks"] },
    element?.section === "checks" && outcome.data !== undefined,
  );
  const inputsQuery = usePackOutcomeInputs(
    workspace.id,
    versionRef,
    "work_tree",
  );
  const explain = usePackOutcomeExplain(
    workspace.id,
    versionRef,
    element ? { ...request, element } : null,
  );

  // Элемент исчез (версию или условия поменяли, и его больше нет): результат обновляется молча,
  // выбор снимается, показывать нечего.
  const gone = isElementGone(explain.error);
  useEffect(() => {
    if (!gone) return;
    void client.invalidateQueries({
      queryKey: packOutcomeKeys.version(workspace.id, versionRef),
    });
    nav.go({ sel: null });
  }, [gone, client, workspace.id, versionRef, nav]);

  const inputList = inputsQuery.data?.inputs;
  const words = useMemo(
    () => makeWords(t, i18n.language, inputList),
    [t, i18n.language, inputList],
  );
  const shown = outcome.data;
  const checks = withChecks.data?.checks ?? undefined;
  const named = useMemo(
    () => (shown && checks ? { ...shown, checks } : shown),
    [shown, checks],
  );
  const info = element ? describeElement(named, element, i18n.language) : null;
  return {
    element,
    request,
    outcome,
    shown,
    checks,
    inputs: inputList,
    words,
    explain,
    info,
    group: groupOf(info?.kind ?? "unknown"),
    state: explain.data ? stateOf(explain.data.state) : null,
  };
};
