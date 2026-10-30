import { useCallback, useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Inbox, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge, Button, DataTable, FilterBar } from "@shared/ui";
import type { AdminJob, AdminQueueSummary, JobState } from "@entities/session";
import type { QueueQuery } from "../api/opsApi";
import { formatDuration } from "../lib/format";
import {
  JOB_BADGE,
  JOB_KINDS,
  JOB_STATES,
  LONG_WAIT_S,
  isActive,
  runSeconds,
} from "../lib/jobs";
import { useDurationUnits } from "../lib/useDurationUnits";
import {
  Card,
  LoadFailed,
  LoadingRow,
  PageHeader,
  Stat,
  StatRow,
} from "./parts";

export type QueueViewProps = {
  summaryStatus: "loading" | "error" | "ready";
  summary: AdminQueueSummary | null;
  status: "loading" | "error" | "ready";
  jobs: readonly AdminJob[];
  /** Есть ещё задачи сверх показанных. */
  hasMore: boolean;
  query: QueueQuery;
  now: number;
  /** Количество запросов меняется фильтром, пока старая страница ещё на экране. */
  refreshing?: boolean;
  onQueryChange: (patch: Partial<QueueQuery>) => void;
  onLoadMore: () => void;
  onOpen: (job: AdminJob) => void;
  onCancel: (job: AdminJob) => void;
  onRetry?: () => void;
};

export const PAGE_STEP = 25;

/**
 * Строка таблицы. Всё меняющееся лежит в данных строки, а не в замыканиях колонок:
 * TanStack Table рисует ячейки как компоненты, и новая функция ячейки пересоздаёт её DOM.
 */
type Row = {
  job: AdminJob;
  wait: string;
  run: string;
  stuck: boolean;
  cancel: () => void;
};

