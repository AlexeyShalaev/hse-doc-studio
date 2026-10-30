import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Archive, FolderOpen, HardDrive, Package } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatFileSize, formatPastTime } from "@shared/lib";
import {
  DataTable,
  EmptyState,
  KpiGrid,
  KpiTile,
  Meter,
  PageHeader,
  PersonCell,
  Section,
  Tooltip,
  type KpiTone,
} from "@shared/ui";
import type { AdminStorage } from "@entities/session";
import { percent } from "../lib/format";
import { personRef, type OpsPerson, type PersonRef } from "../lib/people";
import { isLowSpace } from "../lib/storage";
import type { ViewStatus } from "../lib/viewStatus";
import { Banner, ViewState } from "./parts";

export type StorageViewProps = {
  status: ViewStatus;
  storage: AdminStorage | null;
  /** Почты владельцев по идентификатору. */
  people?: ReadonlyMap<string, OpsPerson>;
  now: number;
  onRetry?: () => void;
};

const NO_PEOPLE: ReadonlyMap<string, OpsPerson> = new Map();

// Доля занятого диска, с которой полоса желтеет; красной её делает isLowSpace.
const WARN_USED = 80;

type OwnerRow = {
  rank: number;
  person: PersonRef;
  projects: number;
  share: number;
};

/** Диск проектов: полоса занятого и свободного места с подписями. */
const DiskUsage = ({
  storage,
  tone,
}: {
  storage: AdminStorage;
  tone: KpiTone;
}) => {
  const { t } = useTranslation("adminOps");
  const total = storage.volume_total_bytes;
  const free = storage.free_bytes;
  if (total === null || free === null || total <= 0) {
    return (
      <EmptyState
        compact
        icon={<HardDrive size={15} />}
        title={t("storage.disk.unknown")}
        description={t("storage.disk.unknownBody")}
      />
    );
  }
  const used = Math.max(0, total - free);
  const usedPct = (used / total) * 100;
  const label = (pct: number): string => `${String(Math.round(pct))}%`;
  return (
    <div className="ops-disk" data-testid="storage-disk">
      <div className="ops-disk-figure">
        <span className="ops-disk-value">{label(usedPct)}</span>
        <span className="ops-disk-of">
          {t("storage.disk.usedOf", {
            used: formatFileSize(used),
            total: formatFileSize(total),
          })}
        </span>
      </div>
      <div
        className="ops-bar"
        role="img"
        aria-label={t("storage.disk.aria", {
          used: formatFileSize(used),
          free: formatFileSize(free),
          total: formatFileSize(total),
        })}
      >
        <Tooltip
          content={t("storage.disk.usedTip", {
            value: formatFileSize(used),
            pct: label(usedPct),
          })}
        >
          <span
            data-part="used"
            data-tone={tone}
            style={{ width: `${String(usedPct)}%` }}
          />
        </Tooltip>
        <Tooltip
          content={t("storage.disk.freeTip", {
            value: formatFileSize(free),
            pct: label(100 - usedPct),
          })}
        >
          <span data-part="free" style={{ flex: 1 }} />
        </Tooltip>
      </div>
      <ul className="ops-legend">
        <li>
          <span
            className="ops-swatch"
            style={{
              background:
                tone === "danger"
                  ? "var(--c-err)"
                  : tone === "warning"
                    ? "var(--c-warn)"
                    : "var(--accent)",
            }}
            aria-hidden="true"
          />
          {t("storage.disk.used")} <strong>{formatFileSize(used)}</strong>
        </li>
        <li>
          <span className="ops-swatch" data-part="free" aria-hidden="true" />
          {t("storage.disk.free")} <strong>{formatFileSize(free)}</strong>
        </li>
      </ul>
    </div>
  );
};

