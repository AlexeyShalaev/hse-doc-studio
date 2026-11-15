import { useTranslation } from "react-i18next";
import {
  catalogErrorText,
  shortRevision,
  usePackCatalogHistory,
  type CatalogSource,
} from "@entities/pack-catalog";
import { formatPastTime } from "@shared/lib";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Modal,
  Spinner,
} from "@shared/ui";
import { eventSummary } from "../lib/eventSummary";

const HistoryList = ({ source }: { source: CatalogSource }) => {
  const { t } = useTranslation("adminPackCatalog");
  const history = usePackCatalogHistory(source.id);
  if (history.isPending) return <Spinner />;
  if (history.isError) {
    return (
      <ErrorState
        compact
        description={catalogErrorText(history.error)}
        onRetry={() => void history.refetch()}
      />
    );
  }
  if (history.data.length === 0) {
    return <EmptyState compact title={t("history.empty")} />;
  }
  return (
    <ul
      className="flex flex-col"
      style={{ gap: "0.5rem", margin: 0, padding: 0, listStyle: "none" }}
      data-testid="pc-history"
    >
      {history.data.map((event) => {
        const summary = eventSummary(event);
        return (
          <li
            key={event.id}
            className="card"
            style={{ padding: "0.5rem 0.75rem" }}
            data-testid={`pc-event-${event.id}`}
          >
            <div
              className="flex items-center"
              style={{ gap: "0.5rem", flexWrap: "wrap" }}
            >
              <strong style={{ fontSize: "0.78125rem" }}>
                {t(`history.action.${event.action}`)}
              </strong>
              <Badge variant={event.ok ? "success" : "error"}>
                {event.ok ? t("history.ok") : t("history.failed")}
              </Badge>
              <span
                className="dimmer"
                style={{ fontSize: "0.6875rem" }}
                title={new Date(event.at).toLocaleString()}
              >
                {formatPastTime(event.at)}
              </span>
              {event.revision && (
                <span className="mono dimmer" style={{ fontSize: "0.6875rem" }}>
                  {t("history.revision", {
                    revision: shortRevision(event.revision),
                  })}
                </span>
              )}
            </div>
            {summary.length > 0 && (
              <div
                className="dim"
                style={{
                  fontSize: "0.71875rem",
                  marginTop: "0.25rem",
                  overflowWrap: "anywhere",
                }}
              >
                {summary.join(" · ")}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
};

/** «История» источника: добавление, проверки, применения, включение и выключение. */
export const HistoryDialog = ({
  source,
  onClose,
}: {
  source: CatalogSource | null;
  onClose: () => void;
}) => {
  const { t } = useTranslation("adminPackCatalog");
  return (
    <Modal
      isOpen={source !== null}
      onClose={onClose}
      title={t("history.title", { name: source?.label ?? "" })}
      width={620}
      footer={<Button onClick={onClose}>{t("common.close")}</Button>}
    >
      {source && <HistoryList source={source} />}
    </Modal>
  );
};