/** Очередь задач: сводка по тегам, фильтры, таблица с отменой. */
export const QueueView = ({
  summaryStatus,
  summary,
  status,
  jobs,
  hasMore,
  query,
  now,
  onQueryChange,
  onLoadMore,
  onOpen,
  onCancel,
  onRetry,
}: QueueViewProps) => {
  const { t } = useTranslation("adminOps");
  const units = useDurationUnits();
  const dur = useCallback(
    (s: number | null) => (s === null ? "-" : formatDuration(s, units)),
    [units],
  );

  const columns = useMemo<ColumnDef<Row>[]>(
    () => [
      {
        id: "kind",
        header: t("queue.columns.kind"),
        enableSorting: false,
        cell: ({ row }) => (
          <span className="flex flex-col" style={{ gap: 1, minWidth: 0 }}>
            <span style={{ fontWeight: 600, fontSize: 13 }}>
              {t(`queue.kind.${row.original.job.kind}`, {
                defaultValue: row.original.job.kind,
              })}
            </span>
            <span
              className="mono"
              style={{ fontSize: 11, color: "var(--fg-2)" }}
            >
              {t(`queue.priority.${row.original.job.priority}`)}
            </span>
          </span>
        ),
      },
      {
        id: "who",
        header: t("queue.columns.who"),
        enableSorting: false,
        cell: ({ row }) => (
          <span className="flex flex-col" style={{ gap: 1, minWidth: 0 }}>
            <span style={{ fontSize: 13 }}>{row.original.job.user_name}</span>
            <span style={{ fontSize: 11.5, color: "var(--fg-2)" }}>
              {row.original.job.project_name ?? t("queue.noProject")}
            </span>
          </span>
        ),
      },
      {
        id: "status",
        header: t("queue.columns.status"),
        enableSorting: false,
        cell: ({ row }) => (
          <Badge
            variant={JOB_BADGE[row.original.job.status]}
            data-testid={`job-status-${row.original.job.id}`}
          >
            {t(`queue.status.${row.original.job.status}`)}
          </Badge>
        ),
      },
      {
        id: "wait",
        header: t("queue.columns.wait"),
        enableSorting: false,
        cell: ({ row }) => (
          <span
            style={{
              fontVariantNumeric: "tabular-nums",
              color: row.original.stuck ? "var(--c-warn)" : undefined,
              fontWeight: row.original.stuck ? 600 : undefined,
            }}
            data-testid={`job-wait-${row.original.job.id}`}
          >
            {row.original.wait}
          </span>
        ),
      },
      {
        id: "run",
        header: t("queue.columns.run"),
        enableSorting: false,
        cell: ({ row }) => row.original.run,
      },
      {
        id: "runner",
        header: t("queue.columns.runner"),
        enableSorting: false,
        cell: ({ row }) => row.original.job.runner_name ?? "-",
      },
      {
        id: "actions",
        header: () => (
          <span className="sr-only">{t("queue.columns.actions")}</span>
        ),
        enableSorting: false,
        cell: ({ row }) =>
          isActive(row.original.job) ? (
            <Button
              size="sm"
              variant="ghost"
              type="button"
              style={{ gap: 5 }}
              data-testid={`job-cancel-${row.original.job.id}`}
              onClick={(event) => {
                event.stopPropagation();
                row.original.cancel();
              }}
            >
              <XCircle size={13} aria-hidden="true" />
              {t("queue.cancel")}
            </Button>
          ) : null,
      },
    ],
    [t],
  );

  const needle = query.q.trim().toLowerCase();
  const rows = useMemo<Row[]>(
    () =>
      jobs
        .filter(
          (job) =>
            needle === "" ||
            job.user_name.toLowerCase().includes(needle) ||
            (job.project_name ?? "").toLowerCase().includes(needle),
        )
        .map((job) => ({
          job,
          wait: dur(job.wait_s),
          run: dur(runSeconds(job, now)),
          stuck: job.status === "queued" && job.wait_s >= LONG_WAIT_S,
          cancel: () => {
            onCancel(job);
          },
        })),
    [jobs, needle, now, dur, onCancel],
  );

  const filtered = query.status !== "" || query.kind !== "" || query.q !== "";

  return (
    <div className="flex flex-col" style={{ gap: 16 }} data-testid="queue-view">
      <PageHeader title={t("queue.title")} lead={t("queue.lead")} />

      {summaryStatus === "loading" && (
        <LoadingRow testId="queue-summary-loading" />
      )}
      {summaryStatus === "error" && (
        <LoadFailed text={t("queue.summaryFailed")} />
      )}
      {summaryStatus === "ready" && summary && (
        <>
          <StatRow>
            <Stat
              label={t("queue.stats.queued")}
              value={String(summary.queued)}
              testId="queue-stat-queued"
            />
            <Stat
              label={t("queue.stats.running")}
              value={String(summary.running)}
              testId="queue-stat-running"
            />
            <Stat
              label={t("queue.stats.oldest")}
              value={dur(summary.oldest_queued_age_s)}
              {...(summary.oldest_queued_age_s !== null &&
              summary.oldest_queued_age_s >= LONG_WAIT_S
                ? { tone: "warn" as const }
                : {})}
            />
            <Stat
              label={t("queue.stats.wait")}
              value={`${dur(summary.wait_p50_s)} / ${dur(summary.wait_p95_s)}`}
              hint={t("queue.stats.waitHint")}
            />
          </StatRow>
          {summary.classes.length > 0 && (
            <Card title={t("queue.classes.title")} testId="queue-classes">
              <table
                style={{
                  width: "100%",
                  fontSize: 12.5,
                  borderCollapse: "collapse",
                }}
              >
                <thead>
                  <tr style={{ color: "var(--fg-2)", textAlign: "left" }}>
                    <th
                      scope="col"
                      style={{ padding: "4px 0", fontWeight: 500 }}
                    >
                      {t("queue.classes.name")}
                    </th>
                    <th scope="col" style={{ fontWeight: 500 }}>
                      {t("queue.classes.queued")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {summary.classes.map((row) => (
                    <tr
                      key={row.name}
                      data-testid={`queue-class-${row.name}`}
                      style={{ borderTop: "1px solid var(--border)" }}
                    >
                      <td style={{ padding: "6px 0" }}>
                        <Badge variant="subtle">
                          {t(`queue.priority.${row.name}`, {
                            defaultValue: row.name,
                          })}
                        </Badge>
                      </td>
                      <td>{row.queued}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </>
      )}

      <FilterBar
        search={query.q}
        onSearchChange={(q) => {
          onQueryChange({ q });
        }}
        searchLabel={t("queue.search")}
        searchPlaceholder={t("queue.search")}
        filters={[
          {
            id: "status",
            label: t("queue.filters.status"),
            value: query.status,
            onChange: (value) => {
              onQueryChange({ status: value as JobState | "" });
            },
            options: JOB_STATES.map((s) => ({
              value: s,
              label: t(`queue.status.${s}`),
            })),
          },
          {
            id: "kind",
            label: t("queue.filters.kind"),
            value: query.kind,
            onChange: (kind) => {
              onQueryChange({ kind });
            },
            options: JOB_KINDS.map((k) => ({
              value: k,
              label: t(`queue.kind.${k}`),
            })),
          },
        ]}
        onReset={() => {
          onQueryChange({ q: "", status: "", kind: "" });
        }}
      />
      <DataTable
        caption={t("queue.caption")}
        columns={columns}
        data={rows}
        getRowId={(r) => r.job.id}
        loading={status === "loading"}
        error={status === "error" ? t("queue.loadFailed") : null}
        {...(onRetry ? { onRetry } : {})}
        emptyTitle={
          filtered ? t("queue.noMatch.title") : t("queue.empty.title")
        }
        emptyHint={filtered ? t("queue.noMatch.body") : t("queue.empty.body")}
        onRowClick={(r) => {
          onOpen(r.job);
        }}
      />
      {status === "ready" && jobs.length > 0 && (
        <div
          className="flex items-center"
          style={{ gap: 12, fontSize: 12, color: "var(--fg-2)" }}
        >
          <span data-testid="queue-count">
            {t("queue.count", { shown: jobs.length })}
          </span>
          {hasMore && (
            <Button
              size="sm"
              variant="ghost"
              type="button"
              onClick={onLoadMore}
              data-testid="queue-more"
            >
              <Inbox size={13} aria-hidden="true" />
              {t("queue.more")}
            </Button>
          )}
        </div>
      )}
    </div>
  );
};
