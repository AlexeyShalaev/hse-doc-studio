import { useTranslation } from "react-i18next";
import { Button, Spinner } from "@shared/ui";
import { UsageList, type MyUsage } from "@entities/quota";

export type UsageViewProps = {
  status: "loading" | "error" | "ready";
  usage?: MyUsage;
  onRetry?: () => void;
};

/** Раздел настроек «Использование»: квоты человека и его организаций с полосами и датами сброса. */
export const UsageView = ({ status, usage, onRetry }: UsageViewProps) => {
  const { t } = useTranslation("quota");
  return (
    <div
      data-testid="usage-section"
      className="flex flex-col"
      style={{ gap: "0.75rem" }}
    >
      <div
        id="usage"
        className="flex flex-col settings-anchor"
        style={{ gap: "0.25rem" }}
      >
        <h4 style={{ margin: 0, fontSize: "0.875rem", fontWeight: 600 }}>
          {t("section.title")}
        </h4>
        <p style={{ margin: 0, color: "var(--fg-2)", fontSize: "0.75rem" }}>
          {t("section.lead")}
        </p>
      </div>
      {status === "loading" && (
        <div
          className="flex items-center"
          style={{ gap: "0.5rem" }}
          role="status"
        >
          <Spinner />
          {t("section.loading")}
        </div>
      )}
      {status === "error" && (
        <div
          role="alert"
          className="flex items-center"
          style={{ gap: "0.75rem" }}
        >
          <span style={{ color: "var(--c-err)" }}>
            {t("section.loadFailed")}
          </span>
          {onRetry && (
            <Button size="sm" variant="ghost" onClick={onRetry}>
              {t("section.retry")}
            </Button>
          )}
        </div>
      )}
      {status === "ready" && usage && (
        <>
          <section
            className="adm-section"
            data-variant="card"
            style={{ padding: "0.5rem 1rem" }}
            aria-label={t("section.mine")}
          >
            <h5 style={{ margin: "0.5rem 0 0", fontSize: "0.8125rem" }}>
              {t("section.mine")}
            </h5>
            <UsageList lines={usage.user.lines} />
          </section>
          {usage.orgs.map((org) => (
            <section
              key={org.owner_id}
              className="adm-section"
              data-variant="card"
              style={{ padding: "0.5rem 1rem" }}
              data-testid={`usage-org-${org.owner_id}`}
              aria-label={t("section.org", { name: org.owner_name })}
            >
              <h5 style={{ margin: "0.5rem 0 0", fontSize: "0.8125rem" }}>
                {t("section.org", { name: org.owner_name })}
              </h5>
              <UsageList lines={org.lines} />
            </section>
          ))}
          <p style={{ margin: 0, color: "var(--fg-3)", fontSize: "0.75rem" }}>
            {t("section.membersHint")} {t("section.aiHint")}
          </p>
        </>
      )}
    </div>
  );
};
