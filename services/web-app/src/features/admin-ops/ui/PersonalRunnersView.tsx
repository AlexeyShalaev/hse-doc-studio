import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import {
  ArrowRight,
  Laptop,
  Pause,
  Play,
  Terminal,
  Trash2,
  Users,
} from "lucide-react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { formatPastTime } from "@shared/lib";
import {
  ActionMenu,
  Badge,
  DataTable,
  EmptyState,
  FilterBar,
  KpiGrid,
  KpiTile,
  PersonCell,
  Section,
  StatusDot,
  type StatusDotStatus,
} from "@shared/ui";
import type { AdminRunner } from "@entities/session";
import { personalStatus, type PersonalStatus } from "../lib/personalStatus";
import type { ViewStatus } from "../lib/viewStatus";
import { Banner, ViewState } from "./parts";

const DOT: Record<PersonalStatus, StatusDotStatus> = {
  online: "online",
  stale: "stale",
  offline: "offline",
  paused: "paused",
  revoked: "neutral",
  disabled: "neutral",
};

const ORDER: Record<PersonalStatus, number> = {
  online: 0,
  stale: 1,
  paused: 2,
  offline: 3,
  disabled: 4,
  revoked: 5,
};

const STATES: readonly PersonalStatus[] = [
  "online",
  "stale",
  "paused",
  "offline",
  "disabled",
  "revoked",
];

export type PersonalRunnersViewProps = {
  status: ViewStatus;
  runners: readonly AdminRunner[];
  /** Личные раннеры разрешены на установке; undefined: сервер не сказал. */
  enabled?: boolean | undefined;
  now: number;
  busyId?: string | null;
  onRetry?: () => void;
  onTogglePause: (runner: AdminRunner) => void;
  onRevoke: (runner: AdminRunner) => void;
};

type Row = {
  runner: AdminRunner;
  status: PersonalStatus;
  seen: string;
  busy: boolean;
  owner: string;
  pause: () => void;
  revoke: () => void;
};

/**
 * Раздел «Личные раннеры» в админке: чьи машины подключены, в каком они
 * состоянии; пауза и отзыв. Смены токена здесь нет: она дала бы админу доступ
 * к проектам человека.
 */
