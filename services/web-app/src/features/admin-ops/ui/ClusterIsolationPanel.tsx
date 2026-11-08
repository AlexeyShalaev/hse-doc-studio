import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Section, TableSkeleton } from "@shared/ui";
import type { AdminRunnerIsolation } from "@entities/session";
import { useRunnerIsolation } from "../api/opsQueries";
import { useNow } from "../lib/useNow";
import { statusOf, type ViewStatus } from "../lib/viewStatus";
import { ClusterIsolationView, IsolationSummary } from "./ClusterIsolationView";
import { ViewState } from "./parts";

/** Раздел «Изоляция раннеров в кластере» на вкладке раннеров. */
export const ClusterIsolationPanel = () => {
  const query = useRunnerIsolation();
  return (
    <ClusterIsolationSection
      info={query.data ?? null}
      status={statusOf(query)}
      onRetry={() => void query.refetch()}
    />
  );
};

/** Вид раздела без запроса: его рендерят тесты и галерея. */
export const ClusterIsolationSection = ({
  info,
  status,
  onRetry,
  initiallyOpen = false,
}: {
  info: AdminRunnerIsolation | null;
  status: ViewStatus;
  onRetry?: () => void;
  initiallyOpen?: boolean;
}) => {
  const { t } = useTranslation("adminRunnerIsolation");
  const [open, setOpen] = useState(initiallyOpen);
  const now = useNow();
  return (
    <Section
      title={t("panel.title")}
      description={t("panel.lead")}
      testId="runner-isolation"
    >
      {info === null ? (
        <ViewState
          status={status}
          errorText={t("panel.loadFailed")}
          onRetry={onRetry}
          compact
          skeleton={<TableSkeleton rows={3} columns={2} />}
          testId="runner-isolation"
        />
      ) : (
        <div className="iso-stack">
          <IsolationSummary info={info} now={now} />
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="iso-toggle"
            aria-expanded={open}
            onClick={() => {
              setOpen((value) => !value);
            }}
            style={{ gap: "0.375rem" }}
            data-testid="runner-isolation-toggle"
          >
            {open ? (
              <ChevronUp size="0.875rem" aria-hidden="true" />
            ) : (
              <ChevronDown size="0.875rem" aria-hidden="true" />
            )}
            {open ? t("panel.hide") : t("panel.show")}
          </Button>
          {open && <ClusterIsolationView info={info} />}
        </div>
      )}
    </Section>
  );
};
