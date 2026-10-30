import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import {
  Archive,
  Building2,
  FolderOpen,
  HardDrive,
  Package,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatFileSize, formatPastTime, localeTag } from "@shared/lib";
import {
  DataTable,
  EmptyState,
  FilterBar,
  KpiGrid,
  KpiTile,
  Meter,
  PageHeader,
  PersonCell,
  Section,
  Tooltip,
  type KpiTone,
} from "@shared/ui";
import type { AdminStorage, AdminStorageOwnerRow } from "@entities/session";
import { percent } from "../lib/format";
import {
  OWNER_KINDS,
  OWNER_SORT,
  type ListView,
  type OwnerFilter,
  type OwnerSort,
} from "../lib/lists";
import { diskTone as toneOf, isLowSpace } from "../lib/storage";
import type { ViewStatus } from "../lib/viewStatus";
import { Banner, ViewState } from "./parts";

export type StorageViewProps = {
  status: ViewStatus;
  storage: AdminStorage | null;
  /** Владельцы места страницей с сервера: люди и организации. */
  owners: ListView<AdminStorageOwnerRow, OwnerFilter, OwnerSort>;
  now: number;
  onRetry?: () => void;
};

type OwnerRow = {
  /** Место в текущем порядке с учётом страницы. */
  rank: number;
  owner: AdminStorageOwnerRow;
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
    </div>
  );
};

/** Сколько места занято, сколько осталось и у кого больше всего проектов. */
export const StorageView = ({
  status,
  storage,
  owners,
  now,
  onRetry,
}: StorageViewProps) => {
  const { t } = useTranslation("adminOps");
  const { state } = owners;

  const low = storage ? isLowSpace(storage) : false;
  const total = storage?.volume_total_bytes ?? null;
  const free = storage?.free_bytes ?? null;
  const diskTone: KpiTone = storage ? toneOf(storage) : "neutral";

  const allProjects = storage?.projects ?? 0;
  const rows = useMemo<OwnerRow[]>(
    () =>
      owners.items.map((owner, i) => ({
        rank: state.offset + i + 1,
        owner,
        share: percent(owner.projects, allProjects),
      })),
    [owners.items, state.offset, allProjects],
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
          <span className="ops-rank">
            {row.original.rank.toLocaleString(localeTag())}
          </span>
        ),
      },
      {
        id: "name",
        header: t("storage.owners.who"),
        cell: ({ row }) => {
          const { owner } = row.original;
          return (
            <span data-testid={`owner-${owner.id}`}>
              <PersonCell
                id={owner.id}
                name={owner.name}
                email={owner.email}
                {...(owner.kind === "org"
                  ? {
                      subtitle: (
                        <span className="ops-owner-org">
                          <Building2 size={11} aria-hidden="true" />
                          {t("storage.owners.org")}
                        </span>
                      ),
                    }
                  : {})}
              />
            </span>
          );
        },
      },
      {
        id: "projects",
        header: () => (
          <span className="ops-num">{t("storage.owners.projectsCol")}</span>
        ),
        sortDescFirst: true,
        cell: ({ row }) => (
          <span className="ops-num">
            {row.original.owner.projects.toLocaleString(localeTag())}
          </span>
        ),
      },
      {
        id: "share",
        header: () => (
          <span className="ops-num">{t("storage.owners.shareCol")}</span>
        ),
        // Доля считается от числа проектов, а не от места: поэтому столбец
        // стоит рядом с проектами, а не рядом с размером.
        enableSorting: false,
        cell: ({ row }) => (
          <span className="ops-share">
            <Meter
              value={row.original.share}
              label={t("storage.owners.share", {
                name: row.original.owner.name,
              })}
            />
            <span className="ops-share-pct">{row.original.share}%</span>
          </span>
        ),
      },
      {
        id: "bytes",
        header: () => (
          <span className="ops-num">{t("storage.owners.bytesCol")}</span>
        ),
        sortDescFirst: true,
        cell: ({ row }) => (
          <span className="ops-num">
            {formatFileSize(row.original.owner.bytes)}
          </span>
        ),
      },
    ],
    [t],
  );

  // Пусто без условий: проектов ещё нет ни у кого.
  const noOwners =
    owners.status === "ready" &&
    !owners.failed &&
    !state.isFiltered &&
    owners.total === 0;

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
              value={storage.projects.toLocaleString(localeTag())}
              secondary={
                storage.deleted_projects > 0
                  ? t("storage.stats.projectsHint", {
                      count: storage.deleted_projects,
                      n: storage.deleted_projects.toLocaleString(localeTag()),
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
                n: storage.blob_count.toLocaleString(localeTag()),
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

          {/* Таблицы админки одного вида: заголовок над ней, таблица в своей рамке. */}
          <Section
            variant="plain"
            title={t("storage.owners.title")}
            description={t("storage.owners.lead")}
            testId="storage-owners"
          >
            {noOwners ? (
              <EmptyState
                framed
                testId="storage-empty"
                icon={<FolderOpen size={18} />}
                title={t("storage.empty.title")}
                description={t("storage.empty.body")}
              />
            ) : (
              <div className="ops-stack" style={{ gap: 12 }}>
                <FilterBar
                  search={state.q}
                  onSearchChange={state.setQ}
                  searchLabel={t("storage.owners.search")}
                  searchPlaceholder={t("storage.owners.searchPlaceholder")}
                  busy={owners.fetching}
                  onReset={state.reset}
                  filters={[
                    {
                      id: "kind",
                      label: t("storage.owners.kind"),
                      value: state.filter("kind"),
                      onChange: (value) => {
                        state.setFilter("kind", value === "" ? null : value);
                      },
                      options: OWNER_KINDS.map((kind) => ({
                        value: kind,
                        label: t(`storage.owners.kinds.${kind}`),
                      })),
                    },
                  ]}
                />
                <DataTable
                  className="ops-table ops-static"
                  caption={t("storage.owners.title")}
                  columns={columns}
                  data={rows}
                  getRowId={(r) => `${r.owner.kind}:${r.owner.id}`}
                  loading={owners.fetching}
                  error={owners.failed ? t("storage.owners.loadFailed") : null}
                  {...(owners.onRetry ? { onRetry: owners.onRetry } : {})}
                  sorting={state.sorting}
                  onSortingChange={state.onSortingChange}
                  sortable={OWNER_SORT}
                  pagination={owners.pagination}
                  filtered={state.isFiltered}
                  searchQuery={state.q}
                  onResetFilters={state.reset}
                  columnWidths={{
                    rank: 56,
                    projects: 110,
                    bytes: 110,
                    share: 170,
                  }}
                />
              </div>
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
