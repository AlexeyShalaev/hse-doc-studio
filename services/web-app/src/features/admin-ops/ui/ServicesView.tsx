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
import { formatDuration } from "../lib/format";
import { secondsSince } from "../lib/runnerStatus";
import { useDurationUnits } from "../lib/useDurationUnits";
import { CARD } from "../lib/styles";
import { LoadFailed, LoadingRow, Meter, PageHeader } from "./parts";

export type ServicesViewProps = {
  status: "loading" | "error" | "ready";
  services: readonly AdminService[];
  now: number;
  /** Сервис, который проверяется прямо сейчас. */
  checkingId?: string | null;
  onRetry?: () => void;
  onCheck: (service: AdminService) => void;
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
  now,
  checkingId = null,
  onRetry,
  onCheck,
}: ServicesViewProps) => {
  const { t } = useTranslation("adminOps");
  const units = useDurationUnits();

  const down = services.filter((s) => s.status === "down").length;
  const degraded = services.filter((s) => s.status === "degraded").length;

  return (
    <div
      className="flex flex-col"
      style={{ gap: 16 }}
      data-testid="services-view"
    >
      <PageHeader title={t("services.title")} lead={t("services.lead")} />
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
            const age = secondsSince(service.checked_at, now);
            const checking = checkingId === service.id;
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
                    : service.latency_ms !== null
                      ? t("services.latency", { ms: service.latency_ms })
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
                {service.replicas.length > 0 && (
                  <ul
                    style={{
                      listStyle: "none",
                      margin: 0,
                      padding: 0,
                      display: "flex",
                      flexDirection: "column",
                      gap: 6,
                    }}
                  >
                    {service.replicas.map((r) => (
                      <li
                        key={r.name}
                        className="flex items-center"
                        style={{ gap: 8, fontSize: 12 }}
                        data-testid={`replica-${r.name}`}
                        data-status={r.status}
                      >
                        <StatusDot
                          status={DOT[r.status]}
                          hideLabel
                          label={t(`services.status.${r.status}`)}
                        />
                        <span className="mono" style={{ width: 54 }}>
                          {r.name}
                        </span>
                        {r.slots_total !== null && r.slots_used !== null ? (
                          <>
                            <span style={{ flex: 1 }}>
                              <Meter
                                value={Math.round(
                                  (r.slots_used / Math.max(1, r.slots_total)) *
                                    100,
                                )}
                                label={t("services.slots", {
                                  used: r.slots_used,
                                  total: r.slots_total,
                                })}
                                tone={
                                  r.slots_used >= r.slots_total
                                    ? "warn"
                                    : "accent"
                                }
                              />
                            </span>
                            <span
                              style={{
                                color: "var(--fg-2)",
                                fontVariantNumeric: "tabular-nums",
                              }}
                            >
                              {r.slots_used}/{r.slots_total}
                            </span>
                          </>
                        ) : (
                          <span style={{ flex: 1, color: "var(--fg-3)" }}>
                            {t(`services.status.${r.status}`)}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
                <div
                  className="flex items-center"
                  style={{ gap: 8, marginTop: "auto" }}
                >
                  <span style={{ flex: 1, fontSize: 11, color: "var(--fg-3)" }}>
                    {age === null
                      ? ""
                      : t("services.checkedAgo", {
                          ago: formatDuration(age, units),
                        })}
                  </span>
                  <Button
                    size="sm"
                    variant="ghost"
                    type="button"
                    disabled={checking}
                    style={{ gap: 5 }}
                    data-testid={`service-check-${service.id}`}
                    onClick={() => {
                      onCheck(service);
                    }}
                  >
                    {checking ? (
                      <Spinner size="sm" />
                    ) : (
                      <RefreshCw size={13} aria-hidden="true" />
                    )}
                    {t("services.check")}
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};
