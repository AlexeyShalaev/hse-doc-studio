import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import {
  ArrowRight,
  KeyRound,
  ListOrdered,
  LoaderCircle,
  Pause,
  Play,
  Plus,
  RotateCw,
  Server,
  Tag,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatPastTime, formatRelativeTime, localeTag } from "@shared/lib";
import {
  ActionMenu,
  Badge,
  Button,
  DataTable,
  EmptyState,
  FilterBar,
  FilterMenu,
  KpiGrid,
  KpiTile,
  ListRow,
  Meter,
  NoResults,
  Pagination,
  Section,
  SectionList,
  Select,
  StatusDot,
  Tooltip,
  type ActiveFilter,
  type KpiTone,
  type StatusDotStatus,
} from "@shared/ui";
import type {
  AdminQueueSummary,
  AdminRunner,
  AdminRunnerSummary,
  AdminRunnerToken,
} from "@entities/session";
import { formatDuration } from "../lib/format";
import { LONG_WAIT_S } from "../lib/jobs";
import {
  RUNNER_SORT,
  TOKEN_STATUSES,
  type ListView,
  type RunnerFilter,
  type RunnerSort,
  type TokenFilter,
  type TokenSort,
} from "../lib/lists";
import {
  RUNNER_STATUSES,
  liveRunners,
  quietRunners,
  type RunnerStatus,
} from "../lib/runnerStatus";
import { tokenStatus, type TokenStatus } from "../lib/tokenStatus";
import { useDurationUnits } from "../lib/useDurationUnits";
import type { ViewStatus } from "../lib/viewStatus";
import { Banner, ViewState } from "./parts";

export type RunnersViewProps = {
  runners: ListView<AdminRunner, RunnerFilter, RunnerSort>;
  tokens: ListView<AdminRunnerToken, TokenFilter, TokenSort>;
  /** Счётчики раннеров от сервера: плитки и числа у фильтра состояний. */
  counts: AdminRunnerSummary | null;
  countsStatus?: ViewStatus;
  /** Сводка очереди: сколько задач ждёт раннера и сколько выполняется. */
  summary?: AdminQueueSummary | null;
  summaryStatus?: ViewStatus;
  /** Занятые места по раннерам; null, пока не известно. */
  slots?: ReadonlyMap<string, number> | null;
  now: number;
  /** Идентификатор раннера, над которым идёт действие. */
  busyId?: string | null;
  onTogglePause: (runner: AdminRunner) => void;
  onRotate: (runner: AdminRunner) => void;
  onRevoke: (runner: AdminRunner) => void;
  onCreateToken: () => void;
  onRevokeToken: (token: AdminRunnerToken) => void;
  onOpenQueue?: (() => void) | undefined;
};

/** Строка таблицы: всё меняющееся лежит в данных, а не в замыканиях колонок (иначе ячейки пересоздаются). */
type Row = {
  runner: AdminRunner;
  status: RunnerStatus;
  seen: string;
  used: number | null;
  busy: boolean;
  pause: () => void;
  rotate: () => void;
  revoke: () => void;
  /** Показать раннеры с этим тегом или классом. */
  pickTag: (tag: string) => void;
  pickClass: (name: string) => void;
  /** Есть раннер новее: версия, до которой стоит обновить. */
  newer: string | null;
};

const DOT: Record<RunnerStatus, StatusDotStatus> = {
  online: "online",
  stale: "stale",
  offline: "offline",
  paused: "paused",
  revoked: "neutral",
};

const TOKEN_DOT: Record<TokenStatus, StatusDotStatus> = {
  active: "success",
  exhausted: "neutral",
  expired: "warning",
  revoked: "neutral",
};

/** Сравнение версий вида 0.3.0: по числам, а не по строкам. */
const compareVersions = (a: string, b: string): number => {
  const pa = a.split(".").map((x) => Number.parseInt(x, 10) || 0);
  const pb = b.split(".").map((x) => Number.parseInt(x, 10) || 0);
  for (let i = 0; i < Math.max(pa.length, pb.length); i += 1) {
    const d = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (d !== 0) return d;
  }
  return 0;
};

const TOKEN_ORDER: Record<string, TokenSort | `-${TokenSort}`> = {
  newest: "-created_at",
  expiring: "expires_at",
  label: "label",
};

