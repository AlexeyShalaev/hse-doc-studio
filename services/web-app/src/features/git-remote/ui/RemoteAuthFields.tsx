import { useState } from "react";
import { ScanSearch } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";
import type { ParsedRemoteUrl } from "../lib/parseRemoteUrl";
import type { AccessMethod, RemoteAuth } from "../model/useRemoteAuth";
import { tokenCreateUrl } from "../lib/providerHelp";
import { useHostProvider } from "../model/useHostProvider";
import { CredentialPicker } from "./CredentialPicker";
import { PatPanel } from "./PatPanel";
import { SshKeyPanel } from "./SshKeyPanel";
import { TlsTrustDialog } from "./TlsTrustDialog";
import { TokenCheckCard } from "./TokenCheckCard";

export type RemoteAuthFieldsProps = {
  auth: RemoteAuth;
  url: ParsedRemoteUrl;
  fixing?: boolean;
  /** Доступ, с которым проект подключён сейчас (для `fix_access`). */
  bound?: { id: string; label: string; kind: string } | null;
  isLoadingCredentials: boolean;
  secretsOk: boolean;
  onSwitchUrl: (value: string) => void;
  /** Название проекта: попадает в имя токена на странице сервера. */
  projectName?: string | null;
};

// Поля доступа к репозиторию: способ (токен, ключ), сохранённые доступы и формы
// создания нового. Общие для шага «Доступ» окна подключения и для мастера
// клонирования; кнопки действия у каждого шага свои.
export const RemoteAuthFields = ({
  auth,
  url,
  fixing = false,
  bound = null,
  isLoadingCredentials,
  secretsOk,
  onSwitchUrl,
  projectName = null,
}: RemoteAuthFieldsProps) => {
  const { t } = useTranslation("gitAccess");
  const provider = useHostProvider(url);
  const [tlsOpen, setTlsOpen] = useState(false);
  const {
    method,
    mismatch,
    pats,
    boundPat,
    boundKey,
    creatingPat,
    error,
    isSaving,
  } = auth;
  const host = auth.host ?? "";

  // Результат проверки показываем для того токена, который сейчас выбран.
  const check = auth.tokenCheck;
  const currentId = boundPat?.id ?? (creatingPat ? null : auth.patChoice);
  const showCheck =
    method === "pat" &&
    check.status !== "idle" &&
    (check.status === "checking" || check.credentialId === currentId);
  const verdict = check.status === "done" ? check.verdict : null;
  const certificate = verdict?.kind === "error" ? verdict.certificate : null;
  const createUrl = tokenCreateUrl(url, {
    provider: url.provider,
    subpath: provider.subpath,
    projectName,
  });

  const methods: AccessMethod[] = auth.allowAnonymous
    ? ["pat", "ssh", "none"]
    : ["pat", "ssh"];

  return (
    <>
      {!secretsOk && (
        <Notice tone="err" role="alert" text={t("secretsUnavailable")} />
      )}

      {!fixing && (
        <div
          className="seg"
          role="group"
          aria-label={t("method.label")}
          style={{ alignSelf: "flex-start", flexWrap: "wrap" }}
        >
          {methods.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={method === value}
              className={method === value ? "active" : undefined}
              onClick={() => {
                auth.setMethod(value);
              }}
            >
              {t(`method.${value}`)}
            </button>
          ))}
        </div>
      )}

      {mismatch && (
        <Notice
          tone="info"
          role="status"
          text={mismatch.text}
          action={
            !fixing && mismatch.target ? (
              <button
                type="button"
                className="btn xs"
                onClick={() => {
                  const target = mismatch.target;
                  if (!target) return;
                  onSwitchUrl(target);
                }}
              >
                {t("mismatch.replace", { target: mismatch.target })}
              </button>
            ) : undefined
          }
        />
      )}

      {isLoadingCredentials && method !== "none" && (
        <div className="flex items-center dim" style={{ gap: 8, fontSize: 12 }}>
          <Spinner size="sm" />
          {t("picker.loading")}
        </div>
      )}

      {method === "none" && (
        <Notice tone="info" role="status" text={t("none.hint")} />
      )}

      {method === "pat" && !isLoadingCredentials && (
        <>
          {!boundPat && pats.length > 0 && (
            <CredentialPicker
              credentials={pats}
              value={auth.patChoice}
              host={host}
              onChange={auth.selectPat}
            />
          )}
          {(creatingPat || boundPat) && (
            <PatPanel
              draft={auth.draft}
              onChange={auth.setDraft}
              showToken={auth.showToken}
              onToggleShowToken={auth.toggleShowToken}
              url={url}
              existing={boundPat}
              helpOpen={pats.length === 0 && !boundPat}
              disabled={!secretsOk || isSaving}
              error={error}
              projectName={projectName}
              serverVersion={provider.detection.version}
              onPasteToken={(token) => {
                void auth.checkToken(token);
              }}
              onCheckToken={() => {
                void auth.checkToken();
              }}
            />
          )}
          {!creatingPat && !boundPat && currentId && !showCheck && (
            <div>
              <button
                type="button"
                className="btn sm"
                data-testid="check-saved-token"
                disabled={isSaving || !secretsOk}
                onClick={auth.checkSaved}
              >
                <ScanSearch size={13} aria-hidden="true" />
                {t("pat.checkSaved")}
              </button>
            </div>
          )}
          {showCheck && (
            <TokenCheckCard
              verdict={verdict}
              provider={url.provider}
              version={
                (check.status === "done" ? check.provider?.version : null) ??
                provider.detection.version
              }
              createUrl={createUrl}
              onRetry={auth.recheck}
              onReviewCertificate={() => {
                setTlsOpen(true);
              }}
            />
          )}
          {!creatingPat && !boundPat && error && (
            <Notice tone="err" role="alert" text={error} />
          )}
        </>
      )}

      {method === "ssh" && !isLoadingCredentials && (
        <SshKeyPanel
          url={url}
          keys={boundKey ? [boundKey] : auth.keys}
          selectedId={auth.keyChoice}
          onSelect={auth.selectKey}
          onCreate={() => {
            void auth.createKey();
          }}
          isCreating={isSaving}
          disabled={!secretsOk}
          error={error}
        />
      )}

      {fixing && bound && (
        <button
          type="button"
          className="sync-history-link"
          onClick={auth.toggleUseOther}
        >
          {auth.useOther ? t("fix.useBound") : t("fix.useOther")}
        </button>
      )}

      {url.host && (
        <TlsTrustDialog
          isOpen={tlsOpen}
          mode={
            verdict?.kind === "error" && verdict.code === "tls_pin_mismatch"
              ? "pin_mismatch"
              : "untrusted"
          }
          host={url.host}
          port={provider.port}
          certificate={certificate}
          onTrusted={() => {
            setTlsOpen(false);
            auth.recheck();
          }}
          onClose={() => {
            setTlsOpen(false);
          }}
        />
      )}
    </>
  );
};
