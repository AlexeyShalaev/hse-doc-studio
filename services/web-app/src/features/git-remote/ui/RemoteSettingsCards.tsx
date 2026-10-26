import { useState, type ReactNode } from "react";
import {
  CloudOff,
  ExternalLink,
  KeyRound,
  Lock,
  RefreshCw,
  Unplug,
} from "lucide-react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { useAppSettings } from "@entities/app-settings";
import { useCredentials, type GitCredential } from "@entities/git-remote";
import {
  AUTHOR_PROFILE_PATH,
  GIT_ACCESS_PATH,
  gitConflictsPath,
  gitErrorMessage,
  useSyncStatus,
  useSyncUiStore,
  useUpdateGitSettings,
  type SyncStatusView,
} from "@entities/git-sync";
import { formatRelativeTime } from "@shared/lib";
import { Badge, type BadgeProps } from "@shared/ui/Badge";
import { Notice } from "@shared/ui/ConflictKit";
import { CopyField } from "@shared/ui/CopyField";
import { Select } from "@shared/ui/Select";
import { Spinner } from "@shared/ui/Spinner";
import {
  DEFAULT_INTERVAL_CHOICE,
  FALLBACK_FETCH_INTERVAL_S,
  intervalChoiceValue,
  intervalChoices,
  parseIntervalChoice,
  splitInterval,
} from "../model/fetchIntervals";
import { CredentialStatusChip } from "./CredentialStatusChip";
import { DisconnectDialog } from "./DisconnectDialog";
import { SharedFolderWarning } from "./SharedFolderWarning";
import { SwitchRow } from "./SwitchRow";

// Карточки раздела «Синхронизация» в настройках проекта. Заголовки карточек
// рисует страница, здесь только содержимое: оно умеет читать состояние проекта
// и действовать, но не знает, в какой карточке оно показано.

export type RemoteSettingsCardProps = {
  projectId: string;
};

const STATE_VARIANT: Record<string, BadgeProps["variant"]> = {
  up_to_date: "success",
  ahead: "info",
  behind: "info",
  diverged: "info",
  syncing: "info",
  conflicts: "warning",
  offline: "warning",
  blocked: "warning",
  auth_failed: "error",
  error: "error",
};

const Row = ({ label, children }: { label: string; children: ReactNode }) => (
  <div
    style={{
      display: "grid",
      gridTemplateColumns: "minmax(96px, 132px) minmax(0, 1fr)",
      gap: 12,
      alignItems: "start",
    }}
  >
    <dt className="dim" style={{ fontSize: 11.5, paddingTop: 3 }}>
      {label}
    </dt>
    <dd style={{ margin: 0, minWidth: 0, fontSize: 12.5 }}>{children}</dd>
  </div>
);

const Loading = ({ label }: { label: string }) => (
  <div
    className="flex items-center"
    style={{ gap: 8, fontSize: 12 }}
    data-testid="remote-settings-loading"
  >
    <Spinner size="sm" />
    <span className="dim">{label}</span>
  </div>
);

// --- репозиторий ---------------------------------------------------------------

const EmptyRemote = () => {
  const { t } = useTranslation("gitRemote");
  return (
    <div
      className="flex flex-col items-center"
      data-testid="remote-empty"
      style={{
        gap: 10,
        padding: "22px 16px",
        textAlign: "center",
        borderRadius: "var(--r-3)",
        border: "1px dashed var(--border-strong)",
        background: "var(--bg-1)",
      }}
    >
      <span
        aria-hidden="true"
        className="flex items-center justify-center"
        style={{
          width: 40,
          height: 40,
          borderRadius: "50%",
          background: "var(--bg-2)",
          color: "var(--fg-2)",
        }}
      >
        <CloudOff size={18} />
      </span>
      <strong style={{ fontSize: 13 }}>
        {t("settings.remote.emptyTitle")}
      </strong>
      <p
        className="dim"
        style={{ margin: 0, maxWidth: 420, fontSize: 12, lineHeight: 1.55 }}
      >
        {t("settings.remote.emptyText")}
      </p>
      <button
        type="button"
        className="btn primary"
        onClick={() => {
          useSyncUiStore.getState().openConnectDialog("connect");
        }}
      >
        {t("settings.remote.connect")}
      </button>
    </div>
  );
};