/** Раннеры установки и токены регистрации. */
export const RunnersView = ({
  runners: list,
  tokens,
  counts,
  countsStatus = "ready",
  summary = null,
  summaryStatus = "ready",
  slots = null,
  now,
  busyId = null,
  onTogglePause,
  onRotate,
  onRevoke,
  onCreateToken,
  onRevokeToken,
  onOpenQueue,
}: RunnersViewProps) => {
  const { t } = useTranslation("adminOps");
  const units = useDurationUnits();
  const num = (value: number) => value.toLocaleString(localeTag());
  const { state } = list;

  const live = counts ? liveRunners(counts) : 0;
  const quiet = counts ? quietRunners(counts) : 0;
  const newest = counts?.newest_version ?? null;

  const columns = useMemo<ColumnDef<Row>[]>(
    () => [
      {
        id: "name",
        header: t("runners.columns.name"),
        cell: ({ row }) => {
          const { runner, status: st, pickClass } = row.original;
          return (
            <span
              className={st === "revoked" ? "ops-cell ops-dim-row" : "ops-cell"}
            >
              <span className="ops-cell-title">{runner.name}</span>
              {/* Обычный класс ничего не говорит: подписан только особый. */}
              {runner.resource_class !== "standard" && (
                <span className="ops-cell-sub">
                  <button
                    type="button"
                    className="ops-link"
                    title={t("runners.classFilter")}
                    onClick={() => {
                      pickClass(runner.resource_class);
                    }}
                  >
                    {t(`runners.class.${runner.resource_class}`, {
                      defaultValue: runner.resource_class,
                    })}
                  </button>
                </span>
              )}
            </span>
          );
        },
      },
      {
        id: "version",
        header: t("runners.columns.version"),
        sortDescFirst: true,
        cell: ({ row }) => {
          const { runner, newer } = row.original;
          return newer !== null ? (
            <Tooltip content={t("runners.newerVersion", { version: newer })}>
              <span
                className="ops-version"
                data-outdated="true"
                tabIndex={0}
                data-testid={`runner-outdated-${runner.id}`}
              >
                <TriangleAlert size={11} aria-hidden="true" />v{runner.version}
              </span>
            </Tooltip>
          ) : (
            <span className="ops-version" title={t("runners.versionOf")}>
              v{runner.version}
            </span>
          );
        },
      },
      {
        id: "status",
        header: t("runners.columns.status"),
        cell: ({ row }) => {
          const { runner, status: st, seen } = row.original;
          return (
            <span className="ops-cell">
              <span data-testid={`runner-status-${runner.id}`} data-status={st}>
                <StatusDot status={DOT[st]} label={t(`runners.status.${st}`)} />
              </span>
              {st !== "revoked" && (
                <span className="ops-cell-sub" style={{ paddingLeft: 16 }}>
                  {seen}
                </span>
              )}
            </span>
          );
        },
      },
      {
        id: "tags",
        header: t("runners.columns.tags"),
        enableSorting: false,
        cell: ({ row }) => (
          <span
            className={
              row.original.status === "revoked"
                ? "ops-tags ops-dim-row"
                : "ops-tags"
            }
          >
            {row.original.runner.tags.map((tag) => (
              <button
                key={tag}
                type="button"
                className="ops-tag-btn"
                title={t("runners.tagFilter", { tag })}
                onClick={() => {
                  row.original.pickTag(tag);
                }}
              >
                <Badge variant="subtle">{tag}</Badge>
              </button>
            ))}
          </span>
        ),
      },
      {
        id: "load",
        header: () => <span>{t("runners.columns.load")}</span>,
        enableSorting: false,
        cell: ({ row }) => {
          const { runner, status: st, used: busy } = row.original;
          const total = runner.concurrency;
          if (st === "revoked") return null;
          const taken = busy ?? 0;
          const share = total > 0 ? (taken / total) * 100 : 0;
          return (
            <span className="ops-load" data-testid={`runner-load-${runner.id}`}>
              <span className="ops-load-text">
                {busy === null
                  ? t("runners.slots", { count: total })
                  : t("runners.load", { used: taken, total })}
              </span>
              <Meter
                value={busy === null ? 0 : share}
                tone={share >= 100 ? "warning" : "neutral"}
                label={t("runners.loadLabel", { name: runner.name })}
              />
            </span>
          );
        },
      },
      {
        id: "actions",
        header: () => (
          <span className="sr-only">{t("runners.columns.actions")}</span>
        ),
        enableSorting: false,
        cell: ({ row }) => {
          const { runner: r, busy, pause, rotate, revoke } = row.original;
          if (r.revoked) return null;
          return (
            <span className="ops-row-actions">
              <ActionMenu
                label={t("runners.actionsLabel", { name: r.name })}
                testId={`runner-actions-${r.id}`}
                items={[
                  {
                    id: "pause",
                    label: r.paused ? t("runners.resume") : t("runners.pause"),
                    icon: r.paused ? (
                      <Play size={14} aria-hidden="true" />
                    ) : (
                      <Pause size={14} aria-hidden="true" />
                    ),
                    disabled: busy,
                    onSelect: pause,
                    testId: `runner-pause-${r.id}`,
                  },
                  {
                    id: "rotate",
                    label: t("runners.rotate"),
                    icon: <RotateCw size={14} aria-hidden="true" />,
                    disabled: busy,
                    onSelect: rotate,
                    testId: `runner-rotate-${r.id}`,
                  },
                  {
                    id: "revoke",
                    label: t("runners.revokeAction"),
                    icon: <Trash2 size={14} aria-hidden="true" />,
                    danger: true,
                    disabled: busy,
                    onSelect: revoke,
                    testId: `runner-revoke-${r.id}`,
                  },
                ]}
              />
            </span>
          );
        },
      },
    ],
    [t],
  );

  const { setFilter } = state;
  // Порядок строк задаёт сервер (sort): здесь только подписи к каждой.
  const rows = useMemo<Row[]>(
    () =>
      list.items.map((runner) => ({
        runner,
        status: runner.status,
        seen:
          runner.last_seen_at === null
            ? t("runners.neverSeen")
            : t("runners.seenAgo", {
                ago: formatPastTime(runner.last_seen_at, now),
              }),
        used: slots ? (slots.get(runner.id) ?? 0) : null,
        busy: busyId === runner.id,
        pause: () => {
          onTogglePause(runner);
        },
        rotate: () => {
          onRotate(runner);
        },
        revoke: () => {
          onRevoke(runner);
        },
        pickTag: (tag: string) => {
          setFilter("tag", tag);
        },
        pickClass: (name: string) => {
          setFilter("resource_class", name);
        },
        newer:
          newest !== null &&
          !runner.revoked &&
          compareVersions(runner.version, newest) < 0
            ? newest
            : null,
      })),
    [
      list.items,
      now,
      t,
      slots,
      busyId,
      newest,
      onTogglePause,
      onRotate,
      onRevoke,
      setFilter,
    ],
  );

  const noneOnline = counts !== null && live > 0 && counts.online === 0;
  const waiting = summary?.queued ?? null;
  const oldest = summary?.oldest_queued_age_s ?? null;
  const onlineTone: KpiTone =
    counts === null || counts.online === 0
      ? "danger"
      : quiet > 0
        ? "warning"
        : "success";

  const statusLabels = state.filters.status.map((s) =>
    t(`runners.status.${s}`),
  );
  const outdatedValue = state.filter("outdated");
  const active: ActiveFilter[] = [
    ...(state.q
      ? [
          {
            id: "q",
            label: t("filters.search"),
            value: state.q,
            onRemove: () => {
              state.setQ("");
            },
          },
        ]
      : []),
    ...(statusLabels.length > 0
      ? [
          {
            id: "status",
            label: t("runners.filters.status"),
            value: statusLabels.join(", "),
            onRemove: () => {
              state.setFilter("status", null);
            },
          },
        ]
      : []),
    ...(outdatedValue
      ? [
          {
            id: "outdated",
            label: t("runners.filters.version"),
            value:
              outdatedValue === "true"
                ? t("runners.version.outdated")
                : t("runners.version.current"),
            onRemove: () => {
              state.setFilter("outdated", null);
            },
          },
        ]
      : []),
    ...(state.filter("tag")
      ? [
          {
            id: "tag",
            label: t("runners.filters.tag"),
            value: state.filter("tag"),
            onRemove: () => {
              state.setFilter("tag", null);
            },
          },
        ]
      : []),
    ...(state.filter("resource_class")
      ? [
          {
            id: "resource_class",
            label: t("runners.filters.class"),
            value: t(`runners.class.${state.filter("resource_class")}`, {
              defaultValue: state.filter("resource_class"),
            }),
            onRemove: () => {
              state.setFilter("resource_class", null);
            },
          },
        ]
      : []),
  ];

  // Пусто без всяких условий: раннеров нет вовсе, ведём к созданию токена.
  const noRunners =
    list.status === "ready" &&
    !list.failed &&
    !state.isFiltered &&
    list.total === 0;
  const noTokens =
    tokens.status === "ready" &&
    !tokens.failed &&
    !tokens.state.isFiltered &&
    tokens.total === 0;

  if (list.status === "forbidden") {
    return (
      <div className="ops-stack" data-testid="runners-view">
        <ViewState status="forbidden" errorText="" testId="runners" />
      </div>
    );
  }

  return (
    <div className="ops-stack" data-testid="runners-view">
      {noneOnline && (
        <Banner
          tone="danger"
          title={t("runners.noneOnline.title")}
          testId="runners-none-online"
          action={
            onOpenQueue && waiting ? (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={onOpenQueue}
                style={{ gap: 6 }}
              >
                {t("runners.noneOnline.queue", { count: waiting })}
                <ArrowRight size={13} aria-hidden="true" />
              </Button>
            ) : undefined
          }
        >
          {t("runners.noneOnline.body")}
        </Banner>
      )}

      {(countsStatus === "loading" || (counts !== null && live > 0)) && (
        <KpiGrid>
          <KpiTile
            testId="runners-stat-online"
            icon={<Server size={14} aria-hidden="true" />}
            label={t("runners.stats.online")}
            value={num(counts?.online ?? 0)}
            loading={countsStatus === "loading"}
            unit={t("runners.stats.of", { total: num(live) })}
            tone={onlineTone}
            secondary={
              counts === null
                ? null
                : quiet === 0 && counts.paused === 0
                  ? t("runners.stats.allOnline")
                  : [
                      quiet > 0
                        ? t("runners.stats.silent", { count: quiet })
                        : null,
                      counts.paused > 0
                        ? t("runners.stats.paused", { count: counts.paused })
                        : null,
                    ]
                      .filter(Boolean)
                      .join(", ")
            }
          />
          <KpiTile
            testId="runners-stat-running"
            icon={<LoaderCircle size={14} aria-hidden="true" />}
            label={t("runners.stats.running")}
            value={num(summary?.running ?? 0)}
            loading={summaryStatus === "loading"}
            error={
              summaryStatus === "error" || summaryStatus === "forbidden"
                ? t("runners.stats.waitingFailed")
                : undefined
            }
            secondary={t("runners.stats.runningHint")}
          />
          <KpiTile
            testId="runners-stat-waiting"
            icon={<ListOrdered size={14} aria-hidden="true" />}
            label={t("runners.stats.waiting")}
            value={num(waiting ?? 0)}
            loading={summaryStatus === "loading"}
            error={
              summaryStatus === "error" || summaryStatus === "forbidden"
                ? t("runners.stats.waitingFailed")
                : undefined
            }
            tone={
              oldest !== null && oldest >= LONG_WAIT_S ? "warning" : "neutral"
            }
            secondary={
              oldest === null
                ? t("runners.stats.nobodyWaits")
                : t("runners.stats.oldest", {
                    ago: formatDuration(oldest, units),
                  })
            }
          />
          <KpiTile
            testId="runners-stat-version"
            icon={<Tag size={14} aria-hidden="true" />}
            label={t("runners.stats.version")}
            value={newest ?? ""}
            loading={countsStatus === "loading"}
            tone={(counts?.outdated ?? 0) > 0 ? "warning" : "neutral"}
            secondary={
              (counts?.outdated ?? 0) > 0
                ? t("runners.stats.outdated", { count: counts?.outdated ?? 0 })
                : t("runners.stats.sameVersion")
            }
          />
        </KpiGrid>
      )}

      {noRunners ? (
        <EmptyState
          framed
          testId="runners-empty"
          icon={<Server size={18} />}
          title={t("runners.empty.title")}
          description={t("runners.empty.body")}
          action={
            <Button
              type="button"
              size="sm"
              onClick={onCreateToken}
              style={{ gap: 6 }}
              data-testid="runners-empty-create"
            >
              <Plus size={14} aria-hidden="true" />
              {t("tokens.create")}
            </Button>
          }
        />
      ) : (
        <>
          <FilterBar
            search={state.q}
            onSearchChange={state.setQ}
            searchLabel={t("runners.search")}
            searchPlaceholder={t("runners.searchPlaceholder")}
            busy={list.fetching}
            onReset={state.reset}
            total={list.status === "ready" ? list.total : null}
            active={active}
            extra={
              <>
                <FilterMenu
                  label={t("runners.filters.status")}
                  testId="runners-filter-status"
                  values={state.filters.status}
                  onChange={(values) => {
                    state.setFilter("status", values);
                  }}
                  options={RUNNER_STATUSES.map((s) => ({
                    value: s,
                    label: t(`runners.status.${s}`),
                    ...(counts ? { count: counts[s] } : {}),
                  }))}
                />
                <FilterMenu
                  label={t("runners.filters.version")}
                  testId="runners-filter-version"
                  single
                  values={outdatedValue ? [outdatedValue] : []}
                  onChange={(values) => {
                    state.setFilter("outdated", values[0] ?? null);
                  }}
                  options={[
                    {
                      value: "true",
                      label: t("runners.version.outdated"),
                      ...(counts ? { count: counts.outdated } : {}),
                    },
                    {
                      value: "false",
                      label: t("runners.version.current"),
                      ...(counts
                        ? { count: Math.max(0, live - counts.outdated) }
                        : {}),
                    },
                  ]}
                />
              </>
            }
          />
          <DataTable
            className="ops-table ops-static"
            caption={t("runners.caption")}
            columns={columns}
            data={rows}
            getRowId={(r) => r.runner.id}
            loading={list.fetching}
            error={list.failed ? t("runners.loadFailed") : null}
            {...(list.onRetry ? { onRetry: list.onRetry } : {})}
            sorting={state.sorting}
            onSortingChange={state.onSortingChange}
            sortable={RUNNER_SORT}
            pagination={list.pagination}
            filtered={state.isFiltered}
            searchQuery={state.q}
            onResetFilters={state.reset}
            columnWidths={{
              version: 96,
              status: 210,
              load: 120,
              actions: 56,
            }}
          />
        </>
      )}

      {/* Ни раннеров, ни токенов: пустое состояние выше уже ведёт к созданию
          токена, второй пустой блок с тем же советом не нужен. */}
      {!(noRunners && noTokens) && (
        <TokensSection
          tokens={tokens}
          now={now}
          onRevokeToken={onRevokeToken}
        />
      )}
    </div>
  );
};

