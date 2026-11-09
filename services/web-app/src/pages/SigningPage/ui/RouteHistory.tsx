import { useTranslation } from "react-i18next";
import type { RouteEvent } from "@entities/signing-route";
import { formatMoment } from "../lib/format";

/** События маршрута, новые сверху: кто, что и когда; у возврата комментарий. */
export const RouteHistory = ({ events }: { events: RouteEvent[] }) => {
  const { t } = useTranslation("signing");
  if (events.length === 0) return null;
  return (
    <details className="sgn-card sgn-history" data-testid="signing-history">
      <summary>
        {t("history.title")} ({events.length})
      </summary>
      <ol>
        {[...events].reverse().map((event) => (
          <li key={event.id} data-kind={event.kind}>
            <time dateTime={event.at}>{formatMoment(event.at)}</time>
            {event.who ?? t("history.server")}:{" "}
            {t(`history.kind.${event.kind}`)}
            {event.reason && event.kind !== "returned"
              ? ` (${t(`history.reason.${event.reason}`)})`
              : ""}
            {event.comment && <q>{event.comment}</q>}
          </li>
        ))}
      </ol>
    </details>
  );
};
