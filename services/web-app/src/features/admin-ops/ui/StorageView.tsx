import { Building2, User } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Notice } from "@shared/ui/ConflictKit";
import type { AdminStorage } from "@entities/session";
import { formatBytes, formatDuration, percent } from "../lib/format";
import { secondsSince } from "../lib/runnerStatus";
import { isLowSpace } from "../lib/storage";
import { useDurationUnits } from "../lib/useDurationUnits";
import { CARD } from "../lib/styles";
import {
  Card,
  EmptyBlock,
  LoadFailed,
  LoadingRow,
  Meter,
  PageHeader,
  Stat,
  StatRow,
} from "./parts";

export type StorageViewProps = {
  status: "loading" | "error" | "ready";
  storage: AdminStorage | null;
  now: number;
  onRetry?: () => void;
};

/** Занятое место по людям и организациям. */
export const StorageView = ({
  status,
  storage,
  now,
  onRetry,
}: StorageViewProps) => {
  const { t, i18n } = useTranslation("adminOps");
  const units = useDurationUnits();
  const locale = i18n.language;
  const bytes = (v: number) => formatBytes(v, locale);

  const age = storage ? secondsSince(storage.computed_at, now) : null;
  const biggest = storage
    ? Math.max(1, ...storage.owners.map((o) => o.bytes))
    : 1;

  return (
    <div
      className="flex flex-col"
      style={{ gap: 16 }}
      data-testid="storage-view"
    >
      <PageHeader title={t("storage.title")} lead={t("storage.lead")} />
      {status === "loading" && <LoadingRow testId="storage-loading" />}
      {status === "error" && (
        <LoadFailed text={t("storage.loadFailed")} onRetry={onRetry} />
      )}
      {status === "ready" && storage && (
        <>
          {isLowSpace(storage) && (
            <div data-testid="storage-low">
              <Notice
                tone="err"
                role="alert"
                text={t("storage.low", {
                  free: bytes(storage.free_bytes ?? 0),
                })}
              />
            </div>
          )}
          <StatRow>
            <Stat
              label={t("storage.stats.total")}
              value={bytes(storage.total_bytes)}
              testId="storage-total"
            />
            <Stat
              label={t("storage.stats.volume")}
              value={bytes(storage.volume_bytes)}
              hint={t("storage.stats.volumeHint")}
            />
            <Stat
              label={t("storage.stats.objects")}
              value={bytes(storage.object_bytes)}
              hint={t("storage.stats.objectsHint")}
            />
            <Stat
              label={t("storage.stats.free")}
              value={
                storage.free_bytes === null
                  ? t("storage.unknown")
                  : bytes(storage.free_bytes)
              }
              hint={t("storage.stats.freeHint")}
              {...(isLowSpace(storage) ? { tone: "err" as const } : {})}
              testId="storage-free"
            />
          </StatRow>
          <Card
            title={t("storage.owners.title")}
            lead={t("storage.owners.lead")}
            testId="storage-owners"
          >
            {storage.owners.length === 0 ? (
              <EmptyBlock
                testId="storage-empty"
                title={t("storage.empty.title")}
                body={t("storage.empty.body")}
              />
            ) : (
              <ul
                style={{
                  listStyle: "none",
                  margin: 0,
                  padding: 0,
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                }}
              >
                {storage.owners.map((o) => {
                  const Icon = o.kind === "org" ? Building2 : User;
                  return (
                    <li
                      key={`${o.kind}:${o.id}`}
                      className="flex items-center"
                      style={{
                        ...CARD,
                        gap: 12,
                        padding: "8px 12px",
                        boxShadow: "none",
                      }}
                      data-testid={`owner-${o.id}`}
                    >
                      <Icon
                        size={15}
                        aria-hidden="true"
                        style={{ color: "var(--fg-2)" }}
                      />
                      <span
                        className="flex flex-col"
                        style={{ flex: 1, minWidth: 0 }}
                      >
                        <span style={{ fontWeight: 600, fontSize: 13 }}>
                          {o.name}
                        </span>
                        <span style={{ fontSize: 11.5, color: "var(--fg-2)" }}>
                          {t(`storage.owners.kind.${o.kind}`)} ·{" "}
                          {t("storage.owners.projects", { count: o.projects })}
                        </span>
                      </span>
                      <span style={{ width: "28%", minWidth: 70 }}>
                        <Meter
                          value={percent(o.bytes, biggest)}
                          label={t("storage.owners.share", { name: o.name })}
                        />
                      </span>
                      <span
                        style={{
                          width: 80,
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                          fontSize: 13,
                        }}
                      >
                        {bytes(o.bytes)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
          <p
            style={{
              margin: 0,
              fontSize: 11.5,
              color: "var(--fg-2)",
              maxWidth: 640,
            }}
            data-testid="storage-note"
          >
            {t("storage.note", {
              ago: age === null ? "-" : formatDuration(age, units),
            })}
          </p>
        </>
      )}
    </div>
  );
};