/** Токены регистрации: свой поиск, фильтр состояния, порядок и страницы. */
const TokensSection = ({
  tokens,
  now,
  onRevokeToken,
}: {
  tokens: RunnersViewProps["tokens"];
  now: number;
  onRevokeToken: (token: AdminRunnerToken) => void;
}) => {
  const { t } = useTranslation("adminOps");
  const { state } = tokens;
  const order =
    Object.entries(TOKEN_ORDER).find(
      ([, value]) =>
        state.sort !== null &&
        value === (state.sort.desc ? `-${state.sort.field}` : state.sort.field),
    )?.[0] ?? "newest";
  const empty =
    tokens.status === "ready" &&
    !tokens.failed &&
    !state.isFiltered &&
    tokens.total === 0;

  return (
    <Section
      title={t("tokens.title")}
      description={t("tokens.lead")}
      flush
      testId="runner-tokens"
      footer={
        <span style={{ fontSize: 12, color: "var(--fg-2)" }}>
          {t("tokens.howTo")}
        </span>
      }
    >
      {!empty && tokens.status !== "forbidden" && (
        <div className="ops-section-bar">
          <FilterBar
            search={state.q}
            onSearchChange={state.setQ}
            searchLabel={t("tokens.search")}
            searchPlaceholder={t("tokens.searchPlaceholder")}
            busy={tokens.fetching}
            onReset={state.reset}
            filters={[
              {
                id: "status",
                label: t("tokens.filters.status"),
                value: state.filter("status"),
                onChange: (value) => {
                  state.setFilter("status", value === "" ? null : value);
                },
                options: TOKEN_STATUSES.map((s) => ({
                  value: s,
                  label: t(`tokens.status.${s}`),
                })),
              },
            ]}
            extra={
              <span className="ops-sort">
                <Select
                  value={order}
                  ariaLabel={t("tokens.sort.label")}
                  onValueChange={(value) => {
                    const param = TOKEN_ORDER[value] ?? "-created_at";
                    const desc = param.startsWith("-");
                    state.setSort({
                      field: (desc ? param.slice(1) : param) as TokenSort,
                      desc,
                    });
                  }}
                  options={[
                    { value: "newest", label: t("tokens.sort.newest") },
                    { value: "expiring", label: t("tokens.sort.expiring") },
                    { value: "label", label: t("tokens.sort.byLabel") },
                  ]}
                />
              </span>
            }
          />
        </div>
      )}
      {tokens.status !== "ready" && (
        <div style={{ padding: "0 20px 16px" }}>
          <ViewState
            status={tokens.status}
            errorText={t("tokens.loadFailed")}
            onRetry={tokens.onRetry}
            testId="tokens"
            compact
            skeleton={<TokensSkeleton />}
          />
        </div>
      )}
      {tokens.status === "ready" && empty && (
        <div style={{ padding: "0 20px 16px" }}>
          <EmptyState
            testId="tokens-empty"
            icon={<KeyRound size={18} />}
            title={t("tokens.empty.title")}
            description={t("tokens.empty.body")}
          />
        </div>
      )}
      {tokens.status === "ready" &&
        !empty &&
        tokens.items.length === 0 &&
        !tokens.failed && (
          <div style={{ padding: "0 20px 16px" }}>
            <NoResults
              compact
              query={state.q}
              onReset={state.reset}
              testId="tokens-no-results"
            />
          </div>
        )}
      {tokens.status === "ready" && tokens.failed && (
        <div style={{ padding: "0 20px 16px" }}>
          <ViewState
            status="error"
            errorText={t("tokens.loadFailed")}
            onRetry={tokens.onRetry}
            testId="tokens"
            compact
          />
        </div>
      )}
      {tokens.status === "ready" && tokens.items.length > 0 && (
        <div
          style={{
            opacity: tokens.fetching ? 0.6 : 1,
            transition: "opacity 0.12s",
          }}
          aria-busy={tokens.fetching}
        >
          <SectionList label={t("tokens.title")}>
            {tokens.items.map((token) => (
              <TokenRow
                key={token.id}
                token={token}
                now={now}
                onRevoke={onRevokeToken}
              />
            ))}
          </SectionList>
        </div>
      )}
      {tokens.status === "ready" && tokens.total > 0 && (
        <div className="ops-section-pager">
          <Pagination {...tokens.pagination} />
        </div>
      )}
    </Section>
  );
};

