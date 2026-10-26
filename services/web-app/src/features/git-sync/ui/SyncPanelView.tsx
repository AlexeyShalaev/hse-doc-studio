import type { ReactNode } from "react";
import {
  ArrowDown,
  ArrowUp,
  CloudOff,
  ExternalLink,
  FileArchive,
  GitBranch,
  RefreshCw,
  Settings,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { gitErrorMessage, type SyncStatusView } from "@entities/git-sync";
import { formatRelativeTime } from "@shared/lib";
import { Notice } from "@shared/ui/ConflictKit";
import { CopyField } from "@shared/ui/CopyField";
import { Stepper, type StepperStep } from "@shared/ui/Stepper";
import type { SyncUi } from "../model/syncUi.model";
import type { SyncText } from "../model/useSyncText";
import { repoLabel } from "../model/repoLabel";
import { SYNC_TONE_COLOR, SYNC_TONE_SOFT } from "../model/syncTone";
import { CommitSection } from "./SyncCommitList";
import { SyncStateIcon } from "./SyncStateIcon";

export type SyncHistoryMode = "incoming" | "unpushed";

export type SyncPanelViewProps = {
  ui: SyncUi;
  status: SyncStatusView;
  text: SyncText;
  now: number;
  isStarting: boolean;
  isChecking: boolean;
  isCancelling: boolean;
  isAcknowledging?: boolean;
  onSync: () => void;
  onCheck: () => void;
  onCancel: () => void;
  onConnect: () => void;
  /** Нет обработчика: кнопка обмена файлом не показывается. */
  onBundle?: () => void;
  onFixAccess: () => void;
  onResolve: () => void;
  onOpenSettings: () => void;
  onOpenProfile: () => void;
  onAcknowledgeSharedFolder: () => void;
  /** Показать версии в ленте истории ниже: пришедшие или не отправленные. */
  onShowInHistory: (mode: SyncHistoryMode) => void;
  /** Выбранная пришедшая версия: под списком показывается её содержимое. */
  selectedIncomingId: string | null;
  onSelectIncoming: (commitId: string | null) => void;
  incomingDetails?: ReactNode;
};

const PHASE_STEPS = ["snapshot", "fetch", "merge", "push"] as const;
const PERCENT_PHASES = new Set(["fetch", "push"]);

const Stat = ({
  label,
  value,
  sub,
  icon,
  tone,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon?: ReactNode;
  tone?: string;
}) => (
  <div className="sync-stat">
    <span className="dim" style={{ fontSize: 10.5, letterSpacing: "0.04em" }}>
      {label}
    </span>
    <span
      className="flex items-center tnum"
      style={{
        gap: 5,
        fontSize: 18,
        fontWeight: 600,
        lineHeight: 1.2,
        color: tone ?? "var(--fg-0)",
      }}
    >
      {icon}
      {value}
    </span>
    {sub !== undefined && (
      <span className="dim" style={{ fontSize: 11 }}>
        {sub}
      </span>
    )}
  </div>
);

/**
 * Синхронизация в большом виде, на странице истории: что подключено, что пришло и
 * что не отправлено, ход операции, причины сбоя и все действия. Получает готовые
 * данные и обработчики, запросов не делает: каждое состояние можно показать в
 * тесте и в галерее.
 */
export const SyncPanelView = ({
  ui,
  status,
  text,
  now,
  isStarting,
  isChecking,
  isCancelling,
  isAcknowledging = false,
  onSync,
  onCheck,
  onCancel,
  onConnect,
  onBundle,
  onFixAccess,
  onResolve,
  onOpenSettings,
  onOpenProfile,
  onAcknowledgeSharedFolder,
  onShowInHistory,
  selectedIncomingId,
  onSelectIncoming,
  incomingDetails,
}: SyncPanelViewProps) => {
  const { t } = useTranslation("gitSync");
  const { t: tRemote } = useTranslation("gitRemote");
  const { t: tAccess } = useTranslation("gitAccess");
  const remote = status.remote ?? null;
  const operation = status.operation ?? null;
  const isConnected = status.connected && remote !== null;

  // --- репозиторий не подключён ----------------------------------------------------

  if (!isConnected) {
    const readOnly = ui.blockReason === "read_only";
    return (
      <div
        className="flex flex-col items-center"
        data-testid="sync-panel-empty"
        style={{ gap: 12, padding: "10px 0 4px", textAlign: "center" }}
      >
        <span
          aria-hidden="true"
          style={{
            width: 52,
            height: 52,
            borderRadius: 14,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--bg-3)",
            color: "var(--fg-2)",
          }}
        >
          <CloudOff size={24} />
        </span>
        <div className="flex flex-col" style={{ gap: 4, maxWidth: 520 }}>
          <h4
            style={{
              margin: 0,
              fontSize: 14,
              fontWeight: 600,
              color: "var(--fg-0)",
            }}
          >
            {t("panel.empty.title")}
          </h4>
          <p
            className="dim"
            style={{ margin: 0, fontSize: 12.5, lineHeight: 1.6 }}
          >
            {t("panel.empty.text")}
          </p>
        </div>
        <div
          className="flex items-center justify-center"
          style={{ gap: 8, flexWrap: "wrap" }}
        >
          <button
            type="button"
            className="btn primary"
            onClick={onConnect}
            disabled={readOnly}
          >
            {t("popover.noRemote.connect")}
          </button>
          {onBundle && (
            <button type="button" className="btn" onClick={onBundle}>
              <FileArchive size={13} aria-hidden="true" />
              {t("panel.empty.bundle")}
            </button>
          )}
        </div>
        {onBundle && (
          <p
            className="dim"
            style={{ margin: 0, fontSize: 11.5, maxWidth: 480 }}
          >
            {t("panel.empty.bundleHint")}
          </p>
        )}
        {readOnly && (
          <div style={{ alignSelf: "stretch", textAlign: "left" }}>
            <Notice tone="info" role="status" text={t("blocked.read_only")} />
          </div>
        )}
        {!status.profile_ok && (
          <div style={{ alignSelf: "stretch", textAlign: "left" }}>
            <Notice
              tone="warn"
              role="status"
              text={t("panel.profileRequired")}
              action={
                <button
                  type="button"
                  className="btn xs"
                  onClick={onOpenProfile}
                >
                  {t("popover.setProfile")}
                </button>
              }
            />
          </div>
        )}
      </div>
    );
  }

  // --- подключён -------------------------------------------------------------------

  const checkedAt = status.last_fetch_ok_at ?? status.last_fetch_at ?? null;
  const toneColor = SYNC_TONE_COLOR[ui.tone];
  const lastError =
    status.last_error &&
    (ui.state === "error" ||
      ui.state === "auth_failed" ||
      ui.state === "offline" ||
      ui.state === "unknown")
      ? status.last_error
      : null;
  const sharedFolder =
    status.shared_folder && !status.shared_folder.acknowledged
      ? status.shared_folder
      : null;

  const headerMeta: string[] = [
    checkedAt
      ? t("popover.checked", { when: formatRelativeTime(checkedAt, now) })
      : t("popover.neverChecked"),
  ];
  if (status.last_sync_at && ui.state !== "up_to_date") {
    headerMeta.push(
      t("popover.synced", {
        when: formatRelativeTime(status.last_sync_at, now),
      }),
    );
  }

  const syncLabel = isStarting ? t("popover.starting") : t("popover.sync");
  const primary = ((): ReactNode => {
    switch (ui.state) {
      case "syncing":
        return operation?.cancellable ? (
          <button
            type="button"
            className="btn"
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
        );
      case "conflicts":
        return (
          <button type="button" className="btn primary" onClick={onResolve}>
            {t("popover.resolve")}
          </button>
        );
      case "auth_failed":
        return (
          <button type="button" className="btn primary" onClick={onFixAccess}>
            {t("popover.fixAccess")}
          </button>
        );
      case "blocked":
        return ui.blockReason === "profile_required" ? (
          <button type="button" className="btn primary" onClick={onOpenProfile}>
            {t("popover.setProfile")}
          </button>
        ) : null;
      default:
        return (
          <button
            type="button"
            className="btn primary"
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
  const showCheck =
    ui.state !== "conflicts" &&
    ui.state !== "syncing" &&
    ui.state !== "unknown";

  // --- этапы операции --------------------------------------------------------------

  const stepper = ((): ReactNode => {
    if (ui.state !== "syncing") return null;
    const isQueued = ui.phase === "queued";
    const current =
      ui.phase !== null && (PHASE_STEPS as readonly string[]).includes(ui.phase)
        ? ui.phase
        : PHASE_STEPS[0];
    // В горизонтальном ряду нет места для подписи и числа: процент дописывается
    // к названию текущего этапа, а пояснение про очередь идёт строкой ниже.
    const steps: StepperStep[] = PHASE_STEPS.map((id) => ({
      id,
      label:
        id === current && ui.percent !== null && PERCENT_PHASES.has(id)
          ? `${t(`phase.${id}`)} ${String(Math.round(ui.percent))}%`
          : t(`phase.${id}`),
    }));
    return (
      <div className="flex flex-col" style={{ gap: 6 }}>
        <Stepper
          steps={steps}
          current={current}
          busy={!isQueued}
          orientation="horizontal"
          label={t("popover.phases")}
        />
        {isQueued && (
          <span className="dim" style={{ fontSize: 11.5 }}>
            {t("phaseHint.queued")}
          </span>
        )}
      </div>
    );
  })();

  // --- предупреждения --------------------------------------------------------------

  const notices: ReactNode[] = [];
  if (ui.state === "conflicts") {
    notices.push(
      <Notice
        key="conflicts"
        tone="err"
        role="status"
        text={`${t("popover.conflicts", {
          open: status.pending?.files_open ?? 0,
          total: status.pending?.files_total ?? 0,
        })}. ${t("stateHint.conflicts")}`}
      />,
    );
  }
  if (ui.state === "blocked") {
    const reason = ui.blockReason ?? "unknown";
    notices.push(
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
    notices.push(
      <Notice
        key="offline-browser"
        tone="warn"
        role="status"
        text={t("popover.offlineBrowser")}
      />,
    );
  }
  if (lastError) {
    notices.push(
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
  }
  if (sharedFolder) {
    notices.push(
      <Notice
        key="shared-folder"
        tone="warn"
        role="status"
        text={t("panel.sharedFolder", {
          provider: tAccess(`sharedProvider.${sharedFolder.provider}`, {
            defaultValue: sharedFolder.provider,
          }),
        })}
        action={
          <button
            type="button"
            className="btn xs"
            onClick={onAcknowledgeSharedFolder}
            disabled={isAcknowledging}
          >
            {t("panel.sharedFolderAck")}
          </button>
        }
      />,
    );
  }
  if (!status.profile_ok && ui.blockReason !== "profile_required") {
    notices.push(
      <Notice
        key="profile"
        tone="warn"
        role="status"
        text={t("panel.profileRequired")}
        action={
          <button type="button" className="btn xs" onClick={onOpenProfile}>
            {t("popover.setProfile")}
          </button>
        }
      />,
    );
  }

  // --- версии ----------------------------------------------------------------------

  const moreLabel = (count: number): string => t("popover.more", { count });
  const showLists = ui.state !== "syncing" && ui.state !== "conflicts";
  const hasIncoming = showLists && status.incoming.length > 0;
  const hasOutgoing = showLists && status.outgoing.length > 0;

  const linkButton = (mode: SyncHistoryMode, label: string): ReactNode => (
    <button
      type="button"
      className="sync-history-link"
      style={{ marginTop: 4 }}
      onClick={() => {
        onShowInHistory(mode);
      }}
    >
      {label}
    </button>
  );

  return (
    <div className="flex flex-col" style={{ gap: 14 }} data-testid="sync-panel">
      {/* состояние и действия */}
      <div className="flex items-center" style={{ gap: 12, flexWrap: "wrap" }}>
        <span
          aria-hidden="true"
          style={{
            width: 38,
            height: 38,
            borderRadius: 10,
            flexShrink: 0,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            background: SYNC_TONE_SOFT[ui.tone],
            color: toneColor,
          }}
        >
          <SyncStateIcon icon={ui.icon} size={19} />
        </span>
        <div style={{ minWidth: 0, flex: "1 1 220px" }}>
          <div
            style={{
              fontSize: 14,
              fontWeight: 600,
              letterSpacing: "-0.01em",
              color: "var(--fg-0)",
            }}
            role="status"
          >
            {text.status}
          </div>
          <div className="dim" style={{ fontSize: 11.5, marginTop: 1 }}>
            {headerMeta.join(" · ")}
          </div>
        </div>
        <div className="flex items-center" style={{ gap: 8, flexWrap: "wrap" }}>
          {primary}
          {showCheck && (
            <button
              type="button"
              className="btn"
              onClick={onCheck}
              disabled={!ui.canCheck || isChecking}
            >
              {isChecking ? t("popover.checking") : t("popover.check")}
            </button>
          )}
          <button
            type="button"
            className="icon-btn"
            onClick={onOpenSettings}
            aria-label={t("popover.settings")}
            title={t("popover.settings")}
          >
            <Settings size={15} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* репозиторий */}
      <div
        className="flex items-center"
        style={{
          gap: 8,
          padding: "7px 12px",
          background: "var(--bg-2)",
          border: "1px solid var(--border)",
          borderRadius: "var(--r-2)",
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
          style={{ fontSize: 12, flex: 1, color: "var(--fg-0)" }}
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

      {stepper}

      {/* числа */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
          gap: 10,
        }}
      >
        <Stat
          label={t("panel.stats.incoming")}
          value={status.behind}
          icon={
            <ArrowDown
              size={15}
              aria-hidden="true"
              style={{ color: "var(--accent)" }}
            />
          }
          sub={
            status.behind > 0 && status.behind_files > 0
              ? t("panel.stats.incomingFiles", { count: status.behind_files })
              : t("panel.stats.nothing")
          }
        />
        <Stat
          label={t("panel.stats.outgoing")}
          value={status.ahead}
          icon={
            <ArrowUp
              size={15}
              aria-hidden="true"
              style={{ color: "var(--c-info)" }}
            />
          }
          sub={
            status.ahead > 0
              ? t("panel.stats.outgoingHint")
              : t("panel.stats.nothing")
          }
        />
        <Stat
          label={t("panel.stats.checked")}
          value={
            <span style={{ fontSize: 14 }}>
              {checkedAt
                ? formatRelativeTime(checkedAt, now)
                : t("panel.stats.never")}
            </span>
          }
          sub={
            status.auto_fetch.enabled
              ? t("panel.stats.autoOn")
              : t("panel.stats.autoOff")
          }
        />
        <Stat
          label={t("panel.stats.synced")}
          value={
            <span style={{ fontSize: 14 }}>
              {status.last_sync_at
                ? formatRelativeTime(status.last_sync_at, now)
                : t("panel.stats.never")}
            </span>
          }
          sub={
            status.last_sync
              ? t(`outcome.${status.last_sync.outcome}`, {
                  defaultValue: status.last_sync.outcome,
                })
              : undefined
          }
        />
      </div>

      {notices.length > 0 && (
        <div className="flex flex-col" style={{ gap: 8 }}>
          {notices}
        </div>
      )}

      {/* что пришло и что не отправлено */}
      {(hasIncoming || hasOutgoing) && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: 20,
            alignItems: "start",
          }}
        >
          {hasIncoming && (
            <div style={{ minWidth: 0 }}>
              <CommitSection
                title={t("popover.incoming")}
                total={status.behind}
                commits={status.incoming}
                now={now}
                moreLabel={moreLabel}
                selectedId={selectedIncomingId}
                onSelect={(id) => {
                  onSelectIncoming(selectedIncomingId === id ? null : id);
                }}
                footer={linkButton("incoming", t("panel.showIncoming"))}
              />
            </div>
          )}
          {hasOutgoing && (
            <div style={{ minWidth: 0 }}>
              <CommitSection
                title={t("popover.outgoing")}
                total={status.ahead}
                commits={status.outgoing}
                now={now}
                moreLabel={moreLabel}
                footer={linkButton("unpushed", t("panel.showOutgoing"))}
              />
            </div>
          )}
        </div>
      )}

      {hasIncoming && selectedIncomingId !== null && incomingDetails}

      <p className="dim" style={{ margin: 0, fontSize: 11, lineHeight: 1.45 }}>
        {t("popover.hint")}
        {onBundle && (
          <>
            {" "}
            <button
              type="button"
              className="sync-history-link"
              onClick={onBundle}
            >
              {t("panel.bundleLink")}
            </button>
          </>
        )}
      </p>
    </div>
  );
};
