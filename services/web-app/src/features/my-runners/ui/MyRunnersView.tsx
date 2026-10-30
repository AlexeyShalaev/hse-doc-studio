import { useCallback, useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import {
  ChevronRight,
  Info,
  KeyRound,
  Laptop,
  Pause,
  Pencil,
  Play,
  Plus,
  RotateCw,
  Server,
  Terminal,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatPastTime, formatRelativeTime } from "@shared/lib";
import {
  ActionMenu,
  Badge,
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  ListRow,
  Section,
  SectionList,
  StatusDot,
  TableSkeleton,
  Tooltip,
  type ActionMenuItem,
} from "@shared/ui";
import {
  RUNNER_STATE_DOT,
  isRunnerOutdated,
  type MyRunner,
  type MyRunnerState,
  type MyRunnerToken,
} from "@entities/runner";
import "./myRunners.css";

export type MyRunnersViewProps = {
  status: "loading" | "error" | "ready";
  runners: readonly MyRunner[];
  tokens: readonly MyRunnerToken[];
  /** Личные раннеры разрешены на установке (capabilities.personal_runners). */
  enabled: boolean;
  /** Версия сервера: раннер старше неё помечается «Устарел». */
  serverVersion: string;
  /** Окно ожидания личного раннера, с: в пояснении «Как это работает». */
  waitS?: number;
  now: number;
  /** Раннер, над которым идёт действие. */
  busyId?: string | null;
  /** Показать отозванные сразу (галерея). */
  startShowRevoked?: boolean;
  onRetry?: () => void;
  onConnect: () => void;
  onRename: (runner: MyRunner) => void;
  onTogglePause: (runner: MyRunner) => void;
  onRotate: (runner: MyRunner) => void;
  onReconnect: (runner: MyRunner) => void;
  onRevoke: (runner: MyRunner) => void;
  onRevokeToken: (token: MyRunnerToken) => void;
};

/** Отозванные внизу: они только для истории. */
const ORDER: Record<MyRunnerState, number> = {
  online: 0,
  stale: 1,
  paused: 2,
  offline: 3,
  disabled: 4,
  revoked: 5,
};

const DEFAULT_WAIT_S = 5;
const JUST_NOW_MS = 60_000;

type Row = {
  runner: MyRunner;
  seen: string;
  /** Пояснение под состоянием; null, когда его нет или его уже сказал баннер. */
  hint: string | null;
  /** Что раннер делает сейчас; null, когда это не имеет смысла (выключен админом). */
  load: string | null;
  outdated: boolean;
  busy: boolean;
  actions: ActionMenuItem[];
};

/**
 * Раздел настроек «Мои раннеры»: свои машины, которые собирают свои проекты.
 * Только отображение: данные и действия приходят снаружи (MyRunnersSection).
 */
export const MyRunnersView = ({
  status,
  runners,
  tokens,
  enabled,
  serverVersion,
  waitS = DEFAULT_WAIT_S,
  now,
  busyId = null,
  startShowRevoked = false,
  onRetry,
  onConnect,
  onRename,
  onTogglePause,
  onRotate,
  onReconnect,
  onRevoke,
  onRevokeToken,
}: MyRunnersViewProps) => {
  const { t } = useTranslation("runners");
  const [showRevoked, setShowRevoked] = useState(startShowRevoked);

  const live = runners.filter((r) => !r.revoked);
  const revoked = runners.filter((r) => r.revoked);
  const shown = showRevoked ? runners : live;

  const columns = useMemo<ColumnDef<Row>[]>(
    () => [
      {
        id: "runner",
        header: t("mine.columns.runner"),
        enableSorting: false,
        cell: ({ row }) => {
          const { runner, outdated } = row.original;
          const KindIcon = runner.host_kind === "desktop" ? Laptop : Terminal;
          return (
            <span
              className={runner.revoked ? "myr-cell myr-dim" : "myr-cell"}
              data-testid={`my-runner-row-${runner.id}`}
            >
              <span className="myr-cell-title">{runner.name}</span>
              <span className="myr-cell-sub">
                <KindIcon
                  size={11}
                  aria-hidden="true"
                  style={{ verticalAlign: -1, marginRight: 4 }}
                />
                {t(`mine.kind.${runner.host_kind}`)}
                {" · "}
                {outdated ? (
                  <Tooltip
                    content={t("mine.outdatedHint", { version: serverVersion })}
                  >
                    <span
                      className="myr-outdated"
                      tabIndex={0}
                      data-testid={`my-runner-outdated-${runner.id}`}
                    >
                      <TriangleAlert size={11} aria-hidden="true" />
                      {t("mine.version", { version: runner.version })}{" "}
                      {t("mine.outdated")}
                    </span>
                  </Tooltip>
                ) : (
                  t("mine.version", { version: runner.version })
                )}
              </span>
              {(runner.tags.length > 0 || runner.ai_endpoints.length > 0) && (
                <span className="myr-chips">
                  {runner.tags.map((tag) => (
                    <Badge key={tag} variant="subtle">
                      {tag}
                    </Badge>
                  ))}
                  {runner.ai_endpoints.map((endpoint) => (
                    <Badge
                      key={`ai-${endpoint.name}`}
                      variant="info"
                      title={t("mine.aiEndpoints")}
                    >
                      {endpoint.name}
                    </Badge>
                  ))}
                </span>
              )}
            </span>
          );
        },
      },
      {
        id: "state",
        header: t("mine.columns.state"),
        enableSorting: false,
        cell: ({ row }) => {
          const { runner, seen } = row.original;
          return (
            <span className="myr-cell">
              <span
                data-testid={`my-runner-status-${runner.id}`}
                data-status={runner.state}
                data-paused-by={runner.paused_by ?? undefined}
              >
                <StatusDot
                  status={RUNNER_STATE_DOT[runner.state]}
                  label={t(`mine.state.${runner.state}`)}
                />
              </span>
              {!runner.revoked && (
                <span className="myr-cell-sub" style={{ paddingLeft: 16 }}>
                  {seen}
                  {row.original.hint && (
                    <>
                      <br />
                      {row.original.hint}
                    </>
                  )}
                </span>
              )}
            </span>
          );
        },
      },
      {
        id: "load",
        header: t("mine.columns.load"),
        enableSorting: false,
        cell: ({ row }) => {
          const { runner } = row.original;
          if (runner.revoked) return null;
          return (
            <span className="myr-cell">
              <span
                title={t("mine.slotsTitle", {
                  jobs: runner.concurrency,
                  ai: runner.ai_concurrency,
                })}
              >
                {/* Без слотов ИИ «до 0 ИИ» ничего не говорит: только сборки. */}
                {runner.ai_concurrency > 0
                  ? t("mine.slots", {
                      jobs: t("mine.jobs", { count: runner.concurrency }),
                      ai: runner.ai_concurrency,
                    })
                  : t("mine.slotsJobs", {
                      jobs: t("mine.jobs", { count: runner.concurrency }),
                    })}
              </span>
              {row.original.load && (
                <span className="myr-cell-sub">{row.original.load}</span>
              )}
            </span>
          );
        },
      },
      {
        id: "actions",
        header: () => (
          <span className="sr-only">{t("mine.columns.actions")}</span>
        ),
        enableSorting: false,
        cell: ({ row }) => {
          const { runner, actions } = row.original;
          if (runner.revoked) return null;
          return (
            <ActionMenu
              label={t("mine.actionsLabel", { name: runner.name })}
              testId={`my-runner-actions-${runner.id}`}
              items={actions}
            />
          );
        },
      },
    ],
    [t, serverVersion],
  );
  // У раннера в сети «был в сети сейчас» звучит странно: там только адрес.
  // Меньше минуты назад «был в сети сейчас» неграмотно: «в сети только что».
  const seenText = useCallback(
    (runner: MyRunner): string => {
      if (runner.last_seen_at === null) return t("mine.neverSeen");
      const ip = runner.last_seen_ip;
      if (runner.state === "online") {
        return ip ? t("mine.ipOnly", { ip }) : t("mine.onlineNow");
      }
      if (now - Date.parse(runner.last_seen_at) < JUST_NOW_MS) {
        return ip ? t("mine.seenJustNowIp", { ip }) : t("mine.seenJustNow");
      }
      const ago = formatPastTime(runner.last_seen_at, now);
      return ip ? t("mine.seenIp", { ago, ip }) : t("mine.seen", { ago });
    },
    [t, now],
  );

  const hintText = useCallback(
    (runner: MyRunner): string | null => {
      if (runner.state === "paused" && runner.paused_by === "admin") {
        return t("mine.stateHint.pausedByAdmin");
      }
      // Баннер «Администратор выключил личные раннеры» уже сказал, где идут сборки.
      if (runner.state === "disabled") return null;
      return runner.state === "offline" ||
        runner.state === "paused" ||
        runner.state === "stale"
        ? t(`mine.stateHint.${runner.state}`)
        : null;
    },
    [t],
  );

  const loadText = useCallback(
    (runner: MyRunner): string | null => {
      // Выключенный админом раннер не проходит проверку токена: начатую сборку он не сдаст.
      if (runner.state === "disabled") return null;
      if (runner.running_jobs > 0) {
        return t("mine.running", { count: runner.running_jobs });
      }
      return runner.state === "online" || runner.state === "stale"
        ? t("mine.idle")
        : t("mine.notTaking");
    },
    [t],
  );

  const rows = useMemo<Row[]>(
    () =>
      [...shown]
        .sort((a, b) => ORDER[a.state] - ORDER[b.state])
        .map((runner) => {
          const busy = busyId === runner.id;
          const adminPaused = runner.paused && runner.paused_by === "admin";
          const items: ActionMenuItem[] = [
            {
              id: "rename",
              label: t("mine.rename"),
              icon: <Pencil size={14} aria-hidden="true" />,
              disabled: busy,
              testId: `my-runner-rename-${runner.id}`,
              onSelect: () => {
                onRename(runner);
              },
            },
            {
              id: "pause",
              label: adminPaused
                ? t("mine.resumeAdminOnly")
                : runner.paused
                  ? t("mine.resume")
                  : t("mine.pause"),
              icon: runner.paused ? (
                <Play size={14} aria-hidden="true" />
              ) : (
                <Pause size={14} aria-hidden="true" />
              ),
              // Пауза ничего не меняет, пока личные раннеры выключены админом;
              // паузу администратора хозяин не снимает.
              disabled: busy || !enabled || adminPaused,
              testId: `my-runner-pause-${runner.id}`,
              onSelect: () => {
                onTogglePause(runner);
              },
            },
            runner.host_kind === "desktop"
              ? {
                  id: "reconnect",
                  label: t("mine.reconnect"),
                  icon: <Laptop size={14} aria-hidden="true" />,
                  disabled: busy,
                  testId: `my-runner-reconnect-${runner.id}`,
                  onSelect: () => {
                    onReconnect(runner);
                  },
                }
              : {
                  id: "rotate",
                  label: t("mine.rotate"),
                  icon: <RotateCw size={14} aria-hidden="true" />,
                  disabled: busy,
                  testId: `my-runner-rotate-${runner.id}`,
                  onSelect: () => {
                    onRotate(runner);
                  },
                },
            {
              id: "revoke",
              label: t("mine.revoke"),
              icon: <Trash2 size={14} aria-hidden="true" />,
              danger: true,
              disabled: busy,
              testId: `my-runner-revoke-${runner.id}`,
              onSelect: () => {
                onRevoke(runner);
              },
            },
          ];
          return {
            runner,
            seen: seenText(runner),
            hint: hintText(runner),
            load: loadText(runner),
            outdated: isRunnerOutdated(runner.version, serverVersion),
            busy,
            actions: items,
          };
        }),
    [
      shown,
      busyId,
      t,
      enabled,
      serverVersion,
      onRename,
      onTogglePause,
      onReconnect,
      onRotate,
      onRevoke,
      seenText,
      hintText,
      loadText,
    ],
  );

  const openTokens = tokens.filter((tok) => !tok.used && !tok.revoked);

  return (
    <div className="myr-stack" data-testid="my-runners">
      <div className="myr-head settings-anchor" id="runners">
        <div style={{ minWidth: 0 }}>
          <h4>{t("mine.title")}</h4>
          <p>{t("mine.sub")}</p>
        </div>
        <Button
          type="button"
          size="sm"
          onClick={onConnect}
          disabled={!enabled}
          style={{ gap: 6, flexShrink: 0 }}
          data-testid="my-runner-connect"
        >
          <Plus size={14} aria-hidden="true" />
          {t("mine.connect")}
        </Button>
      </div>

      {!enabled && (
        <div
          className="myr-banner"
          role="status"
          data-testid="my-runners-disabled"
        >
          <TriangleAlert size={16} aria-hidden="true" />
          <div>
            <p className="myr-banner-title">{t("mine.disabled.title")}</p>
            <p className="myr-banner-body">{t("mine.disabled.body")}</p>
          </div>
        </div>
      )}

      {status === "ready" && (
        // Пока раннеров нет, правила раскрыты: человек решает, подключать ли.
        <details
          className="myr-how"
          open={live.length === 0}
          data-testid="my-runners-how"
        >
          <summary>
            <ChevronRight
              size={14}
              className="myr-chevron"
              aria-hidden="true"
            />
            <Info size={14} aria-hidden="true" />
            {t("mine.how.title")}
          </summary>
          <ol>
            <li>{t("mine.how.own")}</li>
            <li>{t("mine.how.coauthors")}</li>
            <li>{t("mine.how.fallback", { seconds: waitS })}</li>
            <li>{t("mine.how.trust")}</li>
          </ol>
        </details>
      )}

      {status === "loading" && (
        <div data-testid="my-runners-loading" aria-label={t("mine.loading")}>
          <TableSkeleton rows={3} columns={3} />
        </div>
      )}
      {status === "error" && (
        <ErrorState
          framed
          description={t("mine.loadFailed")}
          onRetry={onRetry}
          testId="my-runners-error"
        />
      )}

      {status === "ready" && live.length === 0 && (
        <EmptyState
          framed
          testId="my-runners-empty"
          icon={<Server size={18} />}
          title={t("mine.empty.title")}
          description={t("mine.empty.body")}
          action={
            enabled ? (
              <Button
                type="button"
                size="sm"
                onClick={onConnect}
                style={{ gap: 6 }}
                data-testid="my-runners-empty-connect"
              >
                <Plus size={14} aria-hidden="true" />
                {t("mine.connect")}
              </Button>
            ) : undefined
          }
        />
      )}

      {status === "ready" && rows.length > 0 && (
        <DataTable
          className="myr-table"
          caption={t("mine.caption")}
          columns={columns}
          data={rows}
          getRowId={(r) => r.runner.id}
          columnWidths={{ state: "34%", load: 150, actions: 48 }}
        />
      )}

      {status === "ready" && revoked.length > 0 && (
        <div>
          <button
            type="button"
            className="btn xs ghost"
            onClick={() => {
              setShowRevoked((v) => !v);
            }}
            aria-expanded={showRevoked}
            data-testid="my-runners-show-revoked"
          >
            {showRevoked
              ? t("mine.hideRevoked")
              : t("mine.showRevoked", { count: revoked.length })}
          </button>
        </div>
      )}

      {status === "ready" && openTokens.length > 0 && (
        <Section
          title={t("tokens.title")}
          description={t("tokens.lead")}
          flush
          testId="my-runner-tokens"
        >
          <SectionList label={t("tokens.title")}>
            {openTokens.map((token) => {
              const label =
                token.label === "" ? t("tokens.noLabel") : token.label;
              const expired = Date.parse(token.expires_at) <= now;
              return (
                <div key={token.id} data-testid={`my-runner-token-${token.id}`}>
                  <ListRow
                    icon={<KeyRound size={15} />}
                    tone={expired ? "neutral" : "accent"}
                    title={label}
                    description={
                      expired
                        ? t("tokens.expired", {
                            when: formatPastTime(token.expires_at, now),
                          })
                        : t("tokens.expires", {
                            when: formatRelativeTime(token.expires_at, now),
                          })
                    }
                    meta={
                      <ActionMenu
                        label={t("tokens.actionsLabel", { label })}
                        testId={`my-runner-token-actions-${token.id}`}
                        items={[
                          {
                            id: "revoke",
                            label: t("tokens.revoke"),
                            icon: <Trash2 size={14} aria-hidden="true" />,
                            danger: true,
                            testId: `my-runner-token-revoke-${token.id}`,
                            onSelect: () => {
                              onRevokeToken(token);
                            },
                          },
                        ]}
                      />
                    }
                  />
                </div>
              );
            })}
          </SectionList>
        </Section>
      )}
    </div>
  );
};
