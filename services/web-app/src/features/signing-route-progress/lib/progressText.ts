import type { TFunction } from "i18next";
import type { RouteTally } from "./routeView";

/**
 * Ход маршрута одной строкой: «Согласовано 1 из 3 · подписано 0 из 3», необязательные слоты
 * коротким хвостом. Согласие видно отдельно от подписи: ЭП ставят только после фиксации PDF, и
 * без этого согласовавший видел бы «подписано 0» без объяснения.
 */
export const progressText = (
  t: TFunction<"signingProgress">,
  tally: RouteTally,
): string => {
  if (tally.total === 0)
    return t("progressOnlyOptional", {
      approved: tally.optionalApproved,
      done: tally.optionalDone,
      total: tally.optionalTotal,
    });
  const main = t("progress", {
    approved: tally.approved,
    done: tally.done,
    total: tally.total,
  });
  if (tally.optionalTotal === 0) return main;
  return `${main} ${t("progressOptional", {
    count: tally.optionalTotal,
    done: tally.optionalDone,
  })}`;
};
