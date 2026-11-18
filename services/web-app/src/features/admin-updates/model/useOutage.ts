import { useState } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { ApiError } from "@shared/api";

/** Сервер не отвечает (обрыв сети) или прокси отвечает вместо него: так выглядит перезапуск api. */
export const isUnreachable = (error: unknown): boolean =>
  error instanceof ApiError &&
  (error.status === 0 ||
    error.status === 502 ||
    error.status === 503 ||
    error.status === 504);

export type Outage = {
  /** Последний опрос не прошёл, а прежние данные ещё есть. */
  down: boolean;
  /** Когда простой замечен (мс), пока он идёт. */
  since: number | null;
  /** Сколько неудачных опросов подряд за этот простой. */
  attempts: number;
  /** Простой кончился: сколько секунд длился. Сбрасывается, когда его закрыли. */
  recoveredAfterS: number | null;
};

type Mark = { since: number | null; base: number; recovered: number | null };

/**
 * Простой api во время обновления. Данные прошлого опроса остаются на экране, поверх них показывается
 * «приложение перезапускается»; когда ответ вернулся, простой переходит в `recoveredAfterS`.
 * Время берётся из отметок самого запроса (`errorUpdatedAt`, `dataUpdatedAt`), а не из часов в рендере.
 */
export const useOutage = (
  query: Pick<
    UseQueryResult,
    | "isError"
    | "error"
    | "data"
    | "errorUpdateCount"
    | "errorUpdatedAt"
    | "dataUpdatedAt"
  >,
): Outage & { dismissRecovered: () => void } => {
  const down =
    query.isError && query.data !== undefined && isUnreachable(query.error);
  const [mark, setMark] = useState<Mark>({
    since: null,
    base: 0,
    recovered: null,
  });
  // Переход состояния решается прямо в рендере (допустимый приём React): без лишнего прохода эффекта.
  if (down && mark.since === null) {
    setMark({
      since: query.errorUpdatedAt,
      base: Math.max(0, query.errorUpdateCount - 1),
      recovered: null,
    });
  } else if (!down && mark.since !== null) {
    setMark({
      since: null,
      base: 0,
      recovered: Math.max(
        0,
        Math.round((query.dataUpdatedAt - mark.since) / 1000),
      ),
    });
  }
  return {
    down,
    since: mark.since,
    attempts: down ? Math.max(1, query.errorUpdateCount - mark.base) : 0,
    recoveredAfterS: mark.recovered,
    dismissRecovered: () => {
      setMark((m) => ({ ...m, recovered: null }));
    },
  };
};