export const PersonalRunnersView = ({
  status,
  runners,
  enabled,
  now,
  busyId = null,
  onRetry,
  onTogglePause,
  onRevoke,
}: PersonalRunnersViewProps) => {
  const { t } = useTranslation("adminOps");
  const [q, setQ] = useState("");
  const [state, setState] = useState("");

  const live = runners.filter((r) => !r.revoked);
  const online = live.filter((r) => personalStatus(r, now) === "online").length;
  const owners = new Set(live.map((r) => r.owner?.id ?? "")).size;
  const paused = live.filter((r) => personalStatus(r, now) === "paused").length;

  const columns = useMemo<ColumnDef<Row>[]>(
    () => [
      {
        id: "owner",
        header: t("personal.columns.owner"),
        enableSorting: false,
        cell: ({ row }) => {
          const { runner } = row.original;
          return (
            <PersonCell
              id={runner.owner?.id}
              name={runner.owner?.name}
              email={runner.owner?.email}
              fallback={t("personal.unknownOwner")}
              testId={`admin-runner-owner-${runner.id}`}
            />
          );
        },
      },
      {
        id: "runner",
        header: t("personal.columns.runner"),
        enableSorting: false,
        cell: ({ row }) => {
          const { runner, status: st } = row.original;
          const KindIcon = runner.host_kind === "desktop" ? Laptop : Terminal;
          return (
            <span
              className={st === "revoked" ? "ops-cell ops-dim-row" : "ops-cell"}
            >
              <span className="ops-cell-title">{runner.name}</span>
              <span className="ops-cell-sub">
                <KindIcon
                  size={11}
                  aria-hidden="true"
                  style={{ verticalAlign: -1, marginRight: 4 }}
                />
                {t(`personal.kind.${runner.host_kind ?? "cli"}`)}
                {" · v"}
                {runner.version}
              </span>
            </span>
          );
        },
      },
      {
        id: "state",
        header: t("personal.columns.state"),
        enableSorting: false,
        cell: ({ row }) => {
          const { runner, status: st, seen } = row.original;
          return (
            <span className="ops-cell">
              <span
                data-testid={`admin-personal-runner-status-${runner.id}`}
                data-status={st}
              >
                <StatusDot
                  status={DOT[st]}
                  label={t(`personal.status.${st}`)}
                />
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
        id: "ai",
        header: t("personal.columns.ai"),
        enableSorting: false,
        cell: ({ row }) => {
          const endpoints = row.original.runner.ai_endpoints ?? [];
          return endpoints.length === 0 ? (
            <span className="ops-muted">{t("personal.noAi")}</span>
          ) : (
            <span className="ops-tags">
              {endpoints.map((name) => (
                <Badge key={name} variant="info">
                  {name}
                </Badge>
              ))}
            </span>
          );
        },
      },
      {
        id: "actions",
        header: () => (
          <span className="sr-only">{t("personal.columns.actions")}</span>
        ),
        enableSorting: false,
        cell: ({ row }) => {
          const { runner: r, busy, pause, revoke, owner } = row.original;
          if (r.revoked) return null;
          return (
            <span className="ops-row-actions">
              <ActionMenu
                label={t("personal.actionsLabel", { name: r.name, owner })}
                testId={`admin-personal-runner-actions-${r.id}`}
                items={[
                  {
                    id: "pause",
                    label: r.paused
                      ? t("personal.resume")
                      : t("personal.pause"),
                    icon: r.paused ? (
                      <Play size={14} aria-hidden="true" />
                    ) : (
                      <Pause size={14} aria-hidden="true" />
                    ),
                    disabled: busy,
                    onSelect: pause,
                    testId: `admin-personal-runner-pause-${r.id}`,
                  },
                  {
                    id: "revoke",
                    label: t("personal.revoke"),
                    icon: <Trash2 size={14} aria-hidden="true" />,
                    danger: true,
                    disabled: busy,
                    onSelect: revoke,
                    testId: `admin-personal-runner-revoke-${r.id}`,
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

  const needle = q.trim().toLowerCase();
  const rows = useMemo<Row[]>(
    () =>
      runners
        .map((runner) => {
          const st = personalStatus(runner, now);
          const ago =
            runner.last_seen_at === null
              ? t("runners.neverSeen")
              : formatPastTime(runner.last_seen_at, now);
          const owner = runner.owner?.name ?? t("personal.unknownOwner");
          return {
            runner,
            status: st,
            owner,
            seen: runner.last_seen_ip
              ? t("personal.seenIp", { ago, ip: runner.last_seen_ip })
              : ago,
            busy: busyId === runner.id,
            pause: () => {
              onTogglePause(runner);
            },
            revoke: () => {
              onRevoke(runner);
            },
          };
        })
        .filter((row) => state === "" || row.status === state)
        .filter(
          (row) =>
            needle === "" ||
            [row.runner.name, row.owner, row.runner.owner?.email ?? ""]
              .join(" ")
              .toLowerCase()
              .includes(needle),
        )
        .sort((a, b) => ORDER[a.status] - ORDER[b.status]),
    [runners, now, t, busyId, onTogglePause, onRevoke, state, needle],
  );

  return (
    <Section
      title={t("personal.title")}
      description={t("personal.lead")}
      flush
      testId="admin-personal-runners"
    >
      <div className="ops-stack" style={{ padding: "0 20px 20px" }}>
        {enabled === false && (
          <Banner
            tone="warning"
            title={t("personal.disabled.title")}
            testId="admin-personal-runners-disabled"
            action={
              <Link
                to="/admin/instance"
                className="btn sm"
                style={{ gap: 6, textDecoration: "none" }}
              >
                {t("personal.disabled.action")}
                <ArrowRight size={13} aria-hidden="true" />
              </Link>
            }
          >
            {t("personal.disabled.body")}
          </Banner>
        )}
        <ViewState
          status={status}
          errorText={t("runners.loadFailed")}
          onRetry={onRetry}
          testId="admin-personal-runners"
          compact
        />
        {status === "ready" && runners.length === 0 && (
          <EmptyState
            testId="admin-personal-runners-empty"
            icon={<Users size={18} />}
            title={t("personal.empty.title")}
            description={t("personal.empty.body")}
          />
        )}
        {status === "ready" && runners.length > 0 && (
          <>
            <KpiGrid>
              <KpiTile
                testId="admin-personal-runners-online"
                icon={<Laptop size={14} aria-hidden="true" />}
                label={t("personal.online")}
                value={online}
                unit={t("personal.onlineOf", { total: live.length })}
                tone={
                  enabled === false
                    ? "neutral"
                    : online > 0
                      ? "success"
                      : "neutral"
                }
                secondary={t("personal.onlineHint")}
              />
              <KpiTile
                testId="admin-personal-runners-owners"
                icon={<Users size={14} aria-hidden="true" />}
                label={t("personal.ownersLabel")}
                value={owners}
                secondary={t("personal.ownersHint")}
              />
              <KpiTile
                testId="admin-personal-runners-paused"
                icon={<Pause size={14} aria-hidden="true" />}
                label={t("personal.pausedLabel")}
                value={paused}
                secondary={t("personal.pausedHint")}
              />
            </KpiGrid>
            <FilterBar
              search={q}
              onSearchChange={setQ}
              searchLabel={t("personal.search")}
              searchPlaceholder={t("personal.searchPlaceholder")}
              filters={[
                {
                  id: "state",
                  label: t("personal.filterState"),
                  value: state,
                  onChange: setState,
                  options: STATES.map((s) => ({
                    value: s,
                    label: t(`personal.status.${s}`),
                  })),
                },
              ]}
              onReset={() => {
                setQ("");
                setState("");
              }}
            />
            {rows.length === 0 ? (
              <EmptyState compact title={t("personal.noMatch")} />
            ) : (
              <DataTable
                className="ops-table ops-static"
                caption={t("personal.caption")}
                columns={columns}
                data={rows}
                getRowId={(r) => r.runner.id}
              />
            )}
          </>
        )}
      </div>
    </Section>
  );
};
