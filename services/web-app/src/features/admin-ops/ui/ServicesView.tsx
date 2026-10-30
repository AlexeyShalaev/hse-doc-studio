import type { ReactNode } from "react";
import {
  Cpu,
  Database,
  FileText,
  HardDrive,
  Mail,
  RefreshCw,
  SpellCheck,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatPastTime } from "@shared/lib";
import {
  Button,
  Meter,
  PageHeader,
  Section,
  Spinner,
  StatusDot,
  type StatusDotStatus,
} from "@shared/ui";
import type { AdminService, ServiceStatus } from "@entities/session";
import type { ViewStatus } from "../lib/viewStatus";
import { Banner, ViewState } from "./parts";

export type ServicesViewProps = {
  status: ViewStatus;
  services: readonly AdminService[];
  /** Идёт повторная проверка всех сервисов. */
  refreshing?: boolean;
  /** Когда пришёл последний ответ, мс. */
  checkedAt?: number | null;
  now?: number;
  onRetry?: () => void;
  onRefresh: () => void;
};

const ICON: Record<AdminService["kind"], LucideIcon> = {
  database: Database,
  storage: HardDrive,
  languagetool: SpellCheck,
  onlyoffice: FileText,
  runners: Cpu,
  smtp: Mail,
};

const DOT: Record<ServiceStatus, StatusDotStatus> = {
  ok: "success",
  degraded: "warning",
  down: "danger",
  unconfigured: "neutral",
};

const KNOWN_REASONS = [
  "timeout",
  "no_healthy_replica",
  "no_online_runner",
  "no_runners",
];

const isBad = (s: AdminService): boolean =>
  s.status === "down" || s.status === "degraded";

const ServiceCard = ({ service }: { service: AdminService }) => {
  const { t } = useTranslation("adminOps");
  const Icon = ICON[service.kind];
  const counted = service.total !== null && service.online !== null;
  let foot: ReactNode = null;
  if (service.status === "unconfigured") {
    foot = (
      <p className="ops-service-impact">{t(`services.off.${service.kind}`)}</p>
    );
  } else if (isBad(service)) {
    foot = (
      <>
        <span
          className="ops-service-line"
          data-testid={`service-detail-${service.id}`}
        >
          <span
            style={{
              color:
                service.status === "down" ? "var(--c-err)" : "var(--c-warn)",
              fontWeight: 500,
            }}
          >
            {service.detail && KNOWN_REASONS.includes(service.detail)
              ? t(`services.reason.${service.detail}`)
              : t("services.reason.unknown")}
          </span>
          {service.detail && (
            <span className="ops-code" title={t("services.reasonCode")}>
              {service.detail}
            </span>
          )}
        </span>
        <p className="ops-service-impact">
          {t(`services.impact.${service.kind}`)}
        </p>
      </>
    );
  }
  return (
    <li
      className="ops-service"
      data-testid={`service-${service.id}`}
      data-status={service.status}
    >
      <div className="ops-service-head">
        <span className="ops-service-icon" aria-hidden="true">
          <Icon size={16} />
        </span>
        <div className="ops-service-title">
          <h3 className="ops-service-name">
            {t(`services.kind.${service.kind}`)}
          </h3>
          <StatusDot
            status={DOT[service.status]}
            label={t(`services.status.${service.status}`)}
          />
        </div>
      </div>
      <p className="ops-service-role">{t(`services.role.${service.kind}`)}</p>
      {(foot !== null || (counted && service.status !== "unconfigured")) && (
        <div className="ops-service-foot">
          {counted && service.status !== "unconfigured" && (
            <span className="flex flex-col" style={{ gap: 6 }}>
              <span className="ops-service-line">
                <span>
                  {t("services.online", {
                    online: service.online,
                    total: service.total,
                  })}
                </span>
              </span>
              <Meter
                value={
                  service.total
                    ? ((service.online ?? 0) / service.total) * 100
                    : 0
                }
                tone={
                  service.online === 0
                    ? "danger"
                    : (service.online ?? 0) < (service.total ?? 0)
                      ? "warning"
                      : "success"
                }
                label={t("services.onlineLabel")}
              />
            </span>
          )}
          {foot}
        </div>
      )}
    </li>
  );
};