/** Сколько места занято, сколько осталось и у кого больше всего проектов. */
export const StorageView = ({
  status,
  storage,
  people = NO_PEOPLE,
  now,
  onRetry,
}: StorageViewProps) => {
  const { t } = useTranslation("adminOps");

  const low = storage ? isLowSpace(storage) : false;
  const total = storage?.volume_total_bytes ?? null;
  const free = storage?.free_bytes ?? null;
  const usedPct =
    total !== null && free !== null && total > 0
      ? ((total - free) / total) * 100
      : null;
  const diskTone: KpiTone = low
    ? "danger"
    : usedPct !== null && usedPct >= WARN_USED
      ? "warning"
      : "neutral";

  const rows = useMemo<OwnerRow[]>(
    () =>
      (storage?.owners ?? []).map((o, i) => ({
        rank: i + 1,
        person: personRef(o.id, o.name, people),
        projects: o.projects,
        share: percent(o.projects, storage?.projects ?? 0),
      })),
    [storage, people],
  );

  const columns = useMemo<ColumnDef<OwnerRow>[]>(
    () => [
      {
        id: "rank",
        header: () => (
          <span className="sr-only">{t("storage.owners.rank")}</span>
        ),
        enableSorting: false,
        cell: ({ row }) => (
          <span className="ops-rank">{row.original.rank}</span>
        ),
      },
      {
        id: "who",
        header: t("storage.owners.who"),
        enableSorting: false,
        cell: ({ row }) => (
          <span data-testid={`owner-${row.original.person.id}`}>
            <PersonCell
              id={row.original.person.id}
              name={row.original.person.name}
              email={row.original.person.email}
            />
          </span>
        ),
      },
      {
        id: "projects",
        header: () => (
          <span className="ops-num">{t("storage.owners.projectsCol")}</span>
        ),
        enableSorting: false,
        cell: ({ row }) => (
          <span className="ops-num">
            {t("storage.owners.projects", { count: row.original.projects })}
          </span>
        ),
      },
      {
        id: "share",
        header: () => (
          <span className="ops-num">{t("storage.owners.shareCol")}</span>
        ),
        enableSorting: false,
        cell: ({ row }) => (
          <span className="ops-share">
            <Meter
              value={row.original.share}
              label={t("storage.owners.share", {
                name: row.original.person.name ?? "",
              })}
            />
            <span className="ops-share-pct">{row.original.share}%</span>
          </span>
        ),
      },
    ],
    [t],
  );

  return (
    <div className="ops-stack" data-testid="storage-view">
      <PageHeader title={t("storage.title")} description={t("storage.lead")} />
      <ViewState
        status={status}
        errorText={t("storage.loadFailed")}
        onRetry={onRetry}
        testId="storage"
        skeleton={
          <KpiGrid>
            {[0, 1, 2, 3].map((i) => (
              <KpiTile key={i} label="" value="" loading />
            ))}
          </KpiGrid>
        }
      />
      {status === "ready" && storage && (
        <>
          {low && (
            <Banner
              tone="danger"
              testId="storage-low"
              title={t("storage.lowTitle", {
                free: formatFileSize(storage.free_bytes ?? 0),
              })}
            >
              {t("storage.lowBody")}
            </Banner>
          )}
          <KpiGrid>
            <KpiTile
              testId="storage-total"
              icon={<FolderOpen size={14} aria-hidden="true" />}
              label={t("storage.stats.projects")}
              value={storage.projects}
              secondary={
                storage.deleted_projects > 0
                  ? t("storage.stats.projectsHint", {
                      count: storage.deleted_projects,
                    })
                  : t("storage.stats.noDeleted")
              }
            />
            <KpiTile
              testId="storage-objects"
              icon={<Package size={14} aria-hidden="true" />}
              label={t("storage.stats.objects")}
              value={formatFileSize(storage.blob_bytes)}
              secondary={t("storage.stats.objectsHint", {
                count: storage.blob_count,
              })}
            />
            <KpiTile
              testId="storage-free"
              icon={<Archive size={14} aria-hidden="true" />}
              label={t("storage.stats.free")}
              value={
                free === null ? t("storage.unknown") : formatFileSize(free)
              }
              tone={
                low ? "danger" : diskTone === "warning" ? "warning" : "success"
              }
              secondary={
                free === null || total === null
                  ? t("storage.stats.diskUnknown")
                  : t(low ? "storage.stats.freeLow" : "storage.stats.freeOf", {
                      total: formatFileSize(total),
                    })
              }
            />
          </KpiGrid>

          <Section
            title={t("storage.disk.title")}
            description={t("storage.disk.lead")}
            testId="storage-disk-section"
          >
            <DiskUsage storage={storage} tone={diskTone} />
          </Section>

          <Section
            title={t("storage.owners.title")}
            description={t("storage.owners.lead")}
            flush
            testId="storage-owners"
          >
            {rows.length === 0 ? (
              <div style={{ padding: "0 20px 16px" }}>
                <EmptyState
                  compact
                  testId="storage-empty"
                  icon={<FolderOpen size={15} />}
                  title={t("storage.empty.title")}
                  description={t("storage.empty.body")}
                />
              </div>
            ) : (
              <DataTable
                className="ops-table ops-flush-table"
                caption={t("storage.owners.title")}
                columns={columns}
                data={rows}
                getRowId={(r) => r.person.id}
              />
            )}
          </Section>

          <p
            style={{ margin: 0, fontSize: 12, color: "var(--fg-2)" }}
            data-testid="storage-note"
          >
            {storage.computed_at === null
              ? t("storage.noteNever")
              : t("storage.note", {
                  when: formatPastTime(storage.computed_at, now),
                })}
          </p>
        </>
      )}
    </div>
  );
};
