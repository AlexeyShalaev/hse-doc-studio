import { Fingerprint, FolderGit2, KeyRound, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { GitCredential } from "@entities/git-remote";
import { Notice } from "@shared/ui/ConflictKit";
import { CopyField } from "@shared/ui/CopyField";
import { Spinner } from "@shared/ui/Spinner";
import type { ParsedRemoteUrl } from "../lib/parseRemoteUrl";
import { CredentialStatusChip } from "./CredentialStatusChip";
import { formatDate } from "../lib/formatDate";
import { ProviderHelp, type KeyScope } from "./ProviderHelp";

export type SshKeyPanelProps = {
  url: ParsedRemoteUrl;
  /** Какой это ключ: пользователя (на все репозитории сервера) или deploy (на один). */
  scope: KeyScope;
  /** «владелец/репозиторий»: для deploy-ключа это то, к чему он привязан. */
  repoPath?: string;
  /** Ключи ssh, созданные для этого сервера. */
  keys: GitCredential[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  isCreating: boolean;
  disabled?: boolean;
  error?: string | null;
};

// Ключ ssh: создаётся одной кнопкой, закрытая часть остаётся на компьютере, а
// публичную человек добавляет в репозиторий по подсказке с прямой ссылкой.
export const SshKeyPanel = ({
  url,
  scope,
  repoPath = "",
  keys,
  selectedId,
  onSelect,
  onCreate,
  isCreating,
  disabled = false,
  error = null,
}: SshKeyPanelProps) => {
  const { t } = useTranslation("gitAccess");
  const selected = keys.find((key) => key.id === selectedId) ?? null;
  const repoPill =
    scope === "deploy" && repoPath !== "" ? (
      <div
        className="flex items-center"
        data-testid="deploy-repo"
        style={{
          gap: 6,
          alignSelf: "flex-start",
          maxWidth: "100%",
          padding: "3px 8px",
          borderRadius: "var(--r-2)",
          border: "1px solid var(--border)",
          background: "var(--bg-2)",
          fontSize: 11.5,
        }}
      >
        <FolderGit2 size={12} aria-hidden="true" style={{ flexShrink: 0 }} />
        <span className="dim">{t("ssh.deployFor")}</span>
        <span className="mono truncate" style={{ minWidth: 0 }}>
          {repoPath}
        </span>
      </div>
    ) : null;

  const createButton = (primary: boolean) => (
    <button
      type="button"
      className={primary ? "btn primary" : "btn sm"}
      disabled={disabled || isCreating}
      onClick={onCreate}
    >
      {isCreating ? (
        <Spinner size="sm" />
      ) : (
        <Plus size={13} aria-hidden="true" />
      )}
      {primary
        ? t(scope === "deploy" ? "ssh.createDeploy" : "ssh.create")
        : t("ssh.createAnother")}
    </button>
  );

  if (keys.length === 0) {
    return (
      <div
        className="flex flex-col"
        style={{ gap: 12 }}
        data-testid="ssh-panel"
        data-scope={scope}
      >
        {repoPill}
        <div
          className="flex flex-col items-start"
          style={{
            gap: 10,
            padding: 16,
            borderRadius: "var(--r-3)",
            border: "1px dashed var(--border-strong)",
            background: "var(--bg-2)",
          }}
        >
          <span
            aria-hidden="true"
            style={{
              width: 32,
              height: 32,
              borderRadius: "50%",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              background: "var(--accent-soft)",
              color: "var(--accent)",
            }}
          >
            <KeyRound size={16} />
          </span>
          <div style={{ fontSize: 12.5, lineHeight: 1.5 }}>
            <strong style={{ display: "block", fontWeight: 600 }}>
              {scope === "deploy"
                ? t("ssh.deployEmptyTitle", { repo: repoPath })
                : t("ssh.emptyTitle")}
            </strong>
            <span className="dim">
              {t(scope === "deploy" ? "ssh.deployEmptyText" : "ssh.emptyText")}
            </span>
          </div>
          {createButton(true)}
        </div>
        {error && <Notice tone="err" role="alert" text={error} />}
      </div>
    );
  }

  return (
    <div
      className="flex flex-col"
      style={{ gap: 12 }}
      data-testid="ssh-panel"
      data-scope={scope}
    >
      {repoPill}
      {keys.length > 1 && (
        <div
          role="radiogroup"
          aria-label={t("ssh.chooseKey")}
          className="flex flex-col"
          style={{ gap: 4 }}
        >
          {keys.map((key) => (
            <label
              key={key.id}
              className="flex items-center"
              style={{
                gap: 8,
                padding: "6px 8px",
                borderRadius: "var(--r-2)",
                cursor: "pointer",
                fontSize: 12.5,
                background:
                  key.id === selectedId ? "var(--accent-soft)" : "transparent",
              }}
            >
              <input
                type="radio"
                name="ssh-key"
                checked={key.id === selectedId}
                onChange={() => {
                  onSelect(key.id);
                }}
                style={{ accentColor: "var(--accent)" }}
              />
              <span className="truncate" style={{ flex: 1, minWidth: 0 }}>
                {key.label}
              </span>
              <span className="dim" style={{ fontSize: 11 }}>
                {formatDate(key.created_at)}
              </span>
            </label>
          ))}
        </div>
      )}

      {selected?.public_key && (
        <div className="flex flex-col" style={{ gap: 8 }}>
          <div
            className="flex items-center"
            style={{ gap: 8, justifyContent: "space-between" }}
          >
            <span style={{ fontSize: 12, fontWeight: 600 }}>
              {t("ssh.publicKey")}
            </span>
            <CredentialStatusChip status={selected.status} />
          </div>
          <CopyField
            value={selected.public_key}
            label={t("ssh.publicKey")}
            multiline
          />
          {selected.fingerprint_sha256 && (
            <div
              className="flex items-center dim"
              style={{ gap: 6, fontSize: 11.5, minWidth: 0 }}
            >
              <Fingerprint size={12} aria-hidden="true" />
              <span>{t("ssh.fingerprint")}</span>
              <span
                className="mono truncate"
                style={{ color: "var(--fg-1)", minWidth: 0 }}
                data-testid="ssh-fingerprint"
              >
                {selected.fingerprint_sha256}
              </span>
            </div>
          )}
        </div>
      )}

      <p className="dim" style={{ margin: 0, fontSize: 11.5 }}>
        {t(`ssh.scope.${scope}Hint`)}
      </p>

      {scope === "deploy" && (
        <Notice tone="warn" role="status" text={t("ssh.allowWrite")} />
      )}

      <ProviderHelp url={url} scope={scope} defaultOpen />

      {error && <Notice tone="err" role="alert" text={error} />}

      <div>{createButton(false)}</div>
    </div>
  );
};
