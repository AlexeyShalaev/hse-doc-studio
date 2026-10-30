import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import {
  ArrowRight,
  Cpu,
  KeyRound,
  ListOrdered,
  Pause,
  Play,
  Plus,
  RotateCw,
  Server,
  Tag,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatPastTime, formatRelativeTime } from "@shared/lib";
import {
  ActionMenu,
  Badge,
  Button,
  DataTable,
  EmptyState,
  KpiGrid,
  KpiTile,
  ListRow,
  Meter,
  Section,
  SectionList,
  StatusDot,
  type KpiTone,
  type StatusDotStatus,
} from "@shared/ui";
import type {
  AdminQueueSummary,
  AdminRunner,
  AdminRunnerToken,
} from "@entities/session";
import { formatDuration } from "../lib/format";
import { LONG_WAIT_S } from "../lib/jobs";
import { runnerStatus, type RunnerStatus } from "../lib/runnerStatus";
import { tokenStatus, type TokenStatus } from "../lib/tokenStatus";
import { useDurationUnits } from "../lib/useDurationUnits";
import type { ViewStatus } from "../lib/viewStatus";
import { Banner, ViewState } from "./parts";

export type RunnersViewProps = {
  status: ViewStatus;
  runners: readonly AdminRunner[];
  tokensStatus: ViewStatus;
  tokens: readonly AdminRunnerToken[];
  /** Сводка очереди: сколько задач ждёт раннера. */
  summary?: AdminQueueSummary | null;
  summaryStatus?: ViewStatus;
  /** Занятые места по раннерам; null, пока не известно. */
  slots?: ReadonlyMap<string, number> | null;
  now: number;
  /** Идентификатор раннера, над которым идёт действие. */
  busyId?: string | null;
  onRetry?: () => void;
  onRetryTokens?: () => void;
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

// Отозванные внизу: они только для истории.
const ORDER: Record<RunnerStatus, number> = {
  online: 0,
  stale: 1,
  paused: 2,
  offline: 3,
  revoked: 4,
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

/** Раннеры установки и токены регистрации. */
export const RunnersView = ({
  status,
  runners,
  tokensStatus,
  tokens,
  summary = null,
  summaryStatus = "ready",
  slots = null,
  now,
  busyId = null,
  onRetry,
  onRetryTokens,
  onTogglePause,
  onRotate,
  onRevoke,
  onCreateToken,
  onRevokeToken,
  onOpenQueue,
}: RunnersViewProps) => {
  const { t } = useTranslation("adminOps");
  const units = useDurationUnits();

  const live = runners.filter((r) => !r.revoked);
  const statuses = live.map((r) => runnerStatus(r, now));
  const online = statuses.filter((s) => s === "online").length;
  const paused = statuses.filter((s) => s === "paused").length;
  const silent = statuses.filter(
    (s) => s === "stale" || s === "offline",
  ).length;
  const onlineRunners = live.filter((r) => runnerStatus(r, now) === "online");
  const capacity = onlineRunners.reduce((sum, r) => sum + r.concurrency, 0);
  const used = slots
    ? onlineRunners.reduce((sum, r) => sum + (slots.get(r.id) ?? 0), 0)
    : null;
  const newest = live
    .map((r) => r.version)
    .reduce<string | null>(
      (best, v) => (best === null || compareVersions(v, best) > 0 ? v : best),
      null,
    );
  const outdated = newest
    ? live.filter((r) => compareVersions(r.version, newest) < 0).length
    : 0;

  const columns = useMemo<ColumnDef<Row>[]>(
    () => [
      {
        id: "name",
        header: t("runners.columns.name"),
        enableSorting: false,
        cell: ({ row }) => {
          const { runner, status: st } = row.original;
          return (
            <span
              className={st === "revoked" ? "ops-cell ops-dim-row" : "ops-cell"}
            >
              <span className="ops-cell-title">{runner.name}</span>
              <span className="ops-cell-sub">
                <span className="ops-version" title={t("runners.versionOf")}>
                  v{runner.version}
                </span>
                {/* Обычный класс ничего не говорит: подписан только особый. */}
                {runner.resource_class !== "standard" && (
                  <>
                    {" · "}
                    {t(`runners.class.${runner.resource_class}`, {
                      defaultValue: runner.resource_class,
                    })}
                  </>
                )}
              </span>
            </span>
          );
        },
      },
      {
        id: "status",
        header: t("runners.columns.status"),
        enableSorting: false,
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
              <Badge key={tag} variant="subtle">
                {tag}
              </Badge>
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

  const rows = useMemo<Row[]>(
    () =>
      runners
        .map((runner) => {
          const st = runnerStatus(runner, now);
          return {
            runner,
            status: st,
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
          };
        })
        .sort((a, b) => ORDER[a.status] - ORDER[b.status]),
    [runners, now, t, slots, busyId, onTogglePause, onRotate, onRevoke],
  );

  const noneOnline = status === "ready" && live.length > 0 && online === 0;
  const waiting = summary?.queued ?? null;
  const oldest = summary?.oldest_queued_age_s ?? null;
  const onlineTone: KpiTone =
    online === 0 ? "danger" : silent > 0 ? "warning" : "success";

  const sortedTokens = [...tokens].sort(
    (a, b) =>
      Number(tokenStatus(a, now) !== "active") -
      Number(tokenStatus(b, now) !== "active"),
  );

  if (status === "forbidden") {
    return (
      <div className="ops-stack" data-testid="runners-view">
        <ViewState status={status} errorText="" testId="runners" />
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

      {status === "ready" && live.length > 0 && (
        <KpiGrid>
          <KpiTile
            testId="runners-stat-online"
            icon={<Server size={14} aria-hidden="true" />}
            label={t("runners.stats.online")}
            value={online}
            unit={t("runners.stats.of", { total: live.length })}
            tone={onlineTone}
            secondary={
              silent === 0 && paused === 0
                ? t("runners.stats.allOnline")
                : [
                    silent > 0
                      ? t("runners.stats.silent", { count: silent })
                      : null,
                    paused > 0
                      ? t("runners.stats.paused", { count: paused })
                      : null,
                  ]
                    .filter(Boolean)
                    .join(", ")
            }
          />
          <KpiTile
            testId="runners-stat-capacity"
            icon={<Cpu size={14} aria-hidden="true" />}
            label={t("runners.stats.capacity")}
            value={used ?? capacity}
            unit={
              used === null
                ? undefined
                : t("runners.stats.of", { total: capacity })
            }
            progress={
              used === null || capacity === 0 ? null : (used / capacity) * 100
            }
            progressTone={
              used !== null && used >= capacity ? "warning" : "neutral"
            }
            secondary={
              capacity === 0
                ? t("runners.stats.noCapacity")
                : used === null
                  ? t("runners.stats.capacityHint")
                  : t("runners.stats.free", {
                      count: Math.max(0, capacity - used),
                    })
            }
          />
          <KpiTile
            testId="runners-stat-waiting"
            icon={<ListOrdered size={14} aria-hidden="true" />}
            label={t("runners.stats.waiting")}
            value={waiting ?? 0}
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
            tone={outdated > 0 ? "warning" : "neutral"}
            secondary={
              outdated > 0
                ? t("runners.stats.outdated", { count: outdated })
                : t("runners.stats.sameVersion")
            }
          />
        </KpiGrid>
      )}

      <ViewState
        status={status}
        errorText={t("runners.loadFailed")}
        onRetry={onRetry}
        testId="runners"
      />
      {status === "ready" && runners.length === 0 && (
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
      )}
      {status === "ready" && runners.length > 0 && (
        <DataTable
          className="ops-table ops-static"
          caption={t("runners.caption")}
          columns={columns}
          data={rows}
          getRowId={(r) => r.runner.id}
        />
      )}

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
        {tokensStatus !== "ready" && (
          <div style={{ padding: "0 20px 16px" }}>
            <ViewState
              status={tokensStatus}
              errorText={t("tokens.loadFailed")}
              onRetry={onRetryTokens}
              testId="tokens"
              compact
              skeleton={<TokensSkeleton />}
            />
          </div>
        )}
        {tokensStatus === "ready" && tokens.length === 0 && (
          <div style={{ padding: "0 20px 16px" }}>
            <EmptyState
              testId="tokens-empty"
              icon={<KeyRound size={18} />}
              title={t("tokens.empty.title")}
              description={t("tokens.empty.body")}
            />
          </div>
        )}
        {tokensStatus === "ready" && tokens.length > 0 && (
          <SectionList label={t("tokens.title")}>
            {sortedTokens.map((token) => {
              const st = tokenStatus(token, now);
              const active = st === "active";
              return (
                <div
                  key={token.id}
                  data-testid={`token-${token.id}`}
                  data-status={st}
                  className={active ? undefined : "ops-dim-row"}
                >
                  <ListRow
                    icon={<KeyRound size={15} />}
                    tone={active ? "accent" : "neutral"}
                    title={
                      token.label === "" ? t("tokens.noLabel") : token.label
                    }
                    description={[
                      t("tokens.uses", {
                        uses: token.uses,
                        max: token.max_uses,
                      }),
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
                        {active && (
                          <Button
                            size="sm"
                            variant="ghost"
                            type="button"
                            data-testid={`token-revoke-${token.id}`}
                            aria-label={t("tokens.revokeLabel", {
                              label:
                                token.label === ""
                                  ? t("tokens.noLabel")
                                  : token.label,
                            })}
                            onClick={() => {
                              onRevokeToken(token);
                            }}
                          >
                            {t("tokens.revoke")}
                          </Button>
                        )}
                      </>
                    }
                  />
                </div>
              );
            })}
          </SectionList>
        )}
      </Section>
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