type AccessBlockProps = {
  status: SyncStatusView;
  credential: GitCredential | null;
};

const AccessBlock = ({ status, credential }: AccessBlockProps) => {
  const { t } = useTranslation("gitRemote");
  const [keyShown, setKeyShown] = useState(false);
  const brief = status.remote?.credential ?? null;

  if (!brief) {
    return (
      <span className="dim" data-testid="remote-no-credential">
        {t("settings.remote.noCredential")}
      </span>
    );
  }

  const kind = credential?.kind ?? brief.kind;
  const publicKey = credential?.public_key ?? null;
  const fingerprint = credential?.fingerprint_sha256 ?? null;
  const Icon = kind === "ssh_key" ? KeyRound : Lock;
  return (
    <div className="flex flex-col" style={{ gap: 8 }}>
      <div className="flex items-center" style={{ gap: 8, flexWrap: "wrap" }}>
        <Icon
          size={13}
          aria-hidden="true"
          style={{ color: "var(--fg-2)", flexShrink: 0 }}
        />
        <strong style={{ fontWeight: 600 }}>
          {credential?.label ?? brief.label}
        </strong>
        <span className="chip subtle">
          {t(`credentialKind.${kind}`, { defaultValue: kind })}
        </span>
        <CredentialStatusChip status={credential?.status ?? "unverified"} />
        {credential?.token_family && (
          <span className="mono dim" style={{ fontSize: 11 }}>
            {t("settings.remote.tokenFamily", {
              family: credential.token_family,
            })}
          </span>
        )}
      </div>
      <div className="flex items-center" style={{ gap: 6, flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn xs"
          onClick={() => {
            useSyncUiStore.getState().openConnectDialog("fix_access");
          }}
        >
          {t("settings.remote.replaceAccess")}
        </button>
        {kind === "ssh_key" && publicKey && (
          <button
            type="button"
            className="btn xs ghost"
            aria-expanded={keyShown}
            aria-controls="remote-public-key"
            onClick={() => {
              setKeyShown((shown) => !shown);
            }}
          >
            {keyShown
              ? t("settings.remote.hideKey")
              : t("settings.remote.showKey")}
          </button>
        )}
      </div>
      {keyShown && publicKey && (
        <div
          id="remote-public-key"
          className="flex flex-col"
          style={{ gap: 6 }}
        >
          <CopyField
            multiline
            value={publicKey}
            label={t("settings.remote.publicKey")}
          />
          {fingerprint && (
            <span className="dim" style={{ fontSize: 11 }}>
              {t("settings.remote.fingerprint")}:{" "}
              <span className="mono">{fingerprint}</span>
            </span>
          )}
        </div>
      )}
    </div>
  );
};

// Что мешает синхронизации и что с этим делать: те же причины, что и в панели
// синхронизации, поэтому тексты общие.
const BlockedNotice = ({ status }: { status: SyncStatusView }) => {
  const { t } = useTranslation("gitRemote");
  const { t: tSync } = useTranslation("gitSync");
  const navigate = useNavigate();
  const blocked = status.blocked;
  if (!blocked) return null;
  const text =
    blocked.reason === "remote_schema_newer"
      ? tSync("popover.schemaNewer", { studio: blocked.required_studio ?? "" })
      : tSync(`blocked.${blocked.reason}`, {
          defaultValue: tSync("control.status.blocked_unknown"),
        });
  return (
    <Notice
      tone="warn"
      role="status"
      text={text}
      action={
        blocked.reason === "profile_required" ? (
          <button
            type="button"
            className="btn xs"
            onClick={() => {
              void navigate(AUTHOR_PROFILE_PATH);
            }}
          >
            {t("settings.remote.setProfile")}
          </button>
        ) : undefined
      }
    />
  );
};

const HealthNotice = ({ status }: { status: SyncStatusView }) => {
  const { t } = useTranslation("gitRemote");
  const error = status.last_error;
  if (status.health === "ok" || !error) return null;
  return (
    <Notice
      tone={status.health === "offline" ? "warn" : "err"}
      role="alert"
      text={gitErrorMessage(error.code, error.detail)}
      action={
        status.health === "unauthenticated" ? (
          <button
            type="button"
            className="btn xs"
            onClick={() => {
              useSyncUiStore.getState().openConnectDialog("fix_access");
            }}
          >
            {t("settings.remote.replaceAccess")}
          </button>
        ) : undefined
      }
    />
  );
};

export const RemoteConnectionCard = ({
  projectId,
}: RemoteSettingsCardProps) => {
  const { t } = useTranslation("gitRemote");
  const { t: tSync } = useTranslation("gitSync");
  const navigate = useNavigate();
  const statusQuery = useSyncStatus(projectId);
  const status = statusQuery.data;
  const remote = status?.remote ?? null;
  const connected = status?.connected === true && remote !== null;
  const credentials = useCredentials(connected);
  const [disconnectOpen, setDisconnectOpen] = useState(false);

  if (!status) {
    if (statusQuery.isError) {
      return (
        <Notice
          tone="err"
          role="alert"
          text={t("settings.remote.loadFailed")}
          action={
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                void statusQuery.refetch();
              }}
            >
              {t("settings.remote.retry")}
            </button>
          }
        />
      );
    }
    return <Loading label={t("settings.remote.loading")} />;
  }
  if (!status.supported) return null;
  if (!connected) return <EmptyRemote />;

  const credential =
    credentials.data?.find((item) => item.id === remote.credential?.id) ?? null;
  const isBusy = status.operation !== null && status.operation !== undefined;
  const hasConflicts = !!status.pending;
  const isBlocked = !!status.blocked;
  const lastSync = status.last_sync;
  const mapped = remote.local_branch !== remote.branch;

  return (
    <div
      className="flex flex-col"
      style={{ gap: 14 }}
      data-testid="remote-card"
    >
      <div className="flex items-center" style={{ gap: 8, flexWrap: "wrap" }}>
        <Badge variant={STATE_VARIANT[status.ui_state] ?? "default"}>
          {tSync(`state.${status.ui_state}`, { defaultValue: status.ui_state })}
        </Badge>
        <span className="chip accent">
          {t(`provider.${remote.provider}`, { defaultValue: remote.provider })}
        </span>
        {remote.host && (
          <span className="mono dim" style={{ fontSize: 11.5 }}>
            {remote.host}
          </span>
        )}
      </div>

      <HealthNotice status={status} />
      <BlockedNotice status={status} />

      <dl
        style={{ margin: 0, display: "flex", flexDirection: "column", gap: 14 }}
      >
        <Row label={t("settings.remote.address")}>
          <div className="flex flex-col" style={{ gap: 6 }}>
            <CopyField
              value={remote.display_url}
              label={t("settings.remote.addressLabel")}
            />
            {remote.kind === "http" && (
              <Notice tone="warn" text={t("settings.remote.insecure")} />
            )}
            {remote.web_url && (
              <div>
                <a
                  className="btn xs ghost"
                  href={remote.web_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <ExternalLink size={11} aria-hidden="true" />
                  {t("settings.remote.openInBrowser")}
                </a>
              </div>
            )}
          </div>
        </Row>
        <Row label={t("settings.remote.branch")}>
          <span
            className="flex items-center"
            style={{ gap: 8, flexWrap: "wrap" }}
          >
            <span className="chip mono">{remote.branch}</span>
            {mapped && (
              <span className="dim" style={{ fontSize: 11.5 }}>
                {tSync("popover.branchMapped", {
                  local: remote.local_branch,
                  remote: remote.branch,
                })}
              </span>
            )}
          </span>
        </Row>
        <Row label={t("settings.remote.access")}>
          <AccessBlock status={status} credential={credential} />
        </Row>
        <Row label={t("settings.remote.lastSync")}>
          {lastSync ? (
            t("settings.remote.lastSyncDetail", {
              outcome: tSync(`outcome.${lastSync.outcome}`, {
                defaultValue: lastSync.outcome,
              }),
              when: formatRelativeTime(lastSync.at),
              pulled: lastSync.pulled_commits,
              pushed: lastSync.pushed_commits,
            })
          ) : status.last_sync_at ? (
            formatRelativeTime(status.last_sync_at)
          ) : (
            <span className="dim">{t("settings.remote.neverSynced")}</span>
          )}
        </Row>
        <Row label={t("settings.remote.lastCheck")}>
          {status.last_fetch_ok_at ? (
            t("settings.remote.checkedAt", {
              when: formatRelativeTime(status.last_fetch_ok_at),
            })
          ) : (
            <span className="dim">{t("settings.remote.neverChecked")}</span>
          )}
        </Row>
      </dl>

      <div className="flex items-center" style={{ gap: 8, flexWrap: "wrap" }}>
        {hasConflicts ? (
          <button
            type="button"
            className="btn primary"
            onClick={() => {
              void navigate(gitConflictsPath(projectId));
            }}
          >
            {t("settings.remote.resolve")}
          </button>
        ) : (
          <button
            type="button"
            className="btn primary"
            disabled={isBusy || isBlocked}
            onClick={() => {
              useSyncUiStore.getState().requestCommand("sync");
            }}
          >
            {isBusy ? (
              <Spinner size="sm" />
            ) : (
              <RefreshCw size={12} aria-hidden="true" />
            )}
            {isBusy
              ? t("settings.remote.syncing")
              : t("settings.remote.syncNow")}
          </button>
        )}
        <button
          type="button"
          className="btn"
          disabled={isBusy}
          onClick={() => {
            useSyncUiStore.getState().requestCommand("check");
          }}
        >
          {t("settings.remote.check")}
        </button>
      </div>

      <div
        className="flex items-center justify-between"
        style={{
          gap: 12,
          padding: 12,
          border:
            "1px solid color-mix(in oklch, var(--c-err) 30%, var(--border))",
          borderRadius: "var(--r-2)",
        }}
      >
        <div className="flex flex-col" style={{ gap: 2, minWidth: 0 }}>
          <strong style={{ fontSize: 12.5 }}>
            {t("settings.danger.title")}
          </strong>
          <span className="dim" style={{ fontSize: 11, lineHeight: 1.5 }}>
            {t("settings.danger.text")}
          </span>
        </div>
        <button
          type="button"
          className="btn danger"
          style={{ flexShrink: 0 }}
          onClick={() => {
            setDisconnectOpen(true);
          }}
        >
          <Unplug size={11} aria-hidden="true" />
          {t("settings.danger.button")}
        </button>
      </div>

      <DisconnectDialog
        isOpen={disconnectOpen}
        projectId={projectId}
        remote={remote}
        unsent={status.ahead}
        credential={credential}
        onClose={() => {
          setDisconnectOpen(false);
        }}
      />
    </div>
  );
};

// --- фоновая проверка ----------------------------------------------------------

export const FetchOptionsCard = ({ projectId }: RemoteSettingsCardProps) => {
  const { t } = useTranslation("gitRemote");
  const navigate = useNavigate();
  const { data: status } = useSyncStatus(projectId);
  const { data: appSettings } = useAppSettings();
  const update = useUpdateGitSettings();

  if (!status?.connected) return null;

  const defaultInterval =
    appSettings?.git_fetch_interval_s ?? FALLBACK_FETCH_INTERVAL_S;
  const {
    enabled,
    interval_s: interval,
    next_fetch_at: nextFetchAt,
  } = status.auto_fetch;
  const intervalLabel = (seconds: number): string => {
    const { unit, count } = splitInterval(seconds);
    return t(`settings.interval.${unit}`, { count });
  };
  const defaultLabel =
    defaultInterval > 0
      ? intervalLabel(defaultInterval)
      : t("settings.options.intervalOff");
  const options = [
    {
      value: DEFAULT_INTERVAL_CHOICE,
      label: t("settings.options.intervalDefault", { interval: defaultLabel }),
    },
    ...intervalChoices(interval).map((seconds) => ({
      value: String(seconds),
      label: intervalLabel(seconds),
    })),
  ];
  const pendingKind = update.isPending
    ? "auto_fetch" in update.variables.params
      ? "toggle"
      : "interval"
    : null;

  return (
    <div
      className="flex flex-col"
      style={{ gap: 12 }}
      data-testid="fetch-options"
    >
      <SwitchRow
        id="git-auto-fetch"
        label={t("settings.options.autoFetch")}
        hint={t("settings.options.autoFetchHint")}
        checked={enabled}
        disabled={update.isPending}
        busy={pendingKind === "toggle"}
        onChange={(next) => {
          update.mutate({ projectId, params: { auto_fetch: next } });
        }}
      />

      <div className="flex flex-col" style={{ gap: 6 }}>
        <label
          htmlFor="git-fetch-interval"
          style={{ fontSize: 12, fontWeight: 500 }}
        >
          {t("settings.options.interval")}
        </label>
        <div className="flex items-center" style={{ gap: 8 }}>
          <div style={{ width: 260, maxWidth: "100%" }}>
            <Select
              id="git-fetch-interval"
              placeholder={t("settings.options.interval")}
              value={intervalChoiceValue(interval, defaultInterval)}
              options={options}
              isDisabled={!enabled || update.isPending}
              onValueChange={(value) => {
                update.mutate({
                  projectId,
                  params: { interval_s: parseIntervalChoice(value) },
                });
              }}
            />
          </div>
          {pendingKind === "interval" && <Spinner size="sm" />}
        </div>
        <span className="dim" style={{ fontSize: 11 }}>
          {enabled && nextFetchAt
            ? t("settings.options.nextCheck", {
                when: formatRelativeTime(nextFetchAt),
              })
            : status.last_fetch_ok_at
              ? t("settings.options.lastCheck", {
                  when: formatRelativeTime(status.last_fetch_ok_at),
                })
              : t("settings.options.neverChecked")}
        </span>
      </div>

      {update.isError && (
        <Notice
          tone="err"
          role="alert"
          text={t("settings.options.saveFailed")}
        />
      )}

      <Notice
        tone="info"
        text={t("settings.options.personalNote")}
        action={
          <button
            type="button"
            className="btn xs"
            style={{ flexShrink: 0 }}
            onClick={() => {
              void navigate(GIT_ACCESS_PATH);
            }}
          >
            {t("settings.options.defaultLink")}
          </button>
        }
      />
    </div>
  );
};

// --- папка в облачном диске ----------------------------------------------------

export const SharedFolderCard = ({ projectId }: RemoteSettingsCardProps) => {
  const { t } = useTranslation("gitRemote");
  const { data: status } = useSyncStatus(projectId);
  const update = useUpdateGitSettings();
  const shared = status?.shared_folder ?? null;
  if (!shared) return null;

  return (
    <div
      className="flex flex-col"
      style={{ gap: 12 }}
      data-testid="shared-folder-card"
    >
      <SharedFolderWarning provider={shared.provider} />
      <span className="dim" style={{ fontSize: 11.5, lineHeight: 1.5 }}>
        <span className="mono" title={shared.root}>
          {t("sharedFolder.root", { path: shared.root })}
        </span>
        <br />
        {t("sharedFolder.advice")}
      </span>
      <SwitchRow
        id="git-shared-ack"
        label={t("sharedFolder.acknowledgeToggle")}
        hint={t("sharedFolder.acknowledgeHint")}
        checked={shared.acknowledged}
        disabled={update.isPending}
        busy={update.isPending}
        onChange={(next) => {
          update.mutate({ projectId, params: { shared_folder_ack: next } });
        }}
      />
      {update.isError && (
        <Notice
          tone="err"
          role="alert"
          text={t("settings.options.saveFailed")}
        />
      )}
    </div>
  );
};
