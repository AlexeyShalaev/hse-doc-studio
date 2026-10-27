import { useEffect, useId, useState } from "react";
import { Check, Globe, ScanSearch, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { providerSpec } from "@entities/git-remote";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";
import type { ParsedRemoteUrl } from "../lib/parseRemoteUrl";
import type { AccessMethod, RemoteAuth } from "../model/useRemoteAuth";
import { repoPathOf } from "../lib/keyScope";
import { tokenCreateUrl } from "../lib/providerHelp";
import { useHostProvider } from "../model/useHostProvider";
import { AccessTabs } from "./AccessTabs";
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
  const uid = useId();
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
  const pinExpected = verdict?.kind === "error" ? verdict.expected : null;
  const pinActual = verdict?.kind === "error" ? verdict.actual : null;
  const createUrl = tokenCreateUrl(url, {
    provider: url.provider,
    subpath: provider.subpath,
    projectName,
  });

  // Какие способы предлагаем: deploy-ключ только там, где сервер его умеет, и
  // только когда в адресе есть репозиторий, к которому его привязать.
  const repoPath = repoPathOf(url);
  const spec = providerSpec(url.provider);
  const methods: AccessMethod[] = ["pat", "ssh"];
  if (spec.auth_variants.includes("deploy_key") && repoPath !== "")
    methods.push("deploy");
  if (auth.allowAnonymous) methods.push("none");
  const available = methods.includes(method);
  const setMethod = auth.setMethod;
  useEffect(() => {
    // Тип сервера могли поправить, и выбранного способа у него нет.
    const first = methods[0];
    if (!available && !fixing && first) setMethod(first);
  });

  return (
    <>
      {!secretsOk && (
        <Notice tone="err" role="alert" text={t("secretsUnavailable")} />
      )}

      {!fixing && (
        <AccessTabs
          id={uid}
          methods={methods}
          value={method}
          onChange={auth.setMethod}
        />
      )}

      <div
        role={fixing ? undefined : "tabpanel"}
        id={`${uid}-panel`}
        aria-labelledby={fixing ? undefined : `${uid}-tab-${method}`}
        className="flex flex-col"
        style={{ gap: 12 }}
      >
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
          <div
            className="flex items-center dim"
            style={{ gap: 8, fontSize: 12 }}
          >
            <Spinner size="sm" />
            {t("picker.loading")}
          </div>
        )}

        {method === "none" && <PublicRepoPanel />}

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

        {(method === "ssh" || method === "deploy") && !isLoadingCredentials && (
          <SshKeyPanel
            url={url}
            scope={method === "deploy" ? "deploy" : "user"}
            repoPath={repoPath}
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
      </div>

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
          expected={pinExpected}
          actual={pinActual}
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

// Открытый репозиторий без токена: коротко, что получится и чего нет.
const PublicRepoPanel = () => {
  const { t } = useTranslation("gitAccess");
  const rows: { ok: boolean; text: string }[] = [
    { ok: true, text: t("none.can") },
    { ok: false, text: t("none.cannot") },
  ];
  return (
    <div
      className="flex flex-col"
      data-testid="public-panel"
      style={{
        gap: 10,
        padding: 14,
        borderRadius: "var(--r-3)",
        border: "1px dashed var(--border-strong)",
        background: "var(--bg-2)",
      }}
    >
      <div className="flex items-start" style={{ gap: 10 }}>
        <span
          aria-hidden="true"
          style={{
            width: 32,
            height: 32,
            flexShrink: 0,
            borderRadius: "50%",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--accent-soft)",
            color: "var(--accent)",
          }}
        >
          <Globe size={16} />
        </span>
        <div style={{ fontSize: 12.5, lineHeight: 1.5 }}>
          <strong style={{ display: "block", fontWeight: 600 }}>
            {t("none.title")}
          </strong>
          <span className="dim">{t("none.hint")}</span>
        </div>
      </div>
      <ul
        style={{
          listStyle: "none",
          margin: 0,
          padding: 0,
          display: "flex",
          flexDirection: "column",
          gap: 4,
          fontSize: 12,
        }}
      >
        {rows.map((row) => (
          <li key={row.text} className="flex items-center" style={{ gap: 6 }}>
            {row.ok ? (
              <Check
                size={13}
                aria-hidden="true"
                style={{ color: "var(--c-ok)" }}
              />
            ) : (
              <X
                size={13}
                aria-hidden="true"
                style={{ color: "var(--c-warn)" }}
              />
            )}
            {row.text}
          </li>
        ))}
      </ul>
    </div>
  );
};
