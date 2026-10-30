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
  localeTag,
  type CursorPaginationState,
  type ListQueryState,
  type PickerItem,
} from "@shared/lib";
import {
  ActiveFilters,
  Button,
  DataTable,
  DateRangeFilter,
  useDateRangeLabel,
  FilterMenu,
  KpiGrid,
  KpiTile,
  PersonCell,
  PickerFilter,
  SearchInput,
  StatusDot,
  usePickedItem,
  type ActiveFilter,
  type PickerSource,
} from "@shared/ui";
import {
  adminPickers,
  type AdminJob,
  type AdminQueueSummary,
} from "@entities/session";
import { formatDuration } from "../lib/format";
import {
  JOB_KINDS,
  JOB_STATES,
  JOB_TONE,
  LONG_WAIT_S,
  isActive,
  jobWhere,
  runSeconds,
} from "../lib/jobs";
import type { QueueFilter } from "../lib/lists";
import { personRef, shortRef, type PersonRef } from "../lib/people";
import { useDurationUnits } from "../lib/useDurationUnits";
import type { ViewStatus } from "../lib/viewStatus";
import { ViewState } from "./parts";

export type QueueViewProps = {
  summaryStatus: ViewStatus;
  summary: AdminQueueSummary | null;
  /** Первая страница: ready, когда пришла. */
  status: ViewStatus;
  /** Загруженные страницы подряд, новые первыми. */
  jobs: readonly AdminJob[];
  /** Идёт запрос: на экране прежние строки. */
  fetching?: boolean;
  /** Последний запрос не удался. */
  failed?: boolean;
  state: ListQueryState<QueueFilter, never>;
  /** «Показать ещё» по курсору сервера. */
  pagination: CursorPaginationState;
  /** Сколько задач сейчас идёт на личных раннерах; undefined: личные раннеры отключены на установке. */
  personalRunning?: number | null | undefined;
  now: number;
  onOpen: (job: AdminJob) => void;
  onCancel: (job: AdminJob) => void;
  onRetry?: () => void;
};

// Приоритеты по убыванию: срочные, обычные, фоновые; неизвестные в конце.
const CLASS_ORDER = ["interactive", "checks", "batch"];
const classRank = (name: string): number => {
  const i = CLASS_ORDER.indexOf(name);
  return i === -1 ? CLASS_ORDER.length : i;
};

/**
 * Строка таблицы. Всё меняющееся лежит в данных строки, а не в замыканиях колонок:
 * TanStack Table рисует ячейки как компоненты, и новая функция ячейки пересоздаёт её DOM.
 */
type Row = {
  job: AdminJob;
  person: PersonRef;
  wait: string;
  run: string | null;
  stuck: boolean;
  cancel: () => void;
};

/**
 * Имя выбранного в фильтре по строкам на экране: при фильтре по человеку,
 * проекту или раннеру каждая строка о нём, и имя приходит в ней от сервера.
 */
const knownFrom = (
  jobs: readonly AdminJob[],
  id: string,
  pick: (job: AdminJob) => PickerItem | null,
): PickerItem | null => {
  if (id === "") return null;
  for (const job of jobs) {
    const item = pick(job);
    if (item?.id === id) return item;
  }
  return null;
};