/** Здоровье сервисов установки: карточки по подключённым и неподключённым. */
export const ServicesView = ({
  status,
  services,
  refreshing = false,
  checkedAt = null,
  now,
  onRetry,
  onRefresh,
}: ServicesViewProps) => {
  const { t } = useTranslation("adminOps");

  const connected = services.filter((s) => s.status !== "unconfigured");
  const off = services.filter((s) => s.status === "unconfigured");
  const down = services.filter((s) => s.status === "down");
  const degraded = services.filter((s) => s.status === "degraded");
  const names = (list: readonly AdminService[]): string =>
    list.map((s) => t(`services.kind.${s.kind}`)).join(", ");

  return (
    <div className="ops-stack" data-testid="services-view">
      <PageHeader
        title={t("services.title")}
        description={t("services.lead")}
        meta={
          status === "ready" && down.length === 0 && degraded.length === 0 ? (
            <span data-testid="services-summary">
              <StatusDot
                status={connected.length > 0 ? "success" : "neutral"}
                label={
                  connected.length > 0
                    ? t("services.summary.ok")
                    : t("services.summary.none")
                }
              />
            </span>
          ) : undefined
        }
        actions={
          <span className="flex items-center" style={{ gap: 12 }}>
            {checkedAt !== null && status === "ready" && (
              <span style={{ fontSize: 12, color: "var(--fg-2)" }}>
                {t("services.checked", {
                  when: formatPastTime(checkedAt, now ?? checkedAt),
                })}
              </span>
            )}
            <Button
              size="sm"
              variant="secondary"
              type="button"
              disabled={refreshing}
              style={{ gap: 6 }}
              data-testid="services-refresh"
              onClick={onRefresh}
            >
              {refreshing ? (
                <Spinner size="sm" />
              ) : (
                <RefreshCw size={13} aria-hidden="true" />
              )}
              {t("services.check")}
            </Button>
          </span>
        }
      />
      <ViewState
        status={status}
        errorText={t("services.loadFailed")}
        onRetry={onRetry}
        testId="services"
        skeleton={<ServicesSkeleton />}
      />
      {status === "ready" && down.length > 0 && (
        <Banner
          tone="danger"
          testId="services-summary"
          title={t("services.summary.down", { count: down.length })}
        >
          {t("services.summary.downBody", { names: names(down) })}
        </Banner>
      )}
      {status === "ready" && down.length === 0 && degraded.length > 0 && (
        <Banner
          tone="warning"
          testId="services-summary"
          title={t("services.summary.degraded", { count: degraded.length })}
        >
          {t("services.summary.degradedBody", { names: names(degraded) })}
        </Banner>
      )}
      {status === "ready" && connected.length > 0 && (
        <ul className="ops-services" aria-label={t("services.connected")}>
          {connected.map((service) => (
            <ServiceCard key={service.id} service={service} />
          ))}
        </ul>
      )}
      {status === "ready" && off.length > 0 && (
        <Section
          variant="plain"
          title={t("services.offTitle")}
          description={t("services.offLead")}
          testId="services-off"
        >
          <ul className="ops-services" aria-label={t("services.offTitle")}>
            {off.map((service) => (
              <ServiceCard key={service.id} service={service} />
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
};

const ServicesSkeleton = () => (
  <ul className="ops-services" aria-hidden="true">
    {[0, 1, 2, 3, 4, 5].map((i) => (
      <li key={i} className="ops-service" style={{ height: 132 }}>
        <span className="adm-skel" style={{ width: "50%" }} />
        <span className="adm-skel" style={{ width: "80%" }} />
      </li>
    ))}
  </ul>
);
