import type { ReactNode } from "react";
import { ExternalLink, GitBranch, RefreshCw, Settings, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { gitErrorMessage, type SyncStatusView } from "@entities/git-sync";
import { formatPastTime } from "@shared/lib";
import { Notice } from "@shared/ui/ConflictKit";
import { CopyField } from "@shared/ui/CopyField";
import { Stepper, type StepperStep } from "@shared/ui/Stepper";
import type { SyncUi } from "../model/syncUi.model";
import type { SyncText } from "../model/useSyncText";
import { repoLabel } from "../model/repoLabel";
import { SYNC_TONE_COLOR, SYNC_TONE_SOFT } from "../model/syncTone";
import { sectionTitleStyle } from "../model/commitUi";
import { CommitSection } from "./SyncCommitList";
import { SyncStateIcon } from "./SyncStateIcon";

export type SyncPopoverProps = {
  ui: SyncUi;
  status: SyncStatusView;
  text: SyncText;
  now: number;
  isStarting: boolean;
  isChecking: boolean;
  isCancelling: boolean;
  onSync: () => void;
  onCheck: () => void;
  onCancel: () => void;
  onConnect: () => void;
  onFixAccess: () => void;
  onResolve: () => void;
  onOpenSettings: () => void;
  onOpenHistory: () => void;
  onOpenProfile: () => void;
};

const PHASE_STEPS = ["snapshot", "fetch", "merge", "push"] as const;
const PERCENT_PHASES = new Set(["fetch", "push"]);

/**
 * Панель подробностей синхронизации: репозиторий, что пришло и что не
 * отправлено, ход операции, причина сбоя и действия. Получает готовые данные и
 * обработчики; запросов не делает, поэтому каждое состояние можно показать
 * в тесте и в галерее.
 */
export const SyncPopover = ({
  ui,
  status,
  text,
  now,
  isStarting,
  isChecking,
  isCancelling,
  onSync,
  onCheck,
  onCancel,
  onConnect,
  onFixAccess,
  onResolve,
  onOpenSettings,
  onOpenHistory,
  onOpenProfile,
}: SyncPopoverProps) => {
  const { t } = useTranslation("gitSync");
  const { t: tRemote } = useTranslation("gitRemote");
  const remote = status.remote ?? null;
  const operation = status.operation ?? null;
  const isConnected = status.connected && remote !== null;

  const checkedAt = status.last_fetch_ok_at ?? status.last_fetch_at ?? null;
  const metaParts: string[] = [];
  if (isConnected) {
    metaParts.push(
      checkedAt
        ? t("popover.checked", { when: formatPastTime(checkedAt, now) })
        : t("popover.neverChecked"),
    );
    if (status.last_sync_at && ui.state !== "up_to_date") {
      metaParts.push(
        t("popover.synced", {
          when: formatPastTime(status.last_sync_at, now),
        }),
      );
    }
  }

  const lastError = ((): typeof status.last_error => {
    const error = status.last_error ?? null;
    return error !== null &&
      (ui.state === "error" ||
        ui.state === "auth_failed" ||
        ui.state === "offline" ||
        ui.state === "unknown")
      ? error
      : null;
  })();

  // --- тело ----------------------------------------------------------------------

  const body: ReactNode[] = [];

  if (ui.state === "no_remote") {
    body.push(
      <p
        key="intro"
        style={{
          margin: 0,
          fontSize: 12.5,
          lineHeight: 1.55,
          color: "var(--fg-1)",
        }}
      >
        {t("popover.noRemote.text")}
      </p>,
    );
    if (ui.blockReason === "read_only") {
      body.push(
        <Notice
          key="ro"
          tone="info"
          role="status"
          text={t("blocked.read_only")}
        />,
      );
    }
  }

  if (ui.state === "syncing") {
    const current = ((): string => {
      if (ui.phase === null) return PHASE_STEPS[0];
      if (ui.phase === "queued") return PHASE_STEPS[0];
      return (PHASE_STEPS as readonly string[]).includes(ui.phase)
        ? ui.phase
        : PHASE_STEPS[0];
    })();
    const isQueued = ui.phase === "queued";
    const steps: StepperStep[] = PHASE_STEPS.map((id) => ({
      id,
      label: t(`phase.${id}`),
      ...(isQueued && id === PHASE_STEPS[0]
        ? { description: t("phaseHint.queued") }
        : {}),
      ...(id === current && ui.percent !== null && PERCENT_PHASES.has(id)
        ? { meta: `${String(Math.round(ui.percent))}%` }
        : {}),
    }));
    body.push(
      <div key="steps">
        {ui.operationKind !== null && (
          <div style={{ ...sectionTitleStyle, marginBottom: 8 }}>
            {text.phase}
          </div>
        )}
        <Stepper
          steps={steps}
          current={current}
          busy={!isQueued}
          orientation="vertical"
          label={t("popover.phases")}
        />
      </div>,
    );
  }

  if (ui.state === "conflicts") {
    body.push(
      <Notice
        key="conflicts"
        tone="err"
        role="status"
        text={t("popover.conflicts", {
          open: status.pending?.files_open ?? 0,
          total: status.pending?.files_total ?? 0,
        })}
      />,
      <p
        key="conflicts-hint"
        className="dim"
        style={{ margin: 0, fontSize: 12, lineHeight: 1.5 }}
      >
        {t("stateHint.conflicts")}
      </p>,
    );
  }

  if (ui.state === "blocked") {
    const reason = ui.blockReason ?? "unknown";
    body.push(
      <Notice
        key="blocked"
        tone={reason === "read_only" ? "info" : "warn"}
        role="status"
        text={
          reason === "remote_schema_newer" && ui.requiredStudio
            ? t("popover.schemaNewer", { studio: ui.requiredStudio })
            : t(`blocked.${reason}`, { defaultValue: t("stateHint.blocked") })
        }
      />,
    );
  }

  if (ui.state === "offline" && ui.blockReason === "offline_browser") {
    body.push(
      <Notice
        key="offline-browser"
        tone="warn"
        role="status"
        text={t("popover.offlineBrowser")}
      />,
    );
  }

  if (lastError) {
    body.push(
      <div
        key="error"
        style={{ display: "flex", flexDirection: "column", gap: 8 }}
      >
        <Notice
          tone={ui.state === "offline" ? "warn" : "err"}
          role="alert"
          text={gitErrorMessage(lastError.code, lastError.detail, {})}
        />
        <details className="sync-details">
          <summary>{t("popover.technical")}</summary>
          <div style={{ paddingTop: 8 }}>
            <CopyField
              value={`${lastError.code}: ${lastError.detail}`}
              label={t("popover.technical")}
              multiline
            />
          </div>
        </details>
      </div>,
    );
  } else if (
    ui.state !== "no_remote" &&
    ui.state !== "syncing" &&
    ui.state !== "conflicts" &&
    ui.state !== "blocked" &&
    ui.state !== "unknown"
  ) {
    body.push(
      <p
        key="hint"
        className="dim"
        style={{ margin: 0, fontSize: 12, lineHeight: 1.5 }}
      >
        {t(`stateHint.${ui.state}`)}
      </p>,
    );
  }

  if (isConnected && ui.state !== "syncing" && ui.state !== "conflicts") {
    const moreLabel = (count: number): string => t("popover.more", { count });
    body.push(
      <CommitSection
        key="incoming"
        title={t("popover.incoming")}
        total={status.behind}
        commits={status.incoming}
        now={now}
        moreLabel={moreLabel}
      />,
      <CommitSection
        key="outgoing"
        title={t("popover.outgoing")}
        total={status.ahead}
        commits={status.outgoing}
        now={now}
        moreLabel={moreLabel}
      />,
    );
    if (status.incoming.length > 0 || status.outgoing.length > 0) {
      body.push(
        <button
          key="history"
          type="button"
          className="sync-history-link"
          onClick={onOpenHistory}
        >
          {t("popover.allInHistory")}
        </button>,
      );
    }
  }

  // --- подвал --------------------------------------------------------------------

  const settingsButton = (
    <button
      type="button"
      className="icon-btn"
      onClick={onOpenSettings}
      aria-label={t("popover.settings")}
      title={t("popover.settings")}
    >
      <Settings size={15} aria-hidden="true" />
    </button>
  );

  const syncLabel = isStarting ? t("popover.starting") : t("popover.sync");
  const footer = ((): ReactNode => {
    if (ui.state === "no_remote") {
      return (
        <button
          type="button"
          className="btn primary sm"
          onClick={onConnect}
          disabled={ui.blockReason === "read_only"}
        >
          {t("popover.noRemote.connect")}
        </button>
      );
    }
    if (ui.state === "syncing") {
      return (
        <>
          {operation?.cancellable ? (
            <button
              type="button"
              className="btn sm"
              onClick={onCancel}
              disabled={isCancelling}
            >
              <X size={13} aria-hidden="true" />
              {t("popover.cancel")}
            </button>
          ) : (
            <span className="dim" style={{ fontSize: 11.5 }}>
              {t("popover.notCancellable")}
            </span>
          )}
          <span style={{ flex: 1 }} />
          {settingsButton}
        </>
      );
    }
    const primary = ((): ReactNode => {
      switch (ui.state) {
        case "conflicts":
          return (
            <button
              type="button"
              className="btn primary sm"
              onClick={onResolve}
            >
              {t("popover.resolve")}
            </button>
          );
        case "auth_failed":
          return (
            <button
              type="button"
              className="btn primary sm"
              onClick={onFixAccess}
            >
              {t("popover.fixAccess")}
            </button>
          );
        case "blocked":
          return ui.blockReason === "profile_required" ? (
            <button
              type="button"
              className="btn primary sm"
              onClick={onOpenProfile}
            >
              {t("popover.setProfile")}
            </button>
          ) : null;
        default:
          return (
            <button
              type="button"
              className="btn primary sm"
              onClick={onSync}
              disabled={!ui.canSync || isStarting}
            >
              <RefreshCw
                size={13}
                aria-hidden="true"
                className={isStarting ? "spin" : undefined}
              />
              {ui.state === "error" || ui.state === "offline"
                ? t("popover.retry")
                : syncLabel}
            </button>
          );
      }
    })();
    const canCheckHere = ui.state !== "conflicts" && ui.state !== "auth_failed";
    return (
      <>
        {primary}
        {canCheckHere && status.connected && (
          <button
            type="button"
            className="btn sm"
            onClick={onCheck}
            disabled={!ui.canCheck || isChecking}
          >
            {isChecking ? t("popover.checking") : t("popover.check")}
          </button>
        )}
        {ui.state === "auth_failed" && (
          <button
            type="button"
            className="btn sm"
            onClick={onCheck}
            disabled={!ui.canCheck || isChecking}
          >
            {t("popover.retry")}
          </button>
        )}
        <span style={{ flex: 1 }} />
        {settingsButton}
      </>
    );
  })();

  const toneColor = SYNC_TONE_COLOR[ui.tone];

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <div
        style={{
          display: "flex",
          gap: 11,
          alignItems: "center",
          padding: "13px 14px 11px",
        }}
      >
        <span
          aria-hidden="true"
          style={{
            width: 34,
            height: 34,
            borderRadius: 9,
            flexShrink: 0,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            background: SYNC_TONE_SOFT[ui.tone],
            color: toneColor,
          }}
        >
          <SyncStateIcon icon={ui.icon} size={17} />
        </span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 600,
              letterSpacing: "-0.01em",
              color: "var(--fg-0)",
            }}
          >
            {text.status}
          </div>
          {metaParts.length > 0 && (
            <div className="dim" style={{ fontSize: 11, marginTop: 1 }}>
              {metaParts.join(" · ")}
            </div>
          )}
          {!isConnected && (
            <div className="dim" style={{ fontSize: 11, marginTop: 1 }}>
              {t("popover.noRemote.subtitle")}
            </div>
          )}
        </div>
      </div>

      {isConnected && (
        <div
          className="flex items-center"
          style={{
            gap: 8,
            padding: "7px 14px",
            background: "var(--bg-2)",
            borderTop: "1px solid var(--border)",
            borderBottom: "1px solid var(--border)",
            minWidth: 0,
          }}
        >
          <span className="chip subtle shrink-0">
            {tRemote(`provider.${remote.provider}`, {
              defaultValue: remote.provider,
            })}
          </span>
          <span
            className="mono truncate"
            style={{ fontSize: 11.5, flex: 1, color: "var(--fg-0)" }}
            title={remote.display_url}
          >
            {repoLabel(remote.display_url)}
          </span>
          <span
            className="chip shrink-0"
            title={
              remote.local_branch !== remote.branch
                ? t("popover.branchMapped", {
                    local: remote.local_branch,
                    remote: remote.branch,
                  })
                : t("popover.branch")
            }
          >
            <GitBranch size={10} aria-hidden="true" />
            {remote.branch}
          </span>
          {remote.web_url && (
            <a
              className="icon-btn sm"
              href={remote.web_url}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={t("popover.openInBrowser")}
              title={t("popover.openInBrowser")}
            >
              <ExternalLink size={13} aria-hidden="true" />
            </a>
          )}
        </div>
      )}

      {body.length > 0 && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 12,
            padding: "12px 14px",
            maxHeight: 360,
            overflowY: "auto",
          }}
        >
          {body}
        </div>
      )}

      <div
        className="flex items-center"
        style={{
          gap: 8,
          padding: "10px 14px",
          borderTop: "1px solid var(--border)",
          background: "var(--bg-1)",
          flexWrap: "nowrap",
        }}
      >
        {footer}
      </div>

      {isConnected && ui.state !== "syncing" && (
        <div
          className="dim"
          style={{
            fontSize: 10.5,
            lineHeight: 1.45,
            padding: "0 14px 10px",
            background: "var(--bg-1)",
          }}
        >
          {t("popover.hint")}
        </div>
      )}
    </div>
  );
};
