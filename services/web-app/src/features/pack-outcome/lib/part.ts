import {
  usePackOutcome,
  type OutcomeBranch,
  type OutcomeCheckRule,
  type PackOutcome,
} from "@entities/pack-studio";
import { useOutcomeModel } from "../model";
import { useLastDefined } from "./lastDefined";

/** Дорогие части ответа, которые сервер считает по `include`. */
export type OutcomePart = "checks" | "branches";

type PartItems = {
  checks: OutcomeCheckRule[];
  branches: OutcomeBranch[];
};

export type PartState<K extends OutcomePart> = {
  /** `undefined`: данных ещё не было; `null`: сервер часть не вернул. */
  items: PartItems[K] | null | undefined;
  /** Данные ещё не приходили, запрос идёт. */
  pending: boolean;
  /** Показаны прежние данные: пересчёт идёт или не удался. */
  stale: boolean;
  /** Данные есть, новый запрос идёт: экран пишет «Пересчитываю». */
  refreshing: boolean;
  failed: boolean;
  error: unknown;
  retry: () => void;
};

const pick = <K extends OutcomePart>(
  outcome: PackOutcome | undefined,
  part: K,
): PartItems[K] | null | undefined =>
  outcome === undefined
    ? undefined
    : (outcome[part] as PartItems[K] | null | undefined);

/**
 * Дорогая часть результата (`checks`, `branches`) запрашивается отдельно от основного расчёта и
 * только когда раздел раскрыт (`wanted`): свёрнутый раздел сервер не нагружает. Запрос тот же
 * `outcome` с `include`, вводные и состояние берутся из основного запроса экрана, прежний ответ
 * остаётся на экране, пока идёт пересчёт. До первого основного ответа запроса нет.
 */
export const useOutcomePart = <K extends OutcomePart>(
  part: K,
  wanted: boolean,
): PartState<K> => {
  const { workspaceId, ref, request, shown } = useOutcomeModel();
  const query = usePackOutcome(
    workspaceId,
    ref,
    { ...request, include: [part] },
    wanted && shown !== undefined,
  );
  const items = useLastDefined(pick(query.data, part));
  return {
    items,
    pending: items === undefined && wanted && !query.isError,
    stale: items !== undefined && (query.isPlaceholderData || query.isError),
    refreshing: items !== undefined && query.isFetching,
    failed: query.isError,
    error: query.isError ? query.error : null,
    retry: () => void query.refetch(),
  };
};
