import { useCallback, useMemo, useSyncExternalStore } from "react";
import {
  usePackOutcomeCompare,
  type OutcomeSubject,
  type PackOutcomeCompareRequest,
} from "@entities/pack-studio";
import { useSpace } from "../context/SpaceContext";
import { useSituation } from "../context/useSituation";
import { useSpaceNav } from "../context/useSpaceNav";
import {
  changedElements,
  summarizeDelta,
  type ChangeSymbol,
  type DeltaSummary,
} from "./deltaSummary";
import { deltaStore, type SituationSnapshot } from "./deltaStore";

/** Параметр адреса: показывать только то, что изменилось (`delta=1`). */
export const DELTA_ONLY_PARAM = "delta";
export const EXAMPLE_PARAM = "example";

const NO_CHANGES: ReadonlyMap<string, ChangeSymbol> = new Map();

const sameSnapshot = (a: SituationSnapshot, b: SituationSnapshot): boolean => {
  const keys = Object.keys(a.inputs);
  return (
    a.caseId === b.caseId &&
    keys.length === Object.keys(b.inputs).length &&
    keys.every((key) => a.inputs[key] === b.inputs[key])
  );
};

const subjectOf = (
  side: SituationSnapshot,
  example: string | null,
): OutcomeSubject => ({
  state: "work_tree",
  ...(side.caseId === null ? {} : { scenario: side.caseId }),
  ...(example === null ? {} : { example }),
  inputs: side.inputs,
});

export type SituationDelta = {
  /** Условие менялось, и адрес с тех пор остался тем же: есть что показать. */
  active: boolean;
  /** Что сделал человек словами: «Работа под NDA: Да». */
  label: string;
  status: "idle" | "loading" | "error" | "ready";
  summary: DeltaSummary | null;
  /** Изменившиеся элементы результата: ключ `<раздел>:<id>` как у `sel`, знак изменения. */
  changed: ReadonlyMap<string, ChangeSymbol>;
  /** Строки подсвечены (несколько секунд после изменения). */
  highlight: boolean;
  /** Центр показывает только изменившееся (`delta=1`). */
  onlyChanged: boolean;
  retry: () => void;
  /** Скрыть плашку и подсветку. */
  dismiss: () => void;
  /** Включить или выключить «только изменившееся». */
  toggleOnly: () => void;
};

/**
 * Что изменилось после смены условия студента (pack-studio-ux.md, 5.3). Плашку рисует
 * `situation`, а строки результата берут отсюда `changed`, `highlight` и `onlyChanged`: запрос
 * сравнения у всех один (общий кэш).
 */
export const useSituationDelta = (): SituationDelta => {
  const { workspace, versionRef, location } = useSpace();
  const now = useSituation();
  const nav = useSpaceNav();
  const record = useSyncExternalStore(
    deltaStore.subscribe,
    deltaStore.get,
    deltaStore.get,
  );
  const scope = `${workspace.id}/${versionRef.pack}/${versionRef.template}/${versionRef.version}`;
  const params = new URLSearchParams(location.search);
  const example = params.get(EXAMPLE_PARAM);
  const onlyParam = params.get(DELTA_ONLY_PARAM) === "1";
  const active =
    record !== null &&
    record.scope === scope &&
    !record.dismissed &&
    sameSnapshot(record.after, { inputs: now.inputs, caseId: now.caseId });

  const request = useMemo<PackOutcomeCompareRequest>(
    () => ({
      left: subjectOf(record?.before ?? { inputs: {}, caseId: null }, example),
      right: subjectOf(record?.after ?? { inputs: {}, caseId: null }, example),
    }),
    [record, example],
  );
  const compare = usePackOutcomeCompare(
    workspace.id,
    versionRef,
    request,
    active,
  );
  const summary = useMemo(
    () => (compare.data ? summarizeDelta(compare.data) : null),
    [compare.data],
  );
  const changed = useMemo(
    () => (active ? changedElements(compare.data) : NO_CHANGES),
    [active, compare.data],
  );
  const dismiss = useCallback(() => {
    deltaStore.dismiss();
    if (onlyParam) nav.go({ extra: { [DELTA_ONLY_PARAM]: null } });
  }, [nav, onlyParam]);
  const { refetch } = compare;
  return {
    active,
    label: record !== null && active ? record.label : "",
    status: !active
      ? "idle"
      : compare.isError
        ? "error"
        : compare.data
          ? "ready"
          : "loading",
    summary,
    changed,
    highlight: record !== null && active && record.highlight,
    onlyChanged: active && onlyParam,
    retry: () => void refetch(),
    dismiss,
    toggleOnly: () => {
      nav.go({ extra: { [DELTA_ONLY_PARAM]: onlyParam ? null : "1" } });
    },
  };
};
