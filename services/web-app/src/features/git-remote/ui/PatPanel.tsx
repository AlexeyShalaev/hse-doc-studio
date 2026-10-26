import { useId } from "react";
import { Eye, EyeOff, Lock } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { GitCredential } from "@entities/git-remote";
import { Notice } from "@shared/ui/ConflictKit";
import type { ParsedRemoteUrl } from "../lib/parseRemoteUrl";
import { CredentialStatusChip } from "./CredentialStatusChip";
import { ProviderHelp } from "./ProviderHelp";

export type PatDraft = {
  token: string;
  username: string;
  label: string;
};

export type PatPanelProps = {
  draft: PatDraft;
  onChange: (next: PatDraft) => void;
  showToken: boolean;
  onToggleShowToken: () => void;
  url: ParsedRemoteUrl;
  /** Если задан, токен заменяет прежний у этого доступа, а не создаёт новый. */
  existing?: GitCredential | null;
  disabled?: boolean;
  error?: string | null;
  /** Раскрыть памятку «как получить токен»: нужна тому, у кого токена ещё нет. */
  helpOpen?: boolean;
};

// Форма токена. Сам токен живёт только в состоянии шага и очищается сразу, как
// запрос ушёл (успешно или нет): в сохранённом виде его больше никто не увидит.
export const PatPanel = ({
  draft,
  onChange,
  showToken,
  onToggleShowToken,
  url,
  existing = null,
  disabled = false,
  error = null,
  helpOpen = true,
}: PatPanelProps) => {
  const { t } = useTranslation("gitAccess");
  const uid = useId();
  const tokenId = `${uid}-token`;
  const tokenHintId = `${uid}-token-hint`;
  const userId = `${uid}-user`;
  const labelId = `${uid}-label`;

  return (
    <div className="flex flex-col" style={{ gap: 12 }} data-testid="pat-panel">
      {existing && (
        <div
          className="flex items-center"
          style={{
            gap: 8,
            padding: "8px 10px",
            borderRadius: "var(--r-2)",
            background: "var(--bg-2)",
            border: "1px solid var(--border)",
            fontSize: 12,
          }}
        >
          <Lock size={13} aria-hidden="true" style={{ flexShrink: 0 }} />
          <span className="truncate" style={{ minWidth: 0, flex: 1 }}>
            {existing.label}
            {existing.token_family && (
              <span className="mono dim"> · {existing.token_family}…</span>
            )}
          </span>
          <CredentialStatusChip status={existing.status} />
        </div>
      )}

      <div className="field">
        <label htmlFor={tokenId}>
          {existing ? t("pat.newToken") : t("pat.token")}
        </label>
        <div className="flex" style={{ gap: 6 }}>
          <input
            id={tokenId}
            // Случайное имя и autocomplete выключены: менеджер паролей не должен
            // подставлять сюда пароль от сайта и не должен запоминать токен.
            name={`token-${uid}`}
            type={showToken ? "text" : "password"}
            className="input mono"
            style={{ flex: 1, minWidth: 0 }}
            value={draft.token}
            autoFocus
            autoComplete="off"
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
            disabled={disabled}
            placeholder={t("pat.tokenPlaceholder")}
            aria-describedby={tokenHintId}
            data-lpignore="true"
            data-1p-ignore="true"
            onChange={(event) => {
              onChange({ ...draft, token: event.target.value });
            }}
          />
          <button
            type="button"
            className="btn"
            style={{ flexShrink: 0 }}
            aria-pressed={showToken}
            aria-label={showToken ? t("pat.hide") : t("pat.show")}
            title={showToken ? t("pat.hide") : t("pat.show")}
            onClick={onToggleShowToken}
          >
            {showToken ? (
              <EyeOff size={14} aria-hidden="true" />
            ) : (
              <Eye size={14} aria-hidden="true" />
            )}
          </button>
        </div>
        <p id={tokenHintId} className="hint" style={{ margin: 0 }}>
          {t("pat.stored")}
        </p>
      </div>

      {error && <Notice tone="err" role="alert" text={error} />}

      <ProviderHelp url={url} kind="token" defaultOpen={helpOpen} />

      {!existing && (
        <details className="sync-details">
          <summary>{t("pat.advanced")}</summary>
          <div
            className="flex flex-col"
            style={{ gap: 10, marginTop: 8, maxWidth: 360 }}
          >
            <div className="field">
              <label htmlFor={labelId}>{t("pat.label")}</label>
              <input
                id={labelId}
                type="text"
                className="input"
                value={draft.label}
                autoComplete="off"
                onChange={(event) => {
                  onChange({ ...draft, label: event.target.value });
                }}
              />
            </div>
            <div className="field">
              <label htmlFor={userId}>{t("pat.username")}</label>
              <input
                id={userId}
                type="text"
                className="input"
                value={draft.username}
                autoComplete="off"
                spellCheck={false}
                onChange={(event) => {
                  onChange({ ...draft, username: event.target.value });
                }}
              />
              <p className="hint" style={{ margin: 0 }}>
                {t("pat.usernameHint")}
              </p>
            </div>
          </div>
        </details>
      )}
    </div>
  );
};
