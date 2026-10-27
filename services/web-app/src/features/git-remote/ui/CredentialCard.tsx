import { useState } from "react";
import { KeyRound, Lock, ScanSearch, Trash2 } from "lucide-react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import {
  credentialExpiry,
  providerOfHost,
  useCheckCredential,
  useHostSettings,
  type GitCredential,
} from "@entities/git-remote";
import { gitSettingsPath } from "@entities/git-sync";
import { formatRelativeTime } from "@shared/lib";
import { CopyField } from "@shared/ui/CopyField";
import { Popover, PopoverContent, PopoverTrigger } from "@shared/ui/Popover";
import { urlForHost } from "../lib/hostUrl";
import { tokenCreateUrl } from "../lib/providerHelp";
import {
  verdictOfCheck,
  verdictOfError,
  type TokenVerdict,
} from "../model/tokenVerdict";
import { CredentialStatusChip } from "./CredentialStatusChip";
import { DeleteCredentialDialog } from "./DeleteCredentialDialog";
import { ExpiryBadge } from "./ExpiryBadge";
import { ReplaceTokenDialog } from "./ReplaceTokenDialog";
import { TlsTrustDialog } from "./TlsTrustDialog";
import { TokenCheckCard } from "./TokenCheckCard";

export type CredentialCardProps = {
  credential: GitCredential;
};