const TokenRow = ({
  token,
  now,
  onRevoke,
}: {
  token: AdminRunnerToken;
  now: number;
  onRevoke: (token: AdminRunnerToken) => void;
}) => {
  const { t } = useTranslation("adminOps");
  const st = tokenStatus(token, now);
  const active = st === "active";
  const label = token.label === "" ? t("tokens.noLabel") : token.label;
  return (
    <div
      data-testid={`token-${token.id}`}
      data-status={st}
      className={active ? undefined : "ops-dim-row"}
    >
      <ListRow
        icon={<KeyRound size={15} />}
        tone={active ? "accent" : "neutral"}
        title={label}
        description={[
          t("tokens.uses", { uses: token.uses, max: token.max_uses }),
          active && token.expires_at
            ? t("tokens.expires", {
                when: formatRelativeTime(token.expires_at, now),
              })
            : st === "expired" && token.expires_at
              ? t("tokens.expired", {
                  when: formatPastTime(token.expires_at, now),
                })
              : null,
        ]
          .filter(Boolean)
          .join(" · ")}
        meta={
          <>
            <StatusDot
              status={TOKEN_DOT[st]}
              label={t(`tokens.status.${st}`)}
            />
            {/* Слот действий одной ширины у всех строк: состояния
              стоят ровной колонкой, как в таблицах. */}
            <span className="ops-token-actions">
              {active && (
                <ActionMenu
                  label={t("tokens.actionsLabel", { label })}
                  testId={`token-actions-${token.id}`}
                  items={[
                    {
                      id: "revoke",
                      label: t("tokens.revoke"),
                      icon: <Trash2 size={14} aria-hidden="true" />,
                      danger: true,
                      testId: `token-revoke-${token.id}`,
                      onSelect: () => {
                        onRevoke(token);
                      },
                    },
                  ]}
                />
              )}
            </span>
          </>
        }
      />
    </div>
  );
};

const TokensSkeleton = () => (
  <div className="flex flex-col" style={{ gap: 14, padding: "4px 0" }}>
    {[60, 45, 52].map((w) => (
      <span key={w} className="adm-skel" style={{ width: `${String(w)}%` }} />
    ))}
  </div>
);
