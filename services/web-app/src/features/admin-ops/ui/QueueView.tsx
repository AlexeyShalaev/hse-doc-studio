import { useCallback, useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import {
  CircleAlert,
  Clock,
  ListOrdered,
  LoaderCircle,
  Timer,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  Button,
  DataTable,
  FilterBar,
  KpiGrid,
  KpiTile,
  PersonCell,
  StatusDot,
} from "@shared/ui";
import type { AdminJob, AdminQueueSummary, JobState } from "@entities/session";
import type { QueueQuery } from "../api/opsApi";
import { formatDuration } from "../lib/format";
import {
  JOB_KINDS,
  JOB_STATES,
  JOB_TONE,
  LONG_WAIT_S,
  isActive,
  runSeconds,
} from "../lib/jobs";
import { personRef, type OpsPerson, type PersonRef } from "../lib/people";
import { useDurationUnits } from "../lib/useDurationUnits";
import type { ViewStatus } from "../lib/viewStatus";
import { ViewState } from "./parts";

export type QueueViewProps = {
  summaryStatus: ViewStatus;
  summary: AdminQueueSummary | null;
  status: ViewStatus;
  jobs: readonly AdminJob[];
  /** Есть ещё задачи сверх показанных. */
  hasMore: boolean;
  /** Имена и почты людей по идентификатору. */
  people?: ReadonlyMap<string, OpsPerson>;
  /** Имена раннеров по идентификатору. */
  runnerNames?: ReadonlyMap<string, string>;
  query: QueueQuery;
  now: number;
  onQueryChange: (patch: Partial<QueueQuery>) => void;
  onLoadMore: () => void;
  onOpen: (job: AdminJob) => void;
  onCancel: (job: AdminJob) => void;
  onRetry?: () => void;
};

export const PAGE_STEP = 25;

// Приоритеты по убыванию: срочные, обычные, фоновые; неизвестные в конце.
const CLASS_ORDER = ["interactive", "checks", "batch"];
const classRank = (name: string): number => {
  const i = CLASS_ORDER.indexOf(name);
  return i === -1 ? CLASS_ORDER.length : i;
};

const NO_PEOPLE: ReadonlyMap<string, OpsPerson> = new Map();
const NO_RUNNERS: ReadonlyMap<string, string> = new Map();

/**
 * Строка таблицы. Всё меняющееся лежит в данных строки, а не в замыканиях колонок:
 * TanStack Table рисует ячейки как компоненты, и новая функция ячейки пересоздаёт её DOM.
 */
type Row = {
  job: AdminJob;
  person: PersonRef;
  runner: string | null;
  wait: string;
  run: string | null;
  stuck: boolean;
  cancel: () => void;
};

/** Очередь задач: сводка по состояниям, фильтры, таблица с отменой. */
export const QueueView = ({
  summaryStatus,
  summary,
  status,
  jobs,
  hasMore,
  people = NO_PEOPLE,
  runnerNames = NO_RUNNERS,
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
    (s: number | null) => (s === null ? null : formatDuration(s, units)),
    [units],
  );

  const columns = useMemo<ColumnDef<Row>[]>(
    () => [
      {
        id: "kind",
        header: t("queue.columns.kind"),
        enableSorting: false,
        cell: ({ row }) => {
          const { job } = row.original;
          return (
            <span className="ops-cell">
              <span className="ops-cell-title">
                {t(`queue.kind.${job.kind}`, { defaultValue: job.kind })}
              </span>
              <span className="ops-cell-sub">
                {t(`queue.priority.${job.priority}`, {
                  defaultValue: job.priority,
                })}
                {/* Имени проекта сервер не отдаёт: без него строка не показывает
                    идентификатор, он есть в подробностях задачи. */}
                {job.project_name !== null && ` · ${job.project_name}`}
              </span>
            </span>
          );
        },
      },
      {
        id: "who",
        header: t("queue.columns.who"),
        enableSorting: false,
        cell: ({ row }) => {
          const { person } = row.original;
          return (
            <PersonCell
              id={person.id}
              name={person.name}
              email={person.email}
              fallback={t("queue.unknownPerson")}
            />
          );
        },
      },
      {
        id: "status",
        header: t("queue.columns.status"),
        enableSorting: false,
        cell: ({ row }) => (
          <span data-testid={`job-status-${row.original.job.id}`}>
            <StatusDot
              status={JOB_TONE[row.original.job.status]}
              label={t(`queue.status.${row.original.job.status}`)}
            />
          </span>
        ),
      },
      {
        id: "wait",
        header: () => (
          <span className="ops-num">{t("queue.columns.wait")}</span>
        ),
        enableSorting: false,
        cell: ({ row }) => (
          <span
            className="ops-num"
            style={
              row.original.stuck
                ? { color: "var(--c-warn)", fontWeight: 600 }
                : undefined
            }
            data-testid={`job-wait-${row.original.job.id}`}
          >
            {row.original.wait}
          </span>
        ),
      },
      {
        id: "run",
        header: () => <span className="ops-num">{t("queue.columns.run")}</span>,
        enableSorting: false,
        cell: ({ row }) => (
          <span className="ops-num">
            {row.original.run ?? (
              <span className="ops-muted">{t("queue.notStarted")}</span>
            )}
          </span>
        ),
      },
      {
        id: "runner",
        header: t("queue.columns.runner"),
        enableSorting: false,
        cell: ({ row }) =>
          row.original.runner ?? (
            <span className="ops-muted">{t("queue.noRunner")}</span>
          ),
      },
      {
        id: "actions",
        header: () => (
          <span className="sr-only">{t("queue.columns.actions")}</span>
        ),
        enableSorting: false,
        cell: ({ row }) =>
          isActive(row.original.job) ? (
            <span className="ops-row-actions" data-reveal="hover">
              <Button
                size="sm"
                variant="ghost"
                type="button"
                style={{ gap: 5 }}
                aria-label={t("queue.cancelLabel", {
                  kind: t(`queue.kind.${row.original.job.kind}`, {
                    defaultValue: row.original.job.kind,
                  }),
                })}
                data-testid={`job-cancel-${row.original.job.id}`}
                onClick={(event) => {
                  event.stopPropagation();
                  row.original.cancel();
                }}
              >
                <XCircle size={13} aria-hidden="true" />
                {t("queue.cancel")}
              </Button>
            </span>
          ) : null,
      },
    ],
    [t],
  );

  const needle = query.q.trim().toLowerCase();
  const rows = useMemo<Row[]>(
    () =>
      jobs
        .map((job) => {
          const person = personRef(job.user_id, job.user_name, people);
          const runner = job.runner_id
            ? (runnerNames.get(job.runner_id) ?? job.runner_name)
            : null;
          return {
            job,
            person,
            runner,
            wait: dur(job.wait_s) ?? "",
            run: dur(runSeconds(job, now)),
            stuck: job.status === "queued" && job.wait_s >= LONG_WAIT_S,
            cancel: () => {
              onCancel(job);
            },
          };
        })
        .filter(
          ({ job, person, runner }) =>
            needle === "" ||
            [
              person.name,
              person.email,
              job.project_name,
              job.project_id,
              runner,
              t(`queue.kind.${job.kind}`, { defaultValue: job.kind }),
            ].some((v) => v?.toLowerCase().includes(needle)),
        ),
    [jobs, people, runnerNames, needle, now, dur, onCancel, t],
  );

  const filtered = query.status !== "" || query.kind !== "" || query.q !== "";
  const counts = summary?.by_state;
  const done = counts
    ? counts.succeeded + counts.failed + counts.cancelled + counts.timed_out
    : 0;
  const broken = counts ? counts.failed + counts.timed_out : 0;
  const oldest = summary?.oldest_queued_age_s ?? null;
  const kpiLoading = summaryStatus === "loading";
  const kpiError =
    summaryStatus === "error" || summaryStatus === "forbidden"
      ? t("queue.summaryFailed")
      : undefined;

  // Нет прав или не загрузилось ничего: одно состояние вместо пустых плиток и таблицы.
  if (
    status === "forbidden" ||
    (status === "error" && summaryStatus !== "ready")
  ) {
    return (
      <div className="ops-stack" data-testid="queue-view">
        <ViewState
          status={status}
          errorText={t("queue.loadFailed")}
          onRetry={onRetry}
          testId="queue"
        />
      </div>
    );
  }

  return (
    <div className="ops-stack" data-testid="queue-view">
      <KpiGrid>
        <KpiTile
          testId="queue-stat-queued"
          icon={<ListOrdered size={14} aria-hidden="true" />}
          label={t("queue.stats.queued")}
          value={summary?.queued ?? 0}
          loading={kpiLoading}
          error={kpiError}
          tone={
            oldest !== null && oldest >= LONG_WAIT_S ? "warning" : "neutral"
          }
          secondary={
            oldest === null
              ? t("queue.stats.nobodyWaits")
              : t("queue.stats.oldest", { ago: dur(oldest) })
          }
        />
        <KpiTile
          testId="queue-stat-running"
          icon={<LoaderCircle size={14} aria-hidden="true" />}
          label={t("queue.stats.running")}
          value={summary?.running ?? 0}
          loading={kpiLoading}
          error={kpiError}
          secondary={t("queue.stats.runningHint")}
        />
        <KpiTile
          testId="queue-stat-wait"
          icon={<Clock size={14} aria-hidden="true" />}
          label={t("queue.stats.wait")}
          value={dur(summary?.wait_p50_s ?? null) ?? t("queue.stats.noData")}
          loading={kpiLoading}
          error={kpiError}
          secondary={
            summary?.wait_p95_s == null
              ? t("queue.stats.waitHint")
              : t("queue.stats.p95", { value: dur(summary.wait_p95_s) })
          }
        />
        <KpiTile
          testId="queue-stat-failed"
          icon={<CircleAlert size={14} aria-hidden="true" />}
          label={t("queue.stats.failed")}
          value={broken}
          loading={kpiLoading}
          error={kpiError}
          tone={broken > 0 ? "danger" : "neutral"}
          secondary={t("queue.stats.failedHint", { count: done })}
        />
      </KpiGrid>

      {summary && summary.classes.length > 0 && (
        <div className="ops-classes" data-testid="queue-classes">
          <Timer size={14} aria-hidden="true" />
          <span>{t("queue.classes.title")}</span>
          {[...summary.classes]
            .sort((a, b) => classRank(a.name) - classRank(b.name))
            .map((row) => (
              <span
                key={row.name}
                className="ops-classes-item"
                data-testid={`queue-class-${row.name}`}
              >
                {t(`queue.classes.name.${row.name}`, {
                  defaultValue: t(`queue.priority.${row.name}`, {
                    defaultValue: row.name,
                  }),
                })}
                <strong>{row.queued}</strong>
              </span>
            ))}
        </div>
      )}

      <FilterBar
        search={query.q}
        onSearchChange={(q) => {
          onQueryChange({ q });
        }}
        searchLabel={t("queue.search")}
        searchPlaceholder={t("queue.searchPlaceholder")}
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
              ...(counts ? { count: counts[s] } : {}),
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
        className="ops-table"
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
        {...(filtered
          ? {
              emptyAction: (
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    onQueryChange({ q: "", status: "", kind: "" });
                  }}
                >
                  {t("queue.noMatch.reset")}
                </Button>
              ),
            }
          : {})}
        onRowClick={(r) => {
          onOpen(r.job);
        }}
      />
      {status === "ready" && jobs.length > 0 && (
        <div className="ops-foot">
          <span data-testid="queue-count">
            {t("queue.count", { count: jobs.length })}
          </span>
          {hasMore && (
            <Button
              size="sm"
              variant="secondary"
              type="button"
              onClick={onLoadMore}
              data-testid="queue-more"
            >
              {t("queue.more")}
            </Button>
          )}
        </div>
      )}
    </div>
  );
};
