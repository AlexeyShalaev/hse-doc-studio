import { useCallback, useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import {
  KeyRound,
  Pause,
  Play,
  Plus,
  RotateCw,
  Server,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge, Button, DataTable, StatusDot } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { AdminRunner, AdminRunnerToken } from "@entities/session";
import { formatDuration } from "../lib/format";
import {
  countOnline,
  runnerStatus,
  secondsSince,
  type RunnerStatus,
} from "../lib/runnerStatus";
import { tokenStatus, type TokenStatus } from "../lib/tokenStatus";
import { useDurationUnits } from "../lib/useDurationUnits";
import {
  Card,
  EmptyBlock,
  LoadFailed,
  LoadingRow,
  PageHeader,
  Stat,
  StatRow,
} from "./parts";

export type RunnersViewProps = {
  status: "loading" | "error" | "ready";
  runners: readonly AdminRunner[];
  tokensStatus: "loading" | "error" | "ready";
  tokens: readonly AdminRunnerToken[];
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
};

/** Строка таблицы: всё меняющееся лежит в данных, а не в замыканиях колонок (иначе ячейки пересоздаются). */
type Row = {
  runner: AdminRunner;
  status: RunnerStatus;
  seen: string;
  busy: boolean;
  pause: () => void;
  rotate: () => void;
  revoke: () => void;
};

const DOT: Record<RunnerStatus, "online" | "stale" | "offline" | "paused"> = {
  online: "online",
  stale: "stale",
  offline: "offline",
  paused: "paused",
  revoked: "offline",
};

const TOKEN_VARIANT: Record<
  TokenStatus,
  "success" | "subtle" | "warning" | "error"
> = {
  active: "success",
  exhausted: "subtle",
  expired: "warning",
  revoked: "subtle",
};

/** Давность последнего сигнала: «12 с назад», «не подключался». */
const useSeen = () => {
  const { t } = useTranslation("adminOps");
  const units = useDurationUnits();
  return useCallback(
    (iso: string | null, now: number): string => {
      const age = secondsSince(iso, now);
      return age === null
        ? t("runners.neverSeen")
        : t("runners.seenAgo", { ago: formatDuration(age, units) });
    },
    [t, units],
  );
};

/** Раннеры установки и токены регистрации. */
export const RunnersView = ({
  status,
  runners,
  tokensStatus,
  tokens,
  now,
  busyId = null,
  onRetry,
  onRetryTokens,
  onTogglePause,
  onRotate,
  onRevoke,
  onCreateToken,
  onRevokeToken,
}: RunnersViewProps) => {
  const { t } = useTranslation("adminOps");
  const seen = useSeen();

  const online = countOnline(runners, now);
  const live = runners.filter((r) => !r.revoked);

  const columns = useMemo<ColumnDef<Row>[]>(
    () => [
      {
        id: "name",
        header: t("runners.columns.name"),
        enableSorting: false,
        cell: ({ row }) => (
          <span className="flex flex-col" style={{ gap: 1, minWidth: 0 }}>
            <span style={{ fontWeight: 600, fontSize: 13 }}>
              {row.original.runner.name}
            </span>
            <span
              className="mono"
              style={{ fontSize: 11, color: "var(--fg-2)" }}
            >
              v{row.original.runner.version} ·{" "}
              {row.original.runner.resource_class}
            </span>
          </span>
        ),
      },
      {
        id: "status",
        header: t("runners.columns.status"),
        enableSorting: false,
        cell: ({ row }) => {
          const { runner, status: st, seen } = row.original;
          return (
            <span className="flex flex-col" style={{ gap: 2 }}>
              <span data-testid={`runner-status-${runner.id}`} data-status={st}>
                <StatusDot status={DOT[st]} label={t(`runners.status.${st}`)} />
              </span>
              {st !== "revoked" && (
                <span style={{ fontSize: 11, color: "var(--fg-2)" }}>
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
          <span className="flex" style={{ gap: 4, flexWrap: "wrap" }}>
            {row.original.runner.tags.map((tag) => (
              <Badge key={tag} variant="subtle">
                {tag}
              </Badge>
            ))}
          </span>
        ),
      },
      {
        id: "concurrency",
        header: t("runners.columns.concurrency"),
        enableSorting: false,
        cell: ({ row }) =>
          t("runners.slots", { count: row.original.runner.concurrency }),
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
            <span
              className="flex items-center"
              style={{ gap: 4, justifyContent: "flex-end" }}
            >
              <Button
                size="sm"
                variant="ghost"
                type="button"
                disabled={busy}
                style={{ gap: 5 }}
                data-testid={`runner-pause-${r.id}`}
                onClick={(event) => {
                  event.stopPropagation();
                  pause();
                }}
              >
                {r.paused ? (
                  <Play size={13} aria-hidden="true" />
                ) : (
                  <Pause size={13} aria-hidden="true" />
                )}
                {r.paused ? t("runners.resume") : t("runners.pause")}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                type="button"
                disabled={busy}
                style={{ gap: 5 }}
                data-testid={`runner-rotate-${r.id}`}
                onClick={(event) => {
                  event.stopPropagation();
                  rotate();
                }}
              >
                <RotateCw size={13} aria-hidden="true" />
                {t("runners.rotate")}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                type="button"
                disabled={busy}
                aria-label={t("runners.revokeLabel", { name: r.name })}
                data-testid={`runner-revoke-${r.id}`}
                onClick={(event) => {
                  event.stopPropagation();
                  revoke();
                }}
              >
                <Trash2 size={13} aria-hidden="true" />
              </Button>
            </span>
          );
        },
      },
    ],
    [t],
  );

  const rows = useMemo<Row[]>(
    () =>
      runners.map((runner) => ({
        runner,
        status: runnerStatus(runner, now),
        seen: seen(runner.last_seen_at, now),
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
      })),
    [runners, now, seen, busyId, onTogglePause, onRotate, onRevoke],
  );

  const createButton = (
    <Button
      size="sm"
      type="button"
      onClick={onCreateToken}
      style={{ gap: 6 }}
      data-testid="runner-token-create"
    >
      <Plus size={14} aria-hidden="true" />
      {t("tokens.create")}
    </Button>
  );

  const noneOnline = status === "ready" && live.length > 0 && online === 0;

  return (
    <div
      className="flex flex-col"
      style={{ gap: 16 }}
      data-testid="runners-view"
    >
      <PageHeader
        title={t("runners.title")}
        lead={t("runners.lead")}
        action={createButton}
      />
      {status === "ready" && live.length > 0 && (
        <StatRow>
          <Stat
            label={t("runners.stats.online")}
            value={`${String(online)} / ${String(live.length)}`}
            tone={online === 0 ? "err" : undefined}
            testId="runners-stat-online"
          />
          <Stat
            label={t("runners.stats.paused")}
            value={String(live.filter((r) => r.paused).length)}
          />
          <Stat
            label={t("runners.stats.capacity")}
            value={String(
              live
                .filter((r) => runnerStatus(r, now) === "online")
                .reduce((sum, r) => sum + r.concurrency, 0),
            )}
            hint={t("runners.stats.capacityHint")}
          />
        </StatRow>
      )}
      {noneOnline && (
        <div data-testid="runners-none-online">
          <Notice tone="err" role="alert" text={t("runners.noneOnline")} />
        </div>
      )}
      {status === "loading" && <LoadingRow testId="runners-loading" />}
      {status === "error" && (
        <LoadFailed text={t("runners.loadFailed")} onRetry={onRetry} />
      )}
      {status === "ready" && runners.length === 0 && (
        <EmptyBlock
          testId="runners-empty"
          icon={<Server size={18} aria-hidden="true" />}
          title={t("runners.empty.title")}
          body={t("runners.empty.body")}
          action={
            <Button size="sm" type="button" onClick={onCreateToken}>
              {t("tokens.create")}
            </Button>
          }
        />
      )}
      {status === "ready" && runners.length > 0 && (
        <DataTable
          caption={t("runners.caption")}
          columns={columns}
          data={rows}
          getRowId={(r) => r.runner.id}
        />
      )}

      <Card
        title={t("tokens.title")}
        lead={t("tokens.lead")}
        testId="runner-tokens"
      >
        {tokensStatus === "loading" && <LoadingRow testId="tokens-loading" />}
        {tokensStatus === "error" && (
          <LoadFailed text={t("tokens.loadFailed")} onRetry={onRetryTokens} />
        )}
        {tokensStatus === "ready" && tokens.length === 0 && (
          <EmptyBlock
            testId="tokens-empty"
            icon={<KeyRound size={18} aria-hidden="true" />}
            title={t("tokens.empty.title")}
            body={t("tokens.empty.body")}
          />
        )}
        {tokensStatus === "ready" && tokens.length > 0 && (
          <ul
            style={{
              listStyle: "none",
              margin: 0,
              padding: 0,
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            {tokens.map((token) => {
              const st = tokenStatus(token, now);
              return (
                <li
                  key={token.id}
                  className="flex items-center"
                  style={{
                    gap: 10,
                    padding: "8px 10px",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--r-2)",
                  }}
                  data-testid={`token-${token.id}`}
                  data-status={st}
                >
                  <span
                    className="flex flex-col"
                    style={{ flex: 1, minWidth: 0 }}
                  >
                    <span style={{ fontWeight: 600, fontSize: 13 }}>
                      {token.label === "" ? t("tokens.noLabel") : token.label}
                    </span>
                    <span style={{ fontSize: 11.5, color: "var(--fg-2)" }}>
                      {t("tokens.uses", {
                        uses: token.uses,
                        max: token.max_uses,
                      })}
                    </span>
                  </span>
                  <Badge variant={TOKEN_VARIANT[st]}>
                    {t(`tokens.status.${st}`)}
                  </Badge>
                  {st === "active" && (
                    <Button
                      size="sm"
                      variant="ghost"
                      type="button"
                      data-testid={`token-revoke-${token.id}`}
                      onClick={() => {
                        onRevokeToken(token);
                      }}
                    >
                      {t("tokens.revoke")}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
};