/** Очередь задач: сводка по состояниям, фильтры на сервере, таблица с отменой. */
export const QueueView = ({
  summaryStatus,
  summary,
  status,
  jobs,
  fetching = false,
  failed = false,
  state,
  pagination,
  personalRunning,
  now,
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

  // Пикеры ищут на сервере: человека, организацию, проект и раннер не
  // нужно знать заранее, сколько бы их ни было.
  const sources = useMemo(
    () => ({
      user: adminPickers.users(),
      org: adminPickers.orgs(),
      project: adminPickers.projects(),
      runner: adminPickers.runners(),
    }),
    [],
  );

  const columns = useMemo<ColumnDef<Row>[]>(
    () => [
      {
        id: "kind",
        header: t("queue.columns.kind"),
        enableSorting: false,
        cell: ({ row }) => {
          const { job } = row.original;
          // Название проекта бывает длинным: строка режется, таблица не уезжает вбок.
          return (
            <span className="ops-cell" style={{ maxWidth: 280 }}>
              <span className="ops-cell-title">
                {t(`queue.kind.${job.kind}`, { defaultValue: job.kind })}
              </span>
              <span className="ops-cell-sub">
                {t(`queue.priority.${job.priority}`, {
                  defaultValue: job.priority,
                })}
                {/* Без имени проекта строка не показывает идентификатор:
                    он есть в подробностях задачи. */}
                {job.project_name != null && ` · ${job.project_name}`}
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
        id: "where",
        header: t("queue.columns.where"),
        enableSorting: false,
        cell: ({ row }) => {
          const where = jobWhere(row.original.job);
          if (where === null) {
            return <span className="ops-muted">{t("queue.where.none")}</span>;
          }
          return (
            <span
              className="chip sans"
              data-testid={`queue-where-${row.original.job.id}`}
              data-where={where}
              style={{ fontSize: 11 }}
            >
              {t(`queue.where.${where}`)}
            </span>
          );
        },
      },
      {
        id: "runner",
        header: t("queue.columns.runner"),
        enableSorting: false,
        cell: ({ row }) =>
          row.original.job.runner_id === null ? (
            <span className="ops-muted">{t("queue.noRunner")}</span>
          ) : row.original.job.runner_name !== null ? (
            <span className="ops-ellipsis" title={row.original.job.runner_name}>
              {row.original.job.runner_name}
            </span>
          ) : (
            <span className="ops-code" title={row.original.job.runner_id}>
              {shortRef(row.original.job.runner_id)}
            </span>
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

  // Строки приходят с сервера уже отобранными и по порядку: здесь только подписи.
  const rows = useMemo<Row[]>(
    () =>
      jobs.map((job) => ({
        job,
        person: personRef(job.user_id, job.user_name, job.user_email),
        wait: dur(job.wait_s) ?? "",
        run: dur(runSeconds(job, now)),
        stuck: job.status === "queued" && job.wait_s >= LONG_WAIT_S,
        cancel: () => {
          onCancel(job);
        },
      })),
    [jobs, now, dur, onCancel],
  );

  const userId = state.filter("user_id");
  const orgId = state.filter("org_id");
  const projectId = state.filter("project_id");
  const runnerId = state.filter("runner_id");
  const runnerScope = state.filter("runner_scope");
  const knownUser = knownFrom(jobs, userId, (j) =>
    j.user_name
      ? {
          kind: "user",
          id: j.user_id,
          name: j.user_name,
          detail: j.user_email ?? null,
        }
      : null,
  );
  const knownProject = knownFrom(jobs, projectId, (j) =>
    j.project_id && j.project_name
      ? {
          kind: "project",
          id: j.project_id,
          name: j.project_name,
          detail: null,
        }
      : null,
  );
  const knownRunner = knownFrom(jobs, runnerId, (j) =>
    j.runner_id && j.runner_name
      ? { kind: "runner", id: j.runner_id, name: j.runner_name, detail: null }
      : null,
  );
  const user = usePickedItem(sources.user, userId || null, knownUser);
  const org = usePickedItem(sources.org, orgId || null, null);
  const project = usePickedItem(
    sources.project,
    projectId || null,
    knownProject,
  );
  const runner = usePickedItem(sources.runner, runnerId || null, knownRunner);

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

  const picked = (
    id: QueueFilter,
    label: string,
    value: string,
    item: PickerItem | null,
  ): ActiveFilter[] =>
    value
      ? [
          {
            id,
            label,
            value: item?.name ?? shortRef(value),
            onRemove: () => {
              state.setFilter(id, null);
            },
          },
        ]
      : [];
  const states = state.filters.state;
  const kinds = state.filters.kind;
  const from = state.filter("from");
  const to = state.filter("to");
  // Та же подпись, что на кнопке периода: «30 дней», а не две даты.
  const periodLabel = useDateRangeLabel({ from: from || null, to: to || null });
  const active: ActiveFilter[] = [
    ...(state.q
      ? [
          {
            id: "q",
            label: t("queue.filters.search"),
            value: state.q,
            onRemove: () => {
              state.setQ("");
            },
          },
        ]
      : []),
    ...(states.length > 0
      ? [
          {
            id: "state",
            label: t("queue.filters.status"),
            value: states.map((s) => t(`queue.status.${s}`)).join(", "),
            onRemove: () => {
              state.setFilter("state", null);
            },
          },
        ]
      : []),
    ...(kinds.length > 0
      ? [
          {
            id: "kind",
            label: t("queue.filters.kind"),
            value: kinds
              .map((k) => t(`queue.kind.${k}`, { defaultValue: k }))
              .join(", "),
            onRemove: () => {
              state.setFilter("kind", null);
            },
          },
        ]
      : []),
    ...(runnerScope
      ? [
          {
            id: "runner_scope",
            label: t("queue.filters.where"),
            value: t(`queue.where.${runnerScope}`),
            onRemove: () => {
              state.setFilter("runner_scope", null);
            },
          },
        ]
      : []),
    ...picked("user_id", t("queue.filters.user"), userId, user),
    ...picked("org_id", t("queue.filters.org"), orgId, org),
    ...picked("project_id", t("queue.filters.project"), projectId, project),
    ...picked("runner_id", t("queue.filters.runner"), runnerId, runner),
    ...(periodLabel
      ? [
          {
            id: "period",
            label: t("queue.filters.period"),
            value: periodLabel,
            onRemove: () => {
              state.setFilters({ from: null, to: null });
            },
          },
        ]
      : []),
  ];

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

  const pickerFilter = (
    id: "user_id" | "org_id" | "project_id" | "runner_id",
    label: string,
    source: PickerSource,
    known: PickerItem | null,
    placeholder: string,
  ) => (
    <PickerFilter
      label={label}
      source={source}
      value={state.filter(id) || null}
      known={known}
      searchPlaceholder={placeholder}
      testId={`queue-filter-${id.replace("_id", "")}`}
      onChange={(item) => {
        state.setFilter(id, item?.id ?? null);
      }}
    />
  );

  return (
    <div className="ops-stack" data-testid="queue-view">
      <KpiGrid>
        <KpiTile
          testId="queue-stat-queued"
          icon={<ListOrdered size={14} aria-hidden="true" />}
          label={t("queue.stats.queued")}
          value={(summary?.queued ?? 0).toLocaleString(localeTag())}
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
          value={(summary?.running ?? 0).toLocaleString(localeTag())}
          loading={kpiLoading}
          error={kpiError}
          secondary={
            // Сервер с личными раннерами: сколько из идущих задач на них.
            personalRunning === undefined ? (
              t("queue.stats.runningHint")
            ) : (
              <span data-testid="queue-stat-personal">
                {t("queue.stats.personal", { count: personalRunning ?? 0 })}
              </span>
            )
          }
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
          value={broken.toLocaleString(localeTag())}
          loading={kpiLoading}
          error={kpiError}
          tone={broken > 0 ? "danger" : "neutral"}
          secondary={t("queue.stats.failedHint", {
            count: done,
            n: done.toLocaleString(localeTag()),
          })}
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

      {/* Поиск находит задачу по id или по подстроке в проекте и человеке;
          пикеры сужают до одного человека, организации, проекта и раннера. */}
      <div
        role="search"
        aria-label={t("queue.filters.label")}
        className="fbar"
        data-testid="queue-filters"
      >
        <SearchInput
          className="fbar-search"
          value={state.q}
          onChange={state.setQ}
          label={t("queue.filters.search")}
          placeholder={t("queue.filters.searchPlaceholder")}
          busy={fetching}
          testId="queue-search"
        />
        <div className="fbar-extra">
          <FilterMenu
            label={t("queue.filters.status")}
            testId="queue-filter-state"
            values={states}
            onChange={(values) => {
              state.setFilter("state", values);
            }}
            options={JOB_STATES.map((s) => ({
              value: s,
              label: t(`queue.status.${s}`),
              ...(counts ? { count: counts[s] } : {}),
            }))}
          />
          <FilterMenu
            label={t("queue.filters.kind")}
            testId="queue-filter-kind"
            values={kinds}
            onChange={(values) => {
              state.setFilter("kind", values);
            }}
            options={JOB_KINDS.map((k) => ({
              value: k,
              label: t(`queue.kind.${k}`),
            }))}
          />
          <FilterMenu
            label={t("queue.filters.where")}
            testId="queue-filter-where"
            values={runnerScope ? [runnerScope] : []}
            onChange={(values) => {
              state.setFilter("runner_scope", values[0] ?? null);
            }}
            options={(["shared", "personal"] as const).map((scope) => ({
              value: scope,
              label: t(`queue.where.${scope}`),
            }))}
          />
          {pickerFilter(
            "user_id",
            t("queue.filters.user"),
            sources.user,
            knownUser,
            t("queue.filters.userPlaceholder"),
          )}
          {pickerFilter(
            "org_id",
            t("queue.filters.org"),
            sources.org,
            null,
            t("queue.filters.orgPlaceholder"),
          )}
          {pickerFilter(
            "project_id",
            t("queue.filters.project"),
            sources.project,
            knownProject,
            t("queue.filters.projectPlaceholder"),
          )}
          {pickerFilter(
            "runner_id",
            t("queue.filters.runner"),
            sources.runner,
            knownRunner,
            t("queue.filters.runnerPlaceholder"),
          )}
          <DateRangeFilter
            label={t("queue.filters.period")}
            testId="queue-filter-period"
            value={{ from: from || null, to: to || null }}
            onChange={(range) => {
              state.setFilters({ from: range.from, to: range.to });
            }}
          />
        </div>
        {active.length > 0 && (
          <div className="fbar-active">
            <ActiveFilters items={active} onReset={state.reset} />
          </div>
        )}
      </div>
      <DataTable
        className="ops-table"
        caption={t("queue.caption")}
        columns={columns}
        data={rows}
        getRowId={(r) => r.job.id}
        loading={status === "loading" || fetching}
        error={failed || status === "error" ? t("queue.loadFailed") : null}
        {...(onRetry ? { onRetry } : {})}
        emptyTitle={t("queue.empty.title")}
        emptyHint={t("queue.empty.body")}
        filtered={state.isFiltered}
        searchQuery={state.searchOnly}
        onResetFilters={state.reset}
        pagination={{
          ...pagination,
          pageSize: state.pageSize,
          pageSizes: state.pageSizes,
          onPageSizeChange: state.setPageSize,
        }}
        onRowClick={(r) => {
          onOpen(r.job);
        }}
      />
    </div>
  );
};
