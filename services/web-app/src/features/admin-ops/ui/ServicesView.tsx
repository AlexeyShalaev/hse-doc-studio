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
import { Button, Spinner, StatusDot } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { AdminService, ServiceStatus } from "@entities/session";
import { CARD } from "../lib/styles";
import { LoadFailed, LoadingRow, PageHeader } from "./parts";

export type ServicesViewProps = {
  status: "loading" | "error" | "ready";
  services: readonly AdminService[];
  /** Идёт повторная проверка всех сервисов. */
  refreshing?: boolean;
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

const DOT: Record<ServiceStatus, "online" | "stale" | "degraded" | "offline"> =
  {
    ok: "online",
    degraded: "stale",
    down: "degraded",
    unconfigured: "offline",
  };

/** Здоровье сервисов установки: карточки, реплики, проверка по кнопке. */
export const ServicesView = ({
  status,
  services,
  refreshing = false,
  onRetry,
  onRefresh,
}: ServicesViewProps) => {
  const { t } = useTranslation("adminOps");

  const down = services.filter((s) => s.status === "down").length;
  const degraded = services.filter((s) => s.status === "degraded").length;

  return (
    <div
      className="flex flex-col"
      style={{ gap: 16 }}
      data-testid="services-view"
    >
      <PageHeader
        title={t("services.title")}
        lead={t("services.lead")}
        action={
          <Button
            size="sm"
            variant="ghost"
            type="button"
            disabled={refreshing}
            style={{ gap: 5 }}
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
        }
      />
      {status === "loading" && <LoadingRow testId="services-loading" />}
      {status === "error" && (
        <LoadFailed text={t("services.loadFailed")} onRetry={onRetry} />
      )}
      {status === "ready" && services.length > 0 && (
        <div data-testid="services-summary">
          {down > 0 ? (
            <Notice
              tone="err"
              role="alert"
              text={t("services.summary.down", { count: down })}
            />
          ) : degraded > 0 ? (
            <Notice
              tone="warn"
              role="status"
              text={t("services.summary.degraded", { count: degraded })}
            />
          ) : (
            <Notice tone="info" role="status" text={t("services.summary.ok")} />
          )}
        </div>
      )}
      {status === "ready" && (
        <ul
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            display: "grid",
            gap: 12,
            gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
          }}
        >
          {services.map((service) => {
            const Icon = ICON[service.kind];
            return (
              <li
                key={service.id}
                className="flex flex-col"
                style={{ ...CARD, gap: 10, padding: 14 }}
                data-testid={`service-${service.id}`}
                data-status={service.status}
              >
                <div className="flex items-center" style={{ gap: 8 }}>
                  <Icon
                    size={16}
                    aria-hidden="true"
                    style={{ color: "var(--fg-2)" }}
                  />
                  <strong style={{ fontSize: 13.5, flex: 1 }}>
                    {t(`services.kind.${service.kind}`)}
                  </strong>
                  <StatusDot
                    status={DOT[service.status]}
                    label={t(`services.status.${service.status}`)}
                  />
                </div>
                <div style={{ fontSize: 12, color: "var(--fg-2)" }}>
                  {service.status === "unconfigured"
                    ? t("services.unconfigured")
                    : service.total !== null && service.online !== null
                      ? t("services.online", {
                          online: service.online,
                          total: service.total,
                        })
                      : "-"}
                </div>
                {service.detail && (
                  <div
                    style={{
                      fontSize: 12.5,
                      color:
                        service.status === "down"
                          ? "var(--c-err)"
                          : "var(--c-warn)",
                    }}
                    data-testid={`service-detail-${service.id}`}
                  >
                    {service.detail}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};