// Один сохранённый доступ: что это, работает ли, где используется. Самих токенов
// сюда не приходит: только начало вида, итог проверки и публичная часть ключа.
export const CredentialCard = ({ credential }: CredentialCardProps) => {
  const { t } = useTranslation("gitAccess");
  const { t: tRemote } = useTranslation("gitRemote");
  const [keyShown, setKeyShown] = useState(false);
  const [dialog, setDialog] = useState<"replace" | "delete" | "tls" | null>(
    null,
  );
  const hostSettings = useHostSettings();
  const checkCredential = useCheckCredential();
  // null: проверку не просили; "running": идёт; иначе ответ сервера.
  const [check, setCheck] = useState<
    null | "running" | { verdict: TokenVerdict; version: string | null }
  >(null);

  const isKey = credential.kind === "ssh_key";
  const Icon = isKey ? KeyRound : Lock;
  const usedCount = credential.used_by.length;
  const detection = providerOfHost(credential.host, null, hostSettings.data);
  const keyId = `credential-key-${credential.id}`;

  const runCheck = async (): Promise<void> => {
    setCheck("running");
    try {
      const result = await checkCredential.mutateAsync(credential.id);
      setCheck({
        verdict: verdictOfCheck(result),
        version: result.provider_info.version ?? null,
      });
    } catch (caught) {
      setCheck({
        verdict: verdictOfError(caught, credential.expires_at),
        version: null,
      });
    }
  };
  const verdict = typeof check === "object" && check ? check.verdict : null;
  // Токен не принят или срок вышел (или вот-вот выйдет): первым делом нужен новый.
  const expiryState = credentialExpiry(credential.expires_at).state;
  const needsNewToken =
    !isKey &&
    (credential.status === "auth_failed" ||
      expiryState === "expired" ||
      expiryState === "soon");

  return (
    <li
      className="flex flex-col"
      data-testid="credential-card"
      style={{
        gap: 10,
        padding: 12,
        borderRadius: "var(--r-2)",
        border: "1px solid var(--border)",
        background: "var(--bg-0)",
        listStyle: "none",
      }}
    >
      <div className="flex items-start" style={{ gap: 10 }}>
        <span
          aria-hidden="true"
          className="flex items-center justify-center"
          style={{
            width: 28,
            height: 28,
            flexShrink: 0,
            borderRadius: "var(--r-2)",
            background: "var(--bg-2)",
            color: "var(--fg-1)",
          }}
        >
          <Icon size={14} />
        </span>
        <div className="flex flex-col" style={{ gap: 4, flex: 1, minWidth: 0 }}>
          <div
            className="flex items-center"
            style={{ gap: 6, flexWrap: "wrap" }}
          >
            <strong className="truncate" style={{ fontSize: 13, minWidth: 0 }}>
              {credential.label}
            </strong>
            <span className="chip subtle">
              {tRemote(`credentialKind.${credential.kind}`, {
                defaultValue: credential.kind,
              })}
            </span>
            <CredentialStatusChip status={credential.status} />
            {!isKey && <ExpiryBadge expiresAt={credential.expires_at} />}
          </div>
          <span
            className="dim flex items-center"
            style={{ gap: 6, fontSize: 11.5, flexWrap: "wrap" }}
          >
            <span className="mono">{credential.host}</span>
            {credential.token_family && (
              <span className="mono">
                {t("access.credentials.tokenFamily", {
                  family: credential.token_family,
                })}
              </span>
            )}
            {isKey && credential.fingerprint_sha256 && (
              <span className="mono truncate" style={{ minWidth: 0 }}>
                {credential.fingerprint_sha256}
              </span>
            )}
          </span>
          <span className="dim" style={{ fontSize: 11.5 }}>
            {t("access.credentials.created", {
              when: formatRelativeTime(credential.created_at),
            })}
            {" · "}
            {credential.last_used_at
              ? t("credentials.lastUsed", {
                  when: formatRelativeTime(credential.last_used_at),
                })
              : t("credentials.neverUsed")}
          </span>
          {!isKey && (
            <ExpiryBadge expiresAt={credential.expires_at} showFar hideSoon />
          )}
          {credential.status === "auth_failed" && (
            <span style={{ fontSize: 11.5, color: "var(--c-err)" }}>
              {t("access.credentials.authFailedHint")}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center" style={{ gap: 6, flexWrap: "wrap" }}>
        {usedCount > 0 ? (
          <Popover>
            <PopoverTrigger asChild>
              <button type="button" className="btn xs ghost">
                {t("credentials.usedBy", { count: usedCount })}
              </button>
            </PopoverTrigger>
            <PopoverContent
              width={300}
              align="start"
              aria-label={t("access.credentials.usedByHeading")}
            >
              <div style={{ padding: 10 }}>
                <div
                  className="dim"
                  style={{
                    fontSize: 10.5,
                    fontWeight: 600,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    marginBottom: 6,
                  }}
                >
                  {t("access.credentials.usedByHeading")}
                </div>
                <ul
                  style={{
                    margin: 0,
                    padding: 0,
                    listStyle: "none",
                    display: "flex",
                    flexDirection: "column",
                    gap: 2,
                  }}
                >
                  {credential.used_by.map((project) => (
                    <li key={project.project_id}>
                      <Link
                        to={gitSettingsPath(project.project_id)}
                        className="row-btn truncate"
                        title={t("access.credentials.openProject", {
                          name: project.name,
                        })}
                        style={{ textDecoration: "none" }}
                      >
                        {project.name}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            </PopoverContent>
          </Popover>
        ) : (
          <span className="dim" style={{ fontSize: 11.5 }}>
            {t("credentials.unused")}
          </span>
        )}
        <span style={{ flex: 1 }} />
        {isKey && credential.public_key && (
          <button
            type="button"
            className="btn xs ghost"
            aria-expanded={keyShown}
            aria-controls={keyId}
            onClick={() => {
              setKeyShown((shown) => !shown);
            }}
          >
            {keyShown
              ? t("access.credentials.hideKey")
              : t("access.credentials.showKey")}
          </button>
        )}
        {!isKey && (
          <button
            type="button"
            className="btn xs"
            data-testid="credential-check"
            disabled={check === "running"}
            onClick={() => {
              void runCheck();
            }}
          >
            <ScanSearch size={11} aria-hidden="true" />
            {t("access.credentials.check")}
          </button>
        )}
        {!isKey && (
          <button
            type="button"
            className={needsNewToken ? "btn xs primary" : "btn xs"}
            onClick={() => {
              setDialog("replace");
            }}
          >
            {t("access.credentials.replace")}
          </button>
        )}
        <button
          type="button"
          className="btn xs danger"
          aria-label={t("access.credentials.deleteLabel", {
            label: credential.label,
          })}
          onClick={() => {
            setDialog("delete");
          }}
        >
          <Trash2 size={11} aria-hidden="true" />
          {t("access.credentials.delete")}
        </button>
      </div>

      {keyShown && credential.public_key && (
        <div id={keyId}>
          <CopyField
            multiline
            value={credential.public_key}
            label={t("access.credentials.publicKey")}
          />
        </div>
      )}

      {check !== null && (
        <TokenCheckCard
          verdict={verdict}
          provider={detection.id}
          version={
            (typeof check === "object" ? check.version : null) ??
            detection.version
          }
          createUrl={tokenCreateUrl(urlForHost(credential.host, detection.id), {
            provider: detection.id,
          })}
          onRetry={() => {
            void runCheck();
          }}
          onReviewCertificate={() => {
            setDialog("tls");
          }}
        />
      )}

      {dialog === "tls" && (
        <TlsTrustDialog
          isOpen
          mode={
            verdict?.kind === "error" && verdict.code === "tls_pin_mismatch"
              ? "pin_mismatch"
              : "untrusted"
          }
          host={credential.host}
          port={null}
          certificate={verdict?.kind === "error" ? verdict.certificate : null}
          expected={verdict?.kind === "error" ? verdict.expected : null}
          actual={verdict?.kind === "error" ? verdict.actual : null}
          onTrusted={() => {
            setDialog(null);
            void runCheck();
          }}
          onClose={() => {
            setDialog(null);
          }}
        />
      )}

      {dialog === "replace" && (
        <ReplaceTokenDialog
          credential={credential}
          onClose={() => {
            setDialog(null);
          }}
        />
      )}
      {dialog === "delete" && (
        <DeleteCredentialDialog
          credential={credential}
          onClose={() => {
            setDialog(null);
          }}
        />
      )}
    </li>
  );
};
